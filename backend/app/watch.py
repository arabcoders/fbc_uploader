# Copyright (c) 2026 FBC Uploader contributors
"""Single-process Watch Party rooms."""

from __future__ import annotations

import asyncio
import contextlib
import math
import secrets
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from fastapi import WebSocket

MAX_PARTICIPANTS = 32
MAX_ROOMS = 1000
ROOM_TTL_SECONDS = 1800
STALE_PARTICIPANT_SECONDS = 90
NEVER_JOINED_TTL_SECONDS = 60
MAX_ROOMS_PER_TOKEN = 3
HOST_RECONNECT_GRACE_SECONDS = 15
MESSAGE_WINDOW_SECONDS = 2.0
MAX_MESSAGES_PER_WINDOW = 60
SEND_TIMEOUT_SECONDS = 5
MIN_RATE = 0.25
MAX_RATE = 4.0
MAX_POSITION_SECONDS = 86400.0
COMMAND_WINDOW_SECONDS = 2.0
MAX_COMMANDS_PER_WINDOW = 20
PLAY_LEAD_SECONDS = 0.5
ERROR_CAPACITY = "capacity"
ERROR_CREDENTIAL = "credential"
ERROR_FULL = "full"
ERROR_HOST_KEY = "host_key"
ERROR_AUTHORITY = "authority"
ERROR_RATE_LIMIT = "rate_limit"
ERROR_MESSAGE_RATE_LIMIT = "message_rate_limit"
ERROR_COMMAND = "command"
ERROR_RATE = "rate"
ERROR_PAUSED = "paused"
ERROR_POSITION = "position"
ERROR_SYNC = "sync"
ERROR_UPLOAD = "upload"
ERROR_ROOM = "room"


class WatchRoomError(ValueError):
    """An error that can be returned to a room client."""

    messages: ClassVar[dict[str, str]] = {
        "capacity": "Watch Party capacity reached",
        "credential": "Invalid room credential",
        "full": "Watch Party is full",
        "host_key": "Invalid host key",
        "authority": "Only the host can control playback",
        "rate_limit": "Playback command rate exceeded",
        "message_rate_limit": "Message rate exceeded",
        "command": "Unsupported command",
        "rate": "Invalid playback rate",
        "paused": "Invalid paused state",
        "position": "Invalid position",
        "sync": "Synchronize the current Watch Party state before controlling playback",
        "message": "Message must be an object",
        "json": "Invalid JSON message",
        "size": "Message too large",
        "join": "Invalid join message",
        "ping": "Invalid ping",
        "upload": "Invalid upload",
        "room": "Watch Party not found",
    }

    def __str__(self) -> str:
        return self.messages.get(str(self.args[0]), "Watch Party request rejected")


@dataclass
class Participant:
    socket: WebSocket
    joined_at: int
    is_host: bool = False
    pending_sync: bool = False
    sync_version: int = 0
    command_window_started: float = field(default_factory=time.monotonic)
    command_count: int = 0
    last_seen: float = field(default_factory=time.monotonic)
    message_window_started: float = field(default_factory=time.monotonic)
    message_count: int = 0


@dataclass
class WatchRoom:
    room_id: str
    host_key: str
    download_token: str
    upload_id: str
    token_expires_at: float | None = None
    created_at: float = field(default_factory=time.monotonic)
    last_activity: float = field(default_factory=time.monotonic)
    version: int = 0
    anchor_position: float = 0.0
    anchor_server_time: float = field(default_factory=time.time)
    paused: bool = True
    playback_rate: float = 1.0
    play_at: float | None = None
    participant_version: int = 0
    participants: dict[str, Participant] = field(default_factory=dict)
    host_established: bool = False
    host_reconnect_until: float | None = None

    def projected_position(self, server_time: float | None = None) -> float:
        now = time.time() if server_time is None else server_time
        if self.paused:
            return self.anchor_position
        elapsed = max(0.0, now - self.anchor_server_time)
        return min(MAX_POSITION_SECONDS, max(0.0, self.anchor_position + elapsed * self.playback_rate))


class WatchRoomManager:
    """Store rooms, participants, and playback state for this process."""

    def __init__(self) -> None:
        """Create an empty room manager."""
        self.rooms: dict[str, WatchRoom] = {}
        self._superseded: dict[str, tuple[WatchRoom, WebSocket]] = {}
        self._lock = asyncio.Lock()
        self._join_sequence = 0

    async def create(self, download_token: str, upload_id: str, expires_at: datetime | float | None = None) -> WatchRoom:
        async with self._lock:
            if len(self.rooms) >= MAX_ROOMS:
                raise WatchRoomError(ERROR_CAPACITY)
            if sum(room.download_token == download_token for room in self.rooms.values()) >= MAX_ROOMS_PER_TOKEN:
                raise WatchRoomError(ERROR_CAPACITY)
            if isinstance(expires_at, datetime):
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=UTC)
                token_expires_at = expires_at.timestamp()
            else:
                token_expires_at = expires_at
            room = WatchRoom(secrets.token_urlsafe(18), secrets.token_urlsafe(32), download_token, upload_id, token_expires_at)
            self.rooms[room.room_id] = room
            return room

    def get(self, room_id: str) -> WatchRoom | None:
        return self.rooms.get(room_id)

    async def join(
        self, room: WatchRoom, socket: WebSocket, credential: str, host_key: str | None, upload_id: str
    ) -> tuple[str, bool, bool]:
        superseded_socket: WebSocket | None = None
        async with self._lock:
            if self.rooms.get(room.room_id) is not room:
                raise WatchRoomError(ERROR_ROOM)
            if not isinstance(upload_id, str) or not secrets.compare_digest(upload_id, room.upload_id):
                raise WatchRoomError(ERROR_UPLOAD)
            if not secrets.compare_digest(credential, room.download_token):
                raise WatchRoomError(ERROR_CREDENTIAL)
            if host_key is not None and not isinstance(host_key, str):
                raise WatchRoomError(ERROR_HOST_KEY)
            is_host = False
            reconnected = False
            if host_key is not None:
                if not secrets.compare_digest(host_key, room.host_key):
                    raise WatchRoomError(ERROR_HOST_KEY)
                if room.host_reconnect_until is not None and time.monotonic() > room.host_reconnect_until:
                    raise WatchRoomError(ERROR_HOST_KEY)
                is_host = True
                reconnected = room.host_established or room.host_reconnect_until is not None
                old_host_id = next((key for key, value in room.participants.items() if value.is_host), None)
                effective_count = len(room.participants) - (1 if old_host_id is not None else 0) + 1
                if effective_count > MAX_PARTICIPANTS:
                    raise WatchRoomError(ERROR_FULL)
            elif len(room.participants) >= MAX_PARTICIPANTS - (0 if room.host_established else 1):
                raise WatchRoomError(ERROR_FULL)
            if host_key is not None:
                if room.host_established:
                    if old_host_id is not None:
                        superseded_socket = room.participants.pop(old_host_id).socket
                    timestamp = time.time()
                    room.anchor_position = room.projected_position(timestamp)
                    room.anchor_server_time = timestamp
                    room.paused = True
                    room.play_at = None
                if reconnected:
                    room.version += 1
                room.host_established = True
                room.host_key = secrets.token_urlsafe(32)
                room.host_reconnect_until = None
            self._join_sequence += 1
            participant_id = secrets.token_urlsafe(12)
            room.participants[participant_id] = Participant(
                socket, self._join_sequence, is_host, reconnected, room.version if reconnected else 0
            )
            room.participant_version += 1
            if superseded_socket is not None:
                self._superseded[participant_id] = (room, superseded_socket)
            room.last_activity = time.monotonic()
        return participant_id, is_host, reconnected

    async def close_superseded(self, participant_id: str) -> None:
        async with self._lock:
            entry = self._superseded.get(participant_id)
        if entry is None:
            return
        _, socket = entry
        await self._close_socket(socket)
        async with self._lock:
            if self._superseded.get(participant_id) == entry:
                self._superseded.pop(participant_id, None)

    async def _drain_superseded(self, room_ids: set[str] | None = None) -> None:
        async with self._lock:
            participant_ids = [
                participant_id for participant_id, (room, _) in self._superseded.items() if room_ids is None or room.room_id in room_ids
            ]
        for participant_id in participant_ids:
            await self.close_superseded(participant_id)

    async def participant_message(self, room: WatchRoom) -> dict[str, Any] | None:
        async with self._lock:
            if self.rooms.get(room.room_id) is not room:
                return None
            participant_count = len(room.participants)
            participant_version = room.participant_version
        return {
            "type": "participants",
            "participant_count": participant_count,
            "participant_version": participant_version,
        }

    async def waiting_version(self, room: WatchRoom) -> int | None:
        async with self._lock:
            if self.rooms.get(room.room_id) is room and room.host_reconnect_until is not None:
                return room.version
            return None

    async def synced(self, room: WatchRoom, participant_id: str, version: int) -> dict[str, Any] | None:
        async with self._lock:
            if self.rooms.get(room.room_id) is not room:
                raise WatchRoomError(ERROR_ROOM)
            participant = room.participants.get(participant_id)
            if participant is None or not participant.is_host:
                raise WatchRoomError(ERROR_AUTHORITY)
            if not participant.pending_sync or version != participant.sync_version or version != room.version:
                return self.state(room)
            participant.pending_sync = False
            return None

    async def remove(self, room: WatchRoom, participant_id: str) -> None:
        notifications: list[dict[str, Any]] = []
        async with self._lock:
            if self.rooms.get(room.room_id) is not room:
                return
            participant = room.participants.pop(participant_id, None)
            if participant is None:
                return
            room.participant_version += 1
            room.last_activity = time.monotonic()
            if participant.is_host and room.host_established:
                timestamp = time.time()
                room.anchor_position = room.projected_position(timestamp)
                room.anchor_server_time = timestamp
                room.paused = True
                room.play_at = None
                room.version += 1
                room.host_established = False
                room.host_reconnect_until = time.monotonic() + HOST_RECONNECT_GRACE_SECONDS
                notifications = [
                    {"type": "host_status", "status": "waiting", "version": room.version},
                    self.state(room),
                ]
            elif participant.is_host or (not room.participants and room.host_established):
                self.rooms.pop(room.room_id, None)
        for message in notifications:
            await self.broadcast(room, message)

    async def discard(self, room_id: str, host_key: str) -> bool:
        async with self._lock:
            room = self.rooms.get(room_id)
            if room is None:
                return False
            valid_key = secrets.compare_digest(host_key, room.host_key)
            if not valid_key or room.participants or room.host_established:
                return False
            self.rooms.pop(room_id, None)
            return True

    async def promote_expired(self, room: WatchRoom) -> None:
        while True:
            async with self._lock:
                if room.host_established or room.host_reconnect_until is None or time.monotonic() <= room.host_reconnect_until:
                    return
                candidates = sorted(room.participants.items(), key=lambda item: item[1].joined_at)
                if not candidates:
                    self.rooms.pop(room.room_id, None)
                    return
                promoted_id, participant = candidates[0]
                participant.is_host = True
                participant.pending_sync = True
                room.host_key = secrets.token_urlsafe(32)
                room.host_established = True
                room.host_reconnect_until = None
                room.version += 1
                participant.sync_version = room.version
                notice = {"type": "promotion", "participant_id": promoted_id, "version": room.version, "host_key": room.host_key}
            if await self._send(participant.socket, notice):
                await self.broadcast(room, {"type": "host_status", "status": "connected", "version": room.version})
                await self.broadcast(room, self.state(room))
                return
            async with self._lock:
                if self.rooms.get(room.room_id) is not room:
                    return
                if room.participants.pop(promoted_id, None) is not None:
                    room.participant_version += 1
                    room.host_established = False
                    room.host_reconnect_until = 0
                    room.last_activity = time.monotonic()
                elif not room.host_established:
                    # The failed socket's handler may have removed it and started a
                    # grace period. No client received this promotion key, so retry now.
                    room.host_reconnect_until = 0

    async def command(self, room: WatchRoom, participant_id: str, message: dict[str, Any]) -> dict[str, Any]:
        async with self._lock:
            if self.rooms.get(room.room_id) is not room:
                raise WatchRoomError(ERROR_ROOM)
            participant = room.participants.get(participant_id)
            if participant is None or not participant.is_host:
                raise WatchRoomError(ERROR_AUTHORITY)
            if participant.pending_sync:
                raise WatchRoomError(ERROR_SYNC)
            now = time.monotonic()
            if now - participant.command_window_started >= COMMAND_WINDOW_SECONDS:
                participant.command_window_started = now
                participant.command_count = 0
            participant.command_count += 1
            if participant.command_count > MAX_COMMANDS_PER_WINDOW:
                raise WatchRoomError(ERROR_RATE_LIMIT)
            kind = message.get("type")
            if not isinstance(kind, str) or kind not in {"play", "pause", "seek", "rate", "snapshot"}:
                raise WatchRoomError(ERROR_COMMAND)
            position = self._position(message)
            rate: float | None = None
            paused: bool | None = None
            if kind in {"rate", "snapshot"}:
                raw_rate = message.get("playback_rate")
                if (
                    not isinstance(raw_rate, (int, float))
                    or isinstance(raw_rate, bool)
                    or not _finite(raw_rate)
                    or not MIN_RATE <= raw_rate <= MAX_RATE
                ):
                    raise WatchRoomError(ERROR_RATE)
                rate = float(raw_rate)
            if kind == "snapshot":
                paused = message.get("paused")
                if not isinstance(paused, bool):
                    raise WatchRoomError(ERROR_PAUSED)
            room.anchor_position = position
            timestamp = time.time()
            if kind == "play":
                room.play_at = timestamp + PLAY_LEAD_SECONDS
                room.anchor_server_time = room.play_at
                room.paused = False
            else:
                room.play_at = None
                room.anchor_server_time = timestamp
            if kind == "pause":
                room.paused = True
            elif kind == "rate":
                room.playback_rate = rate or room.playback_rate
            elif kind == "snapshot":
                room.paused = bool(paused)
                room.playback_rate = rate or room.playback_rate
            room.version += 1
            room.last_activity = time.monotonic()
            return self.state(room)

    async def touch(self, room: WatchRoom, participant_id: str) -> None:
        async with self._lock:
            if self.rooms.get(room.room_id) is not room:
                raise WatchRoomError(ERROR_ROOM)
            if participant := room.participants.get(participant_id):
                participant.last_seen = time.monotonic()
                room.last_activity = participant.last_seen

    async def message_allowed(self, room: WatchRoom, participant_id: str) -> None:
        async with self._lock:
            if self.rooms.get(room.room_id) is not room:
                raise WatchRoomError(ERROR_ROOM)
            participant = room.participants.get(participant_id)
            if participant is None:
                raise WatchRoomError(ERROR_CREDENTIAL)
            now = time.monotonic()
            if now - participant.message_window_started >= MESSAGE_WINDOW_SECONDS:
                participant.message_window_started, participant.message_count = now, 0
            participant.message_count += 1
            if participant.message_count > MAX_MESSAGES_PER_WINDOW:
                raise WatchRoomError(ERROR_MESSAGE_RATE_LIMIT)

    @staticmethod
    def _position(message: dict[str, Any]) -> float:
        position = message.get("position")
        if (
            not isinstance(position, (int, float))
            or isinstance(position, bool)
            or not _finite(position)
            or not 0 <= position <= MAX_POSITION_SECONDS
        ):
            raise WatchRoomError(ERROR_POSITION)
        return float(position)

    def state(self, room: WatchRoom) -> dict[str, Any]:
        server_time = time.time()
        return {
            "type": "state",
            "version": room.version,
            "anchor_position": room.projected_position(server_time),
            "paused": room.paused,
            "playback_rate": room.playback_rate,
            "play_at": room.play_at if not room.paused else None,
            "server_time": server_time,
            "participant_count": len(room.participants),
            "participant_version": room.participant_version,
        }

    async def broadcast(self, room: WatchRoom, message: dict[str, Any]) -> None:
        async with self._lock:
            recipients = list(room.participants.items())
        results = await asyncio.gather(*(self._send(participant.socket, message) for _, participant in recipients))
        stale = [participant_id for (participant_id, _), success in zip(recipients, results, strict=True) if not success]
        for participant_id in stale:
            await self.remove(room, participant_id)

    @staticmethod
    async def _send(socket: WebSocket, message: dict[str, Any]) -> bool:
        try:
            await asyncio.wait_for(socket.send_json(message), SEND_TIMEOUT_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await asyncio.wait_for(socket.close(code=1001), SEND_TIMEOUT_SECONDS)
            return False
        return True

    @staticmethod
    async def _close_socket(socket: WebSocket) -> None:
        try:
            await asyncio.wait_for(socket.close(code=1001), SEND_TIMEOUT_SECONDS)
        except Exception:
            return

    async def cleanup(self) -> None:
        now = time.monotonic()
        wall_now = time.time()
        async with self._lock:
            rooms = list(self.rooms.values())
        for room in rooms:
            async with self._lock:
                if self.rooms.get(room.room_id) is not room:
                    continue
                if room.token_expires_at is not None and wall_now >= room.token_expires_at:
                    participants = list(room.participants.values())
                    self.rooms.pop(room.room_id, None)
                    expired = True
                else:
                    participants = []
                    expired = False
                if expired:
                    pass
                else:
                    stale = [
                        participant_id
                        for participant_id, participant in room.participants.items()
                        if now - participant.last_seen > STALE_PARTICIPANT_SECONDS
                    ]
                    stale_sockets = []
                    stale_notifications: list[dict[str, Any]] = []
                    for participant_id in stale:
                        participant = room.participants.pop(participant_id)
                        room.participant_version += 1
                        stale_sockets.append(participant.socket)
                        if participant.is_host and room.host_established:
                            timestamp = time.time()
                            room.anchor_position = room.projected_position(timestamp)
                            room.anchor_server_time = timestamp
                            room.paused = True
                            room.play_at = None
                            room.version += 1
                            room.host_established = False
                            room.host_reconnect_until = time.monotonic() + HOST_RECONNECT_GRACE_SECONDS
                            stale_notifications.extend(
                                [
                                    {"type": "host_status", "status": "waiting", "version": room.version},
                                    self.state(room),
                                ]
                            )
                    room.last_activity = now if stale else room.last_activity
            if expired:
                await asyncio.gather(*(self._close_socket(participant.socket) for participant in participants))
                await self._drain_superseded({room.room_id})
                continue
            for message in stale_notifications:
                await self.broadcast(room, message)
            if stale:
                participant_message = await self.participant_message(room)
                if participant_message is not None:
                    await self.broadcast(room, participant_message)
            await asyncio.gather(*(self._close_socket(socket) for socket in stale_sockets))
            await self.promote_expired(room)
            async with self._lock:
                abandoned = not room.participants and not room.host_established and now - room.created_at > NEVER_JOINED_TTL_SECONDS
            if abandoned or now - room.last_activity > ROOM_TTL_SECONDS:
                async with self._lock:
                    if self.rooms.get(room.room_id) is not room:
                        continue
                    current_now = time.monotonic()
                    should_remove = (
                        not room.participants and not room.host_established and current_now - room.created_at > NEVER_JOINED_TTL_SECONDS
                    ) or (current_now - room.last_activity > ROOM_TTL_SECONDS)
                    if not should_remove:
                        continue
                    participants = list(room.participants.values())
                    self.rooms.pop(room.room_id, None)
                await asyncio.gather(*(self._close_socket(participant.socket) for participant in participants))
                await self._drain_superseded({room.room_id})

    async def invalidate(self, download_token: str | None = None, upload_id: str | None = None) -> None:
        """Remove and close rooms matching an invalidated token or upload."""
        async with self._lock:
            rooms = [
                room
                for room in self.rooms.values()
                if (download_token is None or room.download_token == download_token) and (upload_id is None or room.upload_id == upload_id)
            ]
            for room in rooms:
                self.rooms.pop(room.room_id, None)
            participants = [participant for room in rooms for participant in room.participants.values()]
            room_ids = {room.room_id for room in rooms}
        await self._drain_superseded(room_ids)
        await asyncio.gather(*(self._close_socket(participant.socket) for participant in participants))

    async def update_expiry(self, download_token: str, expires_at: datetime | float) -> None:
        """Update or invalidate rooms for a token whose expiry changed."""
        if isinstance(expires_at, datetime):
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            expiry = expires_at.timestamp()
        else:
            expiry = expires_at

        async with self._lock:
            rooms = [room for room in self.rooms.values() if room.download_token == download_token]
            if time.time() >= expiry:
                for room in rooms:
                    self.rooms.pop(room.room_id, None)
                participants = [participant for room in rooms for participant in room.participants.values()]
                room_ids = {room.room_id for room in rooms}
            else:
                for room in rooms:
                    room.token_expires_at = expiry
                participants = []
                room_ids = set()
        await self._drain_superseded(room_ids)
        await asyncio.gather(*(self._close_socket(participant.socket) for participant in participants))

    async def close(self) -> None:
        async with self._lock:
            participants = [participant for room in self.rooms.values() for participant in room.participants.values()]
            self.rooms.clear()
        await self._drain_superseded()
        await asyncio.gather(*(self._close_socket(participant.socket) for participant in participants))


def _finite(value: float) -> bool:
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False
