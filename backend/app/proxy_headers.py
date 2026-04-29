from __future__ import annotations

import ipaddress
from typing import TYPE_CHECKING

from starlette.datastructures import MutableHeaders

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send

DEFAULT_PORTS: dict[str, int] = {
    "http": 80,
    "https": 443,
    "ws": 80,
    "wss": 443,
}


def _split_header_values(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_host_port(value: str) -> tuple[str, int | None]:
    value = value.strip()
    if not value:
        return "", None

    if value.startswith("["):
        bracket_end = value.find("]")
        if bracket_end == -1:
            return value, None

        host = value[1:bracket_end]
        remainder = value[bracket_end + 1 :]
        if not remainder:
            return host, None
        if not remainder.startswith(":"):
            return value, None

        try:
            return host, int(remainder[1:])
        except ValueError:
            return host, None

    if value.count(":") == 1:
        host, port = value.rsplit(":", 1)
        if not host:
            return value, None

        try:
            return host, int(port)
        except ValueError:
            return value, None

    return value, None


def _format_host_header(host: str, port: int, scheme: str, include_port: bool) -> str:
    host_value = f"[{host}]" if ":" in host and not host.startswith("[") else host
    if not include_port or port == DEFAULT_PORTS.get(scheme, 80):
        return host_value
    return f"{host_value}:{port}"


def _parse_forwarded_port(value: str) -> int | None:
    values = _split_header_values(value)
    if not values:
        return None

    try:
        return int(values[0])
    except ValueError:
        return None


class TrustedProxyNetworks:
    def __init__(self, trusted_hosts: list[str] | str) -> None:
        """Parse configured proxy IPs, CIDRs, or literals into trusted matchers."""
        if isinstance(trusted_hosts, str):
            trusted_hosts = _split_header_values(trusted_hosts)

        self.allow_all = trusted_hosts == ["*"]
        self.trusted_literals: set[str] = set()
        self.trusted_hosts: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
        self.trusted_networks: set[ipaddress.IPv4Network | ipaddress.IPv6Network] = set()

        if self.allow_all:
            return

        for host in trusted_hosts:
            if "/" in host:
                try:
                    self.trusted_networks.add(ipaddress.ip_network(host, strict=False))
                except ValueError:
                    self.trusted_literals.add(host)
                continue

            try:
                self.trusted_hosts.add(ipaddress.ip_address(host))
            except ValueError:
                self.trusted_literals.add(host)

    def __contains__(self, host: str | None) -> bool:
        if self.allow_all:
            return True
        if not host:
            return False

        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return host in self.trusted_literals

        if ip in self.trusted_hosts:
            return True

        return any(ip in network for network in self.trusted_networks)

    def get_client_address(self, forwarded_for: str) -> tuple[str, int | None]:
        hosts = _split_header_values(forwarded_for)
        if not hosts:
            return "", None

        if self.allow_all:
            return _parse_host_port(hosts[0])

        for host_port in reversed(hosts):
            host, port = _parse_host_port(host_port)
            if host not in self:
                return host, port

        return _parse_host_port(hosts[0])


class TrustedProxyHeadersMiddleware:
    def __init__(self, app: ASGIApp, trusted_hosts: list[str] | str) -> None:
        """Trust forwarded headers only from explicitly configured proxy addresses."""
        self.app = app
        self.trusted_hosts = TrustedProxyNetworks(trusted_hosts)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        client_addr = scope.get("client")
        client_host = client_addr[0] if client_addr else None
        if client_host not in self.trusted_hosts:
            await self.app(scope, receive, send)
            return

        headers = MutableHeaders(scope=scope)

        if forwarded_proto := _split_header_values(headers.get("x-forwarded-proto", "")):
            proto = forwarded_proto[0].lower()
            if proto in {"http", "https", "ws", "wss"}:
                if scope["type"] == "websocket":
                    scope["scheme"] = proto.replace("http", "ws")
                else:
                    scope["scheme"] = proto

        if forwarded_for := headers.get("x-forwarded-for"):
            host, port = self.trusted_hosts.get_client_address(forwarded_for)
            if host:
                scope["client"] = (host, port or 0)

        if forwarded_host := _split_header_values(headers.get("x-forwarded-host", "")):
            host, port = _parse_host_port(forwarded_host[0])
            if host:
                scheme = scope.get("scheme", "http")
                forwarded_port = _parse_forwarded_port(headers.get("x-forwarded-port", ""))
                resolved_port = forwarded_port or port or DEFAULT_PORTS.get(scheme, 80)
                include_port = forwarded_port is not None or port is not None

                headers["host"] = _format_host_header(host, resolved_port, scheme, include_port=include_port)
                scope["server"] = (host, resolved_port)

        await self.app(scope, receive, send)
