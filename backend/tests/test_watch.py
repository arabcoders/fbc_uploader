import asyncio
from types import SimpleNamespace
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app.watch import ERROR_MESSAGE_RATE_LIMIT, WatchRoomError, WatchRoomManager


class FakeSocket:
    def __init__(self):
        self.messages = []
        self.closed = False

    async def send_json(self, message):
        self.messages.append(message)

    async def close(self, **_kwargs):
        self.closed = True


@pytest.mark.asyncio
async def test_host_commands():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    host_key = room.host_key
    host, is_host = await manager.join(room, FakeSocket(), "download", host_key, "upload")
    guest, guest_is_host = await manager.join(room, FakeSocket(), "download", None, "upload")
    assert is_host and not guest_is_host, "The creator should be host and later participants should be guests"
    state = await manager.command(room, host, {"type": "play", "position": 4})
    assert not state["paused"] and state["version"] == 1, "A host play command should advance the authoritative state"
    with pytest.raises(ValueError, match="Only the host"):
        await manager.command(room, guest, {"type": "pause"})
    with pytest.raises(ValueError, match="Invalid position"):
        await manager.command(room, host, {"type": "seek", "position": float("inf")})


@pytest.mark.asyncio
async def test_host_promotion():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    host_key = room.host_key
    host, _ = await manager.join(room, FakeSocket(), "download", host_key, "upload")
    guest_socket = FakeSocket()
    guest, _ = await manager.join(room, guest_socket, "download", None, "upload")
    await manager.remove(room, host)
    room.host_reconnect_until = 0
    await manager.promote_expired(room)
    assert room.participants[guest].is_host, "The longest-connected guest should become host"
    assert room.host_key != host_key, "Promotion should invalidate the original host key"
    assert guest_socket.messages[-1]["host_key"] == room.host_key, "Promotion should deliver the rotated host key"
    await manager.remove(room, guest)
    room.last_activity = 0
    await manager.cleanup()
    assert manager.get(room.room_id) is None, "An empty room should be removed"


@pytest.mark.asyncio
async def test_join_auth():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    with pytest.raises(ValueError, match="credential"):
        await manager.join(room, FakeSocket(), "wrong", None, "upload")


@pytest.mark.asyncio
async def test_guest_waits():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    guest, guest_is_host = await manager.join(room, FakeSocket(), "download", None, "upload")
    creator, creator_is_host = await manager.join(room, FakeSocket(), "download", room.host_key, "upload")
    assert not guest_is_host and creator_is_host, "A guest must not consume the creator authority"
    await manager.remove(room, creator)
    room.host_reconnect_until = 0
    await manager.promote_expired(room)
    assert room.participants[guest].is_host, "The waiting guest should be promoted when the creator leaves"


@pytest.mark.asyncio
async def test_state_projects_elapsed():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    host, _ = await manager.join(room, FakeSocket(), "download", room.host_key, "upload")
    await manager.command(room, host, {"type": "play", "position": 10})
    room.anchor_server_time -= 2
    state = manager.state(room)
    assert state["anchor_position"] >= 11.9, "A late state must include elapsed playback"


@pytest.mark.asyncio
async def test_upload_mismatch():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    with pytest.raises(ValueError, match="upload"):
        await manager.join(room, FakeSocket(), "download", None, "other")


@pytest.mark.asyncio
async def test_token_room_cap():
    manager = WatchRoomManager()
    for _ in range(3):
        await manager.create("download", "upload")
    with pytest.raises(ValueError, match="capacity"):
        await manager.create("download", "upload")


@pytest.mark.asyncio
async def test_cleanup_stale_count():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    socket = FakeSocket()
    observer = FakeSocket()
    participant, _ = await manager.join(room, socket, "download", None, "upload")
    await manager.join(room, observer, "download", None, "upload")
    room.participants[participant].last_seen = 0
    await manager.cleanup()
    assert socket.closed
    assert observer.messages[-1]["participant_count"] == 1


@pytest.mark.asyncio
async def test_malformed_messages():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    host, _ = await manager.join(room, FakeSocket(), "download", room.host_key, "upload")
    with pytest.raises(ValueError, match="command"):
        await manager.command(room, host, {"type": []})
    with pytest.raises(ValueError, match="position"):
        await manager.command(room, host, {"type": "seek", "position": 10**1000})


@pytest.mark.asyncio
async def test_room_invalidation():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    socket = FakeSocket()
    await manager.join(room, socket, "download", None, "upload")
    await manager.invalidate(download_token="download")
    assert manager.get(room.room_id) is None
    assert socket.closed


@pytest.mark.asyncio
async def test_removed_room_rejects():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    participant, _ = await manager.join(room, FakeSocket(), "download", None, "upload")
    await manager.invalidate(download_token="download")
    with pytest.raises(WatchRoomError, match="not found"):
        await manager.message_allowed(room, participant)
    with pytest.raises(WatchRoomError, match="not found"):
        await manager.touch(room, participant)
    with pytest.raises(WatchRoomError, match="not found"):
        await manager.command(room, participant, {"type": "pause", "position": 0})


@pytest.mark.asyncio
async def test_invalidation_close_race():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    participant, _ = await manager.join(room, FakeSocket(), "download", None, "upload")
    close_started = asyncio.Event()
    release_close = asyncio.Event()

    async def close_socket(_socket):
        close_started.set()
        await release_close.wait()

    manager._close_socket = close_socket
    invalidation = asyncio.create_task(manager.invalidate(download_token="download"))
    await close_started.wait()
    with pytest.raises(WatchRoomError, match="not found"):
        await manager.message_allowed(room, participant)
    release_close.set()
    await invalidation


@pytest.mark.asyncio
async def test_expiry_shortens():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload", datetime.now(UTC) + timedelta(hours=1))
    expires_at = datetime.now(UTC) + timedelta(minutes=5)
    await manager.update_expiry("download", expires_at)
    assert room.token_expires_at == pytest.approx(expires_at.timestamp())


@pytest.mark.asyncio
async def test_expiry_extends():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload", datetime.now(UTC) + timedelta(minutes=5))
    expires_at = datetime.now(UTC) + timedelta(hours=1)
    await manager.update_expiry("download", expires_at)
    assert room.token_expires_at == pytest.approx(expires_at.timestamp())


@pytest.mark.asyncio
async def test_expiry_invalidates():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload", datetime.now(UTC) + timedelta(hours=1))
    socket = FakeSocket()
    await manager.join(room, socket, "download", None, "upload")
    await manager.update_expiry("download", datetime.now(UTC) - timedelta(seconds=1))
    assert manager.get(room.room_id) is None
    assert socket.closed


@pytest.mark.asyncio
async def test_room_expiry():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload", datetime.now(UTC) + timedelta(seconds=1))
    socket = FakeSocket()
    await manager.join(room, socket, "download", None, "upload")
    room.token_expires_at = 0
    await manager.cleanup()
    assert manager.get(room.room_id) is None
    assert socket.closed


@pytest.mark.asyncio
async def test_discard_room():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    assert await manager.discard(room.room_id, "wrong") is False
    assert await manager.discard(room.room_id, room.host_key) is True
    assert manager.get(room.room_id) is None


@pytest.mark.asyncio
async def test_message_limit_error():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    participant, _ = await manager.join(room, FakeSocket(), "download", None, "upload")
    room.participants[participant].message_count = 60
    with pytest.raises(WatchRoomError) as error:
        await manager.message_allowed(room, participant)
    assert error.value.args[0] == ERROR_MESSAGE_RATE_LIMIT


@pytest.mark.asyncio
async def test_host_reconnect_grace():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    creation_key = room.host_key
    host, _ = await manager.join(room, FakeSocket(), "download", creation_key, "upload")
    reconnect_key = room.host_key
    await manager.remove(room, host)
    reconnected, is_host = await manager.join(room, FakeSocket(), "download", reconnect_key, "upload")
    assert is_host
    assert reconnected in room.participants
    assert room.host_key != reconnect_key


@pytest.mark.asyncio
async def test_guest_room_survives():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    guest, _ = await manager.join(room, FakeSocket(), "download", None, "upload")
    await manager.remove(room, guest)
    assert manager.get(room.room_id) is room


def test_watch_create_route(monkeypatch):
    from backend.app import main
    from backend.app.routers import watch

    monkeypatch.setattr(watch.settings, "allow_public_downloads", True)
    token = SimpleNamespace(download_token="download", expires_at=datetime.now(UTC) + timedelta(hours=1))
    record = SimpleNamespace(public_id="upload", mimetype="video/mp4")

    async def accessible(*_args):
        return token, record, "/tmp/video.mp4"

    monkeypatch.setattr(watch, "_get_accessible_upload", accessible)
    with TestClient(main.app) as client:
        response = client.post("/api/tokens/download/uploads/upload/watch")
    assert response.status_code == 200, "Playable public upload should create a room"
    assert response.json()["room_id"], "Creation should return a room ID"


def test_watch_discard_route(monkeypatch):
    from backend.app import main
    from backend.app.routers import watch

    monkeypatch.setattr(watch.settings, "allow_public_downloads", True)
    token = SimpleNamespace(download_token="download", expires_at=datetime.now(UTC) + timedelta(hours=1))
    record = SimpleNamespace(public_id="upload", mimetype="video/mp4")

    async def accessible(*_args):
        return token, record, "/tmp/video.mp4"

    monkeypatch.setattr(watch, "_get_accessible_upload", accessible)
    with TestClient(main.app) as client:
        created = client.post("/api/tokens/download/uploads/upload/watch").json()
        response = client.delete(f"/api/watch/{created['room_id']}", headers={"X-Watch-Host-Key": created["host_key"]})
    assert response.status_code == 204


def test_watch_public_gate(monkeypatch):
    from backend.app import main
    from backend.app.routers import watch

    monkeypatch.setattr(watch.settings, "allow_public_downloads", False)
    with TestClient(main.app) as client:
        response = client.post("/api/tokens/download/uploads/upload/watch")
    assert response.status_code == 403, "Room creation must require public downloads"


def test_watch_rejects_nonmedia(monkeypatch):
    from backend.app import main
    from backend.app.routers import watch

    monkeypatch.setattr(watch.settings, "allow_public_downloads", True)

    async def accessible(*_args):
        return SimpleNamespace(download_token="download"), SimpleNamespace(public_id="upload", mimetype="text/plain"), "/tmp/file.txt"

    monkeypatch.setattr(watch, "_get_accessible_upload", accessible)
    with TestClient(main.app) as client:
        response = client.post("/api/tokens/download/uploads/upload/watch")
    assert response.status_code == 415, "Rooms must only accept playable media"


def test_watch_socket_protocol(monkeypatch):
    from backend.app import main
    from backend.app.routers import watch

    monkeypatch.setattr(watch.settings, "allow_public_downloads", True)
    token = SimpleNamespace(download_token="download", expires_at=datetime.now(UTC) + timedelta(hours=1))
    record = SimpleNamespace(public_id="upload", mimetype="audio/mpeg")

    async def accessible(*_args):
        return token, record, "/tmp/audio.mp3"

    monkeypatch.setattr(watch, "_get_accessible_upload", accessible)
    with TestClient(main.app) as client:
        created = client.post("/api/tokens/download/uploads/upload/watch").json()
        with client.websocket_connect(f"/api/watch/{created['room_id']}/ws") as host:
            host.send_json({"type": "join", "download_token": "download", "upload_id": "upload", "host_key": created["host_key"]})
            ready = host.receive_json()
            assert ready["role"] == "host", "Valid creator key should establish host"
            assert ready["host_key"] != created["host_key"], "Host join should rotate the reconnect key"
            host.receive_json()
            host.send_json({"type": "play", "position": 12})
            messages = [host.receive_json() for _ in range(2)]
            state = next(message for message in messages if message.get("type") == "state")
            assert state["anchor_position"] == pytest.approx(12, abs=0.1), "Host position should anchor state"
