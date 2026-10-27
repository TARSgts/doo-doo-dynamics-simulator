import json
import os
import struct
import time
import uuid

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QSettings
from PySide6.QtNetwork import QLocalServer
from PySide6.QtWidgets import QApplication, QMessageBox
from opensim.discord_presence import (DEFAULT_APPLICATION_ID, DiscordPresence, FrameReader,
                                      activity_for, application_id, encode_frame, load_presence_preferences)


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def until(app, predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.002)
    assert predicate()


@pytest.fixture
def ipc(app):
    server = QLocalServer()
    name = "doo-doo-discord-test-" + uuid.uuid4().hex
    assert server.listen(name)
    presence = DiscordPresence(endpoints=[name])
    presence.set_activity(activity_for({"study": "static", "view": "geometry"}, started=100))
    presence.configure(True, DEFAULT_APPLICATION_ID)
    until(app, server.hasPendingConnections)
    peer = server.nextPendingConnection()
    until(app, lambda: peer.bytesAvailable() > 0)
    reader = FrameReader()
    handshake = reader.feed(bytes(peer.readAll()))
    assert handshake == [(0, {"v": 1, "client_id": DEFAULT_APPLICATION_ID})]
    try:
        yield presence, peer, reader
    finally:
        presence.stop()
        app.processEvents()
        peer.abort()
        peer.deleteLater()
        server.close()
        app.processEvents()


def receive(app, peer, reader):
    until(app, lambda: peer.bytesAvailable() > 0)
    frames = []
    until(app, lambda: bool(frames.extend(reader.feed(bytes(peer.readAll()))) or frames))
    return frames


def ready(app, presence, peer, reader):
    frame = encode_frame(1, {"cmd": "DISPATCH", "evt": "READY", "data": {}})
    peer.write(frame[:5])
    peer.flush()
    app.processEvents()
    assert not presence.ready
    peer.write(frame[5:])
    peer.flush()
    message = receive(app, peer, reader)[0][1]
    assert message["cmd"] == "SET_ACTIVITY"
    assert message["args"]["pid"] == os.getpid()
    peer.write(encode_frame(1, {"cmd": "SET_ACTIVITY", "nonce": message["nonce"], "data": {}}))
    peer.flush()
    until(app, lambda: presence.pending_nonce is None)
    assert presence.status == "Connected — activity sent to Discord"
    return message


def test_frames_handle_fragmentation_coalescing_and_invalid_input():
    frame = encode_frame(1, {"evt": "READY"})
    reader = FrameReader()
    assert reader.feed(frame[:3]) == []
    assert reader.feed(frame[3:] + encode_frame(3, {"ping": 1})) == [(1, {"evt": "READY"}), (3, {"ping": 1})]
    for data in (struct.pack("<II", 1, 2**25), struct.pack("<II", 9, 0), struct.pack("<II", 1, 2) + b"[]",
                 struct.pack("<II", 1, 1) + b"{"):
        with pytest.raises(ValueError):
            FrameReader().feed(data)


@pytest.mark.parametrize("value", ["bot.secret.token", "123", "", "１２３４５６７８９０１２３４５６７", "123456789012345678901"])
def test_application_id_rejects_secrets_and_invalid_ids(value):
    with pytest.raises(ValueError, match="Application ID"):
        application_id(value)


def test_activity_has_no_project_paths_names_or_results():
    state = {"study": "modal", "view": "results", "project_name": "secret design", "path": "private.step"}
    job = {"status": "running", "kind": "modal", "project_id": "secret", "result": {"stress": 123}}
    activity = activity_for(state, job, 100)
    assert activity["details"] == "Calculating natural frequencies"
    assert activity["timestamps"]["start"] == 100
    assert "secret" not in json.dumps(activity) and "private" not in json.dumps(activity)
    assert "library" in activity_for(state, started=100, has_project=False)["details"]


def test_fresh_download_uses_shared_id_and_starts_enabled(tmp_path):
    settings = QSettings(str(tmp_path / "fresh.ini"), QSettings.Format.IniFormat)
    assert load_presence_preferences(settings) == (True, DEFAULT_APPLICATION_ID)
    assert settings.allKeys() == []  # Merely reading defaults does not write preferences.


def test_desktop_starts_presence_for_fresh_user_and_clears_on_close(app, tmp_path):
    from opensim.desktop import SimulatorWindow
    from opensim.workspace import Workspace
    window = SimulatorWindow(Workspace(tmp_path / "workspace"))
    try:
        assert window.discord.enabled
        assert window.discord.client_id == DEFAULT_APPLICATION_ID
        assert window.discord.activity["details"] == "In the project library"
    finally:
        window.close()
        assert not window.discord.enabled
        window.view.setPage(None)
        window.deleteLater()
        app.processEvents()


def test_saved_opt_out_and_custom_id_survive_updates(tmp_path):
    path = str(tmp_path / "existing.ini")
    settings = QSettings(path, QSettings.Format.IniFormat)
    settings.setValue("discord/enabled", False)
    settings.setValue("discord/application_id", "123456789012345678")
    settings.sync()
    reopened = QSettings(path, QSettings.Format.IniFormat)
    assert load_presence_preferences(reopened) == (False, "123456789012345678")
    reopened.setValue("discord/application_id", "")
    assert load_presence_preferences(reopened) == (False, DEFAULT_APPLICATION_ID)


def test_local_ipc_handshake_activity_ack_ping_throttle_and_clear(app, ipc):
    presence, peer, reader = ipc
    message = ready(app, presence, peer, reader)
    peer.write(encode_frame(3, {"nonce": "ping-test"}))
    peer.flush()
    assert receive(app, peer, reader) == [(4, {"nonce": "ping-test"})]
    presence.set_activity(message["args"]["activity"])
    app.processEvents()
    assert peer.bytesAvailable() == 0
    presence.set_activity(activity_for({"study": "static", "view": "results"}, started=100))
    assert presence.update_timer.isActive()
    assert peer.bytesAvailable() == 0
    presence.last_sent -= 16
    presence._publish()
    update = receive(app, peer, reader)[0][1]
    assert update["args"]["activity"]["details"] == "Viewing displacement and stress"
    presence.stop()
    clear = receive(app, peer, reader)[0][1]
    assert clear["args"]["activity"] is None
    assert presence.status == "Off" and not presence.retry.isActive()


def test_disconnected_discord_reconnects_and_republishes(app, ipc):
    presence, peer, reader = ipc
    ready(app, presence, peer, reader)
    peer.abort()
    until(app, lambda: presence.retry.isActive())
    assert not presence.ready and presence.socket is None
    assert presence.retry.remainingTime() > 20000


def test_rejection_and_handshake_timeout_back_off_without_popups(app, ipc):
    presence, peer, _ = ipc
    peer.write(encode_frame(1, {"evt": "ERROR", "data": {"message": "bad id"}}))
    peer.flush()
    until(app, lambda: presence.retry.isActive())
    assert "Application ID" in presence.status
    presence.retry.stop()
    presence._connect()
    presence.deadline.timeout.emit()
    assert presence.socket is None and presence.retry.isActive()


def test_no_discord_is_optional_and_disabling_stops_retries(app):
    presence = DiscordPresence(endpoints=["missing-discord-" + uuid.uuid4().hex])
    presence.configure(True, DEFAULT_APPLICATION_ID)
    until(app, lambda: presence.retry.isActive())
    assert "Discord" in presence.status
    presence.configure(False, DEFAULT_APPLICATION_ID)
    assert not presence.retry.isActive() and presence.socket is None


def test_settings_apply_persist_and_reject_bad_ids(app, tmp_path, monkeypatch):
    import opensim.discord_dialog as module
    settings = QSettings(str(tmp_path / "discord.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr(module, "presence_settings", lambda: settings)
    presence = DiscordPresence(endpoints=[])
    dialog = module.DiscordPresenceDialog(presence)
    assert dialog.advanced.isHidden()
    errors = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: errors.append(args[-1]))
    try:
        dialog.enabled.setChecked(True)
        dialog.client_id.setText("not a public id")
        dialog.apply()
        assert errors and not presence.enabled
        dialog.client_id.setText(DEFAULT_APPLICATION_ID)
        dialog.apply()
        assert presence.enabled and settings.value("discord/enabled", type=bool)
        assert settings.value("discord/application_id") == DEFAULT_APPLICATION_ID
        dialog.enabled.setChecked(False)
        dialog.apply()
        assert not presence.enabled and not settings.value("discord/enabled", type=bool)
    finally:
        presence.stop()
        dialog.close()
