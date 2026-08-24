# Copyright (c) 2026 FBC Uploader contributors
"""HTTP and WebSocket endpoints for Watch Party rooms."""

from __future__ import annotations

import asyncio
import contextlib
import json
import math
import time
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel

from backend.app.config import settings
from backend.app.db import SessionLocal
from backend.app.routers.tokens import _get_accessible_upload
from backend.app.watch import ERROR_CREDENTIAL, WatchRoomError, WatchRoomManager

ERROR_MESSAGE = "message"
ERROR_JSON = "json"
ERROR_SIZE = "size"
ERROR_JOIN = "join"
ERROR_PING = "ping"

router = APIRouter(tags=["watch"])
MAX_MESSAGE_BYTES = 8192
JOIN_TIMEOUT_SECONDS = 10


class WatchCreation(BaseModel):
    room_id: str
    host_key: str
    invite_path: str


def get_manager(request: Request) -> WatchRoomManager:
    return request.app.state.watch_rooms


@router.post("/api/tokens/{download_token}/uploads/{upload_id}/watch", response_model=WatchCreation, name="create_watch_room")
async def create_watch_room(request: Request, download_token: str, upload_id: str) -> WatchCreation:
    if not settings.allow_public_downloads:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Public downloads are disabled")
    async with SessionLocal() as db:
        token, record, _ = await _get_accessible_upload(download_token, upload_id, db, False)
    if not (record.mimetype or "").startswith(("video/", "audio/")):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Upload is not playable media")
    try:
        room = await get_manager(request).create(token.download_token, record.public_id, token.expires_at)
    except WatchRoomError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return WatchCreation(
        room_id=room.room_id, host_key=room.host_key, invite_path=f"/f/{download_token}?upload={record.public_id}&room={room.room_id}"
    )


@router.delete("/api/watch/{room_id}", status_code=status.HTTP_204_NO_CONTENT, name="discard_watch_room")
async def discard_watch_room(request: Request, room_id: str, x_watch_host_key: Annotated[str | None, Header()] = None) -> None:
    manager: WatchRoomManager = get_manager(request)
    room = manager.get(room_id)
    if room is None or x_watch_host_key is None or not await manager.discard(room_id, x_watch_host_key):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watch Party not found")


async def _read_message(websocket: WebSocket) -> dict[str, Any]:
    return _parse_message(await websocket.receive_text())


def _parse_message(raw: str) -> dict[str, Any]:
    if len(raw.encode()) > MAX_MESSAGE_BYTES:
        raise WatchRoomError(ERROR_SIZE)
    try:
        message = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise WatchRoomError(ERROR_JSON) from exc
    if not isinstance(message, dict):
        raise WatchRoomError(ERROR_MESSAGE)
    return message


async def _send_error(websocket: WebSocket, message: str) -> None:
    with contextlib.suppress(Exception):
        await websocket.send_json({"type": "error", "message": message[:160]})


@router.websocket("/api/watch/{room_id}/ws", name="watch_websocket")
async def watch_websocket(websocket: WebSocket, room_id: str) -> None:
    await websocket.accept()
    manager: WatchRoomManager = websocket.app.state.watch_rooms
    room = manager.get(room_id)
    if room is None:
        await _send_error(websocket, "Watch Party not found")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    participant_id: str | None = None
    try:
        try:
            message = await asyncio.wait_for(_read_message(websocket), JOIN_TIMEOUT_SECONDS)
            credential = message.get("download_token")
            host_key = message.get("host_key")
            upload_id = message.get("upload_id")
            if (
                message.get("type") != "join"
                or not isinstance(credential, str)
                or not isinstance(upload_id, str)
                or (host_key is not None and not isinstance(host_key, str))
            ):
                raise WatchRoomError(ERROR_JOIN)
            if not settings.allow_public_downloads:
                raise WatchRoomError(ERROR_CREDENTIAL)
            try:
                async with SessionLocal() as db:
                    token, record, _ = await _get_accessible_upload(credential, upload_id, db, False)
            except HTTPException as exc:
                raise WatchRoomError(ERROR_CREDENTIAL) from exc
            if record.public_id != room.upload_id or token.download_token != room.download_token:
                raise WatchRoomError(ERROR_CREDENTIAL)
            participant_id, is_host = await manager.join(room, websocket, credential, host_key, upload_id)
        except (WatchRoomError, TimeoutError) as exc:
            await _send_error(websocket, str(exc))
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        if not await manager._send(
            websocket,
            {
                "type": "ready",
                "participant_id": participant_id,
                "role": "host" if is_host else "guest",
                "participant_count": len(room.participants),
                **({"host_key": room.host_key} if is_host else {}),
            },
        ):
            return
        if not await manager._send(websocket, manager.state(room)):
            return
        await manager.broadcast(room, {"type": "participants", "participant_count": len(room.participants)})
        while True:
            try:
                raw = await websocket.receive_text()
                await manager.message_allowed(room, participant_id)
                await manager.touch(room, participant_id)
                message = _parse_message(raw)
                kind = message.get("type")
                if kind == "ping":
                    client_time = message.get("client_time")
                    if not isinstance(client_time, (int, float)) or isinstance(client_time, bool) or not _finite(client_time):
                        raise WatchRoomError(ERROR_PING)
                    if not await manager._send(websocket, {"type": "pong", "client_time": client_time, "server_time": time.time()}):
                        return
                elif kind == "ready":
                    if not await manager._send(websocket, manager.state(room)):
                        return
                else:
                    state = await manager.command(room, participant_id, message)
                    await manager.broadcast(room, state)
            except WatchRoomError as exc:
                await _send_error(websocket, str(exc))
                if exc.args and exc.args[0] == "message_rate_limit":
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                    return
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        if participant_id is not None:
            await manager.remove(room, participant_id)
            if room.room_id in manager.rooms:
                await manager.broadcast(room, {"type": "participants", "participant_count": len(room.participants)})


def _finite(value: float) -> bool:
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False
