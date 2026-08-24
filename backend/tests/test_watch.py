import asyncio
from types import SimpleNamespace
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app.watch import MAX_PARTICIPANTS, ERROR_MESSAGE_RATE_LIMIT, Participant, WatchRoomError, WatchRoomManager


class FakeSocket:
    def __init__(self):
        self.messages = []
        self.closed = False

    async def send_json(self, message):
        self.messages.append(message)

    async def close(self, **_kwargs):
        self.closed = True


class FailingSocket(FakeSocket):
    async def send_json(self, _message):
        raise RuntimeError("send failed")


@pytest.mark.asyncio
async def test_host_commands():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    host_key = room.host_key
    host, is_host, _ = await manager.join(room, FakeSocket(), "download", host_key, "upload")
    guest, guest_is_host, _ = await manager.join(room, FakeSocket(), "download", None, "upload")
    assert is_host and not guest_is_host, "The creator should be host and later participants should be guests"
    state = await manager.command(room, host, {"type": "play", "position": 4})
    assert not state["paused"] and state["version"] == 1, "A host play command should advance the authoritative state"
    with pytest.raises(ValueError, match="Only the host"):
        await manager.command(room, guest, {"type": "pause"})
    with pytest.raises(ValueError, match="Invalid position"):
        await manager.command(room, host, {"type": "seek", "position": float("inf")})


@pytest.mark.asyncio
async def test_reserved_host_slot():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    for _ in range(MAX_PARTICIPANTS - 1):
        await manager.join(room, FakeSocket(), "download", None, "upload")
    with pytest.raises(WatchRoomError, match="full"):
        await manager.join(room, FakeSocket(), "download", None, "upload")
    _, is_host, _ = await manager.join(room, FakeSocket(), "download", room.host_key, "upload")
    assert is_host and room.host_established


@pytest.mark.asyncio
async def test_capacity_failure_unchanged():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    original_key = room.host_key
    for index in range(MAX_PARTICIPANTS):
        room.participants[str(index)] = Participant(FakeSocket(), index)
    with pytest.raises(WatchRoomError, match="full"):
        await manager.join(room, FakeSocket(), "download", original_key, "upload")
    assert room.host_key == original_key and not room.host_established


@pytest.mark.asyncio
async def test_participant_versions():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    host, _, _ = await manager.join(room, FakeSocket(), "download", room.host_key, "upload")
    guest, _, _ = await manager.join(room, FakeSocket(), "download", None, "upload")
    assert room.participant_version == 2
    assert manager.state(room)["participant_version"] == 2
    await manager.remove(room, guest)
    message = await manager.participant_message(room)
    assert message == {"type": "participants", "participant_count": 1, "participant_version": 3}
    await manager.remove(room, host)


@pytest.mark.asyncio
async def test_host_promotion():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    host_key = room.host_key
    host, _, _ = await manager.join(room, FakeSocket(), "download", host_key, "upload")
    guest_socket = FakeSocket()
    guest, _, _ = await manager.join(room, guest_socket, "download", None, "upload")
    await manager.remove(room, host)
    room.host_reconnect_until = 0
    await manager.promote_expired(room)
    assert room.participants[guest].is_host, "The longest-connected guest should become host"
    assert room.host_key != host_key, "Promotion should invalidate the original host key"
    promotion = next(message for message in guest_socket.messages if message["type"] == "promotion")
    assert promotion["host_key"] == room.host_key, "Promotion should deliver the rotated host key"
    assert any(message.get("type") == "host_status" and message.get("status") == "connected" for message in guest_socket.messages)
    assert any(message.get("type") == "state" and message.get("paused") for message in guest_socket.messages)
    with pytest.raises(WatchRoomError, match="Synchronize"):
        await manager.command(room, guest, {"type": "play", "position": 4})
    assert await manager.synced(room, guest, room.version) is None
    with pytest.raises(ValueError, match="host key"):
        await manager.join(room, FakeSocket(), "download", host_key, "upload")
    _, guest_role, _ = await manager.join(room, FakeSocket(), "download", None, "upload")
    assert not guest_role and manager.state(room)["paused"]
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
    guest, guest_is_host, _ = await manager.join(room, FakeSocket(), "download", None, "upload")
    creator, creator_is_host, _ = await manager.join(room, FakeSocket(), "download", room.host_key, "upload")
    assert not guest_is_host and creator_is_host, "A guest must not consume the creator authority"
    await manager.remove(room, creator)
    room.host_reconnect_until = 0
    await manager.promote_expired(room)
    assert room.participants[guest].is_host, "The waiting guest should be promoted when the creator leaves"


@pytest.mark.asyncio
async def test_state_projects_elapsed():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    host, _, _ = await manager.join(room, FakeSocket(), "download", room.host_key, "upload")
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
    participant, _, _ = await manager.join(room, socket, "download", None, "upload")
    await manager.join(room, observer, "download", None, "upload")
    room.participants[participant].last_seen = 0
    await manager.cleanup()
    assert socket.closed
    assert observer.messages[-1]["participant_count"] == 1


@pytest.mark.asyncio
async def test_malformed_messages():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    host, _, _ = await manager.join(room, FakeSocket(), "download", room.host_key, "upload")
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
    participant, _, _ = await manager.join(room, FakeSocket(), "download", None, "upload")
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
    participant, _, _ = await manager.join(room, FakeSocket(), "download", None, "upload")
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
    participant, _, _ = await manager.join(room, FakeSocket(), "download", None, "upload")
    room.participants[participant].message_count = 60
    with pytest.raises(WatchRoomError) as error:
        await manager.message_allowed(room, participant)
    assert error.value.args[0] == ERROR_MESSAGE_RATE_LIMIT


@pytest.mark.asyncio
async def test_host_reconnect_grace():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    creation_key = room.host_key
    host, _, _ = await manager.join(room, FakeSocket(), "download", creation_key, "upload")
    reconnect_key = room.host_key
    await manager.remove(room, host)
    reconnected, is_host, was_reconnected = await manager.join(room, FakeSocket(), "download", reconnect_key, "upload")
    assert is_host and was_reconnected
    assert reconnected in room.participants
    assert room.host_key != reconnect_key


@pytest.mark.asyncio
async def test_sync_barrier():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    host, _, _ = await manager.join(room, FakeSocket(), "download", room.host_key, "upload")
    reconnect_key = room.host_key
    await manager.remove(room, host)
    recovered, is_host, _ = await manager.join(room, FakeSocket(), "download", reconnect_key, "upload")
    with pytest.raises(WatchRoomError, match="Synchronize"):
        await manager.command(room, recovered, {"type": "play", "position": 1})
    assert await manager.synced(room, recovered, room.version - 1)
    assert await manager.synced(room, recovered, room.version) is None
    state = await manager.command(room, recovered, {"type": "play", "position": 1})
    assert is_host and not state["paused"]


@pytest.mark.asyncio
async def test_reconnect_supersedes_host():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    old_socket = FakeSocket()
    old_host, _, _ = await manager.join(room, old_socket, "download", room.host_key, "upload")
    reconnect_key = room.host_key
    new_host, is_host, reconnected = await manager.join(room, FakeSocket(), "download", reconnect_key, "upload")
    assert is_host and reconnected and old_host not in room.participants and not old_socket.closed
    await manager.close_superseded(new_host)
    assert old_socket.closed
    with pytest.raises(WatchRoomError, match="host"):
        await manager.command(room, old_host, {"type": "play", "position": 1})
    await manager.synced(room, new_host, room.version)
    assert room.participants[new_host].is_host


@pytest.mark.asyncio
async def test_superseded_close_async():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    old_socket = FakeSocket()
    await manager.join(room, old_socket, "download", room.host_key, "upload")
    reconnect_key = room.host_key
    new_host, _, _ = await manager.join(room, FakeSocket(), "download", reconnect_key, "upload")
    started, release = asyncio.Event(), asyncio.Event()

    async def delayed_close(_socket):
        started.set()
        await release.wait()

    manager._close_socket = delayed_close
    close_task = asyncio.create_task(manager.close_superseded(new_host))
    await started.wait()
    await manager.synced(room, new_host, room.version)
    state = await manager.command(room, new_host, {"type": "play", "position": 2})
    assert not state["paused"]
    release.set()
    await close_task


@pytest.mark.asyncio
async def test_superseded_cancel_recover():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    await manager.join(room, FakeSocket(), "download", room.host_key, "upload")
    reconnect_key = room.host_key
    new_host, _, _ = await manager.join(room, FakeSocket(), "download", reconnect_key, "upload")
    started, release = asyncio.Event(), asyncio.Event()

    async def delayed_close(_socket):
        started.set()
        await release.wait()

    manager._close_socket = delayed_close
    close_task = asyncio.create_task(manager.close_superseded(new_host))
    await started.wait()
    close_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await close_task
    assert new_host in manager._superseded
    release.set()
    await manager.close()
    assert not manager._superseded


@pytest.mark.asyncio
async def test_cleanup_count_refresh():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    host, _, _ = await manager.join(room, FakeSocket(), "download", room.host_key, "upload")
    failed = FailingSocket()
    await manager.join(room, failed, "download", None, "upload")
    observer = FakeSocket()
    await manager.join(room, observer, "download", None, "upload")
    room.participants[host].last_seen = 0
    await manager.cleanup()
    assert any(message.get("type") == "participants" and message.get("participant_count") == 1 for message in observer.messages)


@pytest.mark.asyncio
async def test_cleanup_revoke_close():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    host_socket = FakeSocket()
    guest_socket = FakeSocket()
    host, _, _ = await manager.join(room, host_socket, "download", room.host_key, "upload")
    await manager.join(room, guest_socket, "download", None, "upload")
    reconnect_key = room.host_key
    room.participants[host].last_seen = 0
    started, release = asyncio.Event(), asyncio.Event()

    async def delayed_close(_socket):
        started.set()
        await release.wait()

    manager._close_socket = delayed_close
    cleanup = asyncio.create_task(manager.cleanup())
    await started.wait()
    assert any(message.get("type") == "state" and message.get("paused") for message in guest_socket.messages)
    recovered, is_host, _ = await manager.join(room, FakeSocket(), "download", reconnect_key, "upload")
    assert is_host and recovered in room.participants
    release.set()
    await cleanup


@pytest.mark.asyncio
async def test_promotion_skips_failure():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    host, _, _ = await manager.join(room, FakeSocket(), "download", room.host_key, "upload")
    failed_socket, winner_socket = FailingSocket(), FakeSocket()
    failed, _, _ = await manager.join(room, failed_socket, "download", None, "upload")
    winner, _, _ = await manager.join(room, winner_socket, "download", None, "upload")
    await manager.remove(room, host)
    room.host_reconnect_until = 0
    await manager.promote_expired(room)
    assert failed not in room.participants and room.participants[winner].is_host
    assert any(message.get("type") == "promotion" for message in winner_socket.messages)


@pytest.mark.asyncio
async def test_promotion_remove_race():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    host, _, _ = await manager.join(room, FakeSocket(), "download", room.host_key, "upload")
    winner_socket = FakeSocket()

    class RemovingSocket(FakeSocket):
        async def send_json(self, _message):
            await manager.remove(room, failed)
            raise RuntimeError("send failed")

    failed, _, _ = await manager.join(room, RemovingSocket(), "download", None, "upload")
    winner, _, _ = await manager.join(room, winner_socket, "download", None, "upload")
    await manager.remove(room, host)
    room.host_reconnect_until = 0
    await manager.promote_expired(room)
    assert failed not in room.participants and room.participants[winner].is_host
    assert any(message.get("type") == "promotion" for message in winner_socket.messages)


@pytest.mark.asyncio
@pytest.mark.parametrize("token_expired", [False, True])
async def test_cleanup_drains_superseded(token_expired):
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    old_socket, new_socket = FakeSocket(), FakeSocket()
    await manager.join(room, old_socket, "download", room.host_key, "upload")
    await manager.join(room, new_socket, "download", room.host_key, "upload")
    if token_expired:
        room.token_expires_at = 0
    else:
        room.last_activity = 0
    await manager.cleanup()
    assert old_socket.closed and new_socket.closed
    assert not manager._superseded and manager.get(room.room_id) is None


@pytest.mark.asyncio
async def test_disconnect_pauses_room():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    host_socket, guest_socket = FakeSocket(), FakeSocket()
    host, _, _ = await manager.join(room, host_socket, "download", room.host_key, "upload")
    await manager.join(room, guest_socket, "download", None, "upload")
    await manager.command(room, host, {"type": "play", "position": 10})
    version = room.version
    await manager.remove(room, host)
    assert room.paused and room.version == version + 1
    assert room.anchor_position >= 10
    assert [message["type"] for message in guest_socket.messages[-2:]] == ["host_status", "state"]
    assert guest_socket.messages[-2]["status"] == "waiting"


@pytest.mark.asyncio
async def test_reconnect_advances_status():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    host_socket, guest_socket, replacement_socket = FakeSocket(), FakeSocket(), FakeSocket()
    host, _, _ = await manager.join(room, host_socket, "download", room.host_key, "upload")
    await manager.join(room, guest_socket, "download", None, "upload")
    reconnect_key = room.host_key
    await manager.remove(room, host)
    waiting_version = room.version
    _, is_host, reconnected = await manager.join(room, replacement_socket, "download", reconnect_key, "upload")
    assert is_host and reconnected and room.version > waiting_version
    await manager.broadcast(room, {"type": "host_status", "status": "connected", "version": room.version})
    await manager.broadcast(room, manager.state(room))
    assert guest_socket.messages[-2]["status"] == "connected"
    assert guest_socket.messages[-2]["version"] > waiting_version


@pytest.mark.asyncio
async def test_guest_join_waiting_status():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    host, _, _ = await manager.join(room, FakeSocket(), "download", room.host_key, "upload")
    await manager.remove(room, host)
    _, is_host, reconnected = await manager.join(room, FakeSocket(), "download", None, "upload")
    waiting_version = await manager.waiting_version(room)
    assert not is_host and not reconnected and waiting_version == room.version


@pytest.mark.asyncio
async def test_stale_cleanup_pauses_room():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    host_socket, guest_socket = FakeSocket(), FakeSocket()
    host, _, _ = await manager.join(room, host_socket, "download", room.host_key, "upload")
    await manager.join(room, guest_socket, "download", None, "upload")
    await manager.command(room, host, {"type": "play", "position": 3})
    room.participants[host].last_seen = 0
    await manager.cleanup()
    assert room.paused
    assert any(message.get("type") == "host_status" and message.get("status") == "waiting" for message in guest_socket.messages)


@pytest.mark.asyncio
async def test_guest_room_survives():
    manager = WatchRoomManager()
    room = await manager.create("download", "upload")
    guest, _, _ = await manager.join(room, FakeSocket(), "download", None, "upload")
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
