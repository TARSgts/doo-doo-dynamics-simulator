"""Optional, asynchronous Discord desktop IPC. No tokens or model data."""
import json
import os
from pathlib import Path
import re
import struct
import time
import uuid

from PySide6.QtCore import QObject, QSettings, QTimer, Signal
from PySide6.QtNetwork import QLocalSocket


DEFAULT_APPLICATION_ID = "1564783884363632670"
# Public app artwork, pinned to the commit that introduced it so every install
# gets the same image without uploading files or needing developer credentials.
PRESENCE_ICON_URL = ("https://raw.githubusercontent.com/TARSgts/doo-doo-dynamics-simulator/"
                     "c8a32b8a9bfb3a081daa805cb4b42b6fea1c5da5/src/opensim/assets/app-icon.png")
MAX_FRAME = 1024 * 1024


def application_id(value):
    value = str(value).strip()
    if not re.fullmatch(r"[0-9]{17,20}", value):
        raise ValueError("Enter the public 17–20 digit Application ID from Discord's Developer Portal, not a token or secret.")
    return value


def presence_settings():
    return QSettings("TARSgts", "DooDooDynamicsSimulator")


def load_presence_preferences(settings=None):
    """Fresh installs share the shipped app identity; preserve explicit opt-outs."""
    if settings is None:
        settings = presence_settings()
    return (settings.value("discord/enabled", True, type=bool),
            settings.value("discord/application_id", DEFAULT_APPLICATION_ID, type=str).strip() or DEFAULT_APPLICATION_ID)


def ipc_endpoints():
    if os.name == "nt":
        return [f"discord-ipc-{index}" for index in range(10)]
    directories = list(dict.fromkeys([os.environ[key] for key in ("XDG_RUNTIME_DIR", "TMPDIR", "TMP", "TEMP")
                                     if os.environ.get(key)] + ["/tmp"]))
    return [str(Path(directory) / f"discord-ipc-{index}") for directory in directories for index in range(10)]


def encode_frame(opcode, payload):
    body = json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return struct.pack("<II", opcode, len(body)) + body


class FrameReader:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        frames = []
        while len(self.buffer) >= 8:
            opcode, length = struct.unpack("<II", self.buffer[:8])
            if length > MAX_FRAME or opcode not in range(5):
                raise ValueError("Invalid Discord IPC frame")
            if len(self.buffer) < 8 + length:
                break
            payload = json.loads(self.buffer[8:8 + length])
            del self.buffer[:8 + length]
            if not isinstance(payload, dict):
                raise ValueError("Invalid Discord IPC payload")
            frames.append((opcode, payload))
        return frames


def activity_for(state, active=None, started=None, has_project=True):
    """Only allowlisted descriptions; never copy project/job strings into presence."""
    study = {"static": "Static structural", "modal": "Modal analysis", "convergence": "Mesh convergence", "thermal": "Steady thermal analysis"}.get(state.get("study"), "Structural simulation")
    if active and active.get("status") in {"queued", "running"}:
        details = {"mesh": "Generating mesh", "solve": "Solving static structural", "modal": "Calculating natural frequencies",
                   "convergence": "Checking mesh convergence", "thermal": "Solving thermal conduction"}.get(active.get("kind"), "Preparing simulation")
        if active["status"] == "queued":
            details = "Waiting for simulation"
    elif not has_project:
        details = "In the project library"
    else:
        details = {"geometry": "Preparing a model", "mesh": "Inspecting mesh", "results": "Viewing displacement and stress",
                   "modal": "Viewing vibration modes", "thermal": "Viewing temperature and heat flow"}.get(state.get("view"), "Working on a simulation")
    return {"type": 0, "details": details, "state": study, "timestamps": {"start": int(started or time.time())},
            "assets": {"large_image": PRESENCE_ICON_URL, "large_text": "Doo Doo Dynamics Simulator"}}


class DiscordPresence(QObject):
    statusChanged = Signal(str)

    def __init__(self, parent=None, endpoints=None):
        super().__init__(parent)
        self.enabled = False
        self.client_id = ""
        self.status = "Off"
        self.socket = None
        self.ready = False
        self.activity = None
        self.last_activity = None
        self.last_sent = 0
        self.pending_nonce = None
        self.endpoints = endpoints if endpoints is not None else ipc_endpoints()
        self.endpoint_index = 0
        self.retry = QTimer(self)
        self.retry.setSingleShot(True)
        self.retry.timeout.connect(self._connect)
        self.deadline = QTimer(self)
        self.deadline.setSingleShot(True)
        self.deadline.timeout.connect(lambda: self._failed("Discord did not respond; retrying"))
        self.update_timer = QTimer(self)
        self.update_timer.setSingleShot(True)
        self.update_timer.timeout.connect(self._publish)

    def _status(self, text):
        self.status = text
        self.statusChanged.emit(text)

    def configure(self, enabled, client_id):
        client_id = application_id(client_id) if enabled else str(client_id).strip()
        if (self.enabled, self.client_id) == (enabled, client_id):
            return
        self.stop()
        self.enabled, self.client_id = bool(enabled), client_id
        self.endpoint_index = 0
        if enabled:
            self._connect()

    def _connect(self):
        if not self.enabled or self.socket is not None or not self.endpoints:
            return
        self.reader = FrameReader()
        socket = QLocalSocket(self)
        self.socket = socket
        socket.setReadBufferSize(MAX_FRAME + 8)
        socket.connected.connect(lambda: self._connected(socket))
        socket.readyRead.connect(lambda: self._read(socket))
        socket.errorOccurred.connect(lambda error: self._failed("Waiting for Discord desktop", socket))
        socket.disconnected.connect(lambda: self._failed("Discord disconnected; retrying", socket))
        self._status("Connecting to Discord desktop…")
        self.deadline.start(3000)
        socket.connectToServer(self.endpoints[self.endpoint_index])

    def _connected(self, socket):
        if socket is self.socket:
            self._send(0, {"v": 1, "client_id": self.client_id})

    def _send(self, opcode, payload):
        if self.socket is not None:
            self.socket.write(encode_frame(opcode, payload))
            self.socket.flush()

    def _read(self, socket):
        if socket is not self.socket:
            return
        try:
            for opcode, payload in self.reader.feed(bytes(socket.readAll())):
                if opcode == 3:
                    self._send(4, payload)
                elif opcode == 2 or payload.get("evt") == "ERROR":
                    self._failed("Discord rejected the connection or activity; check the Application ID", socket, backoff=True)
                    return
                elif opcode == 1 and payload.get("evt") == "READY":
                    self.ready = True
                    self.deadline.stop()
                    self._status("Connected; preparing activity")
                    self._publish()
                elif opcode == 1 and payload.get("cmd") == "SET_ACTIVITY" and payload.get("nonce") == self.pending_nonce:
                    self.pending_nonce = None
                    self.deadline.stop()
                    self._status("Connected — activity sent to Discord")
        except (ValueError, UnicodeError, struct.error):
            self._failed("Invalid response from Discord; retrying", socket, backoff=True)

    def _failed(self, message, socket=None, backoff=False):
        if self.socket is None or (socket is not None and socket is not self.socket):
            return
        old, self.socket = self.socket, None
        old.abort()
        old.deleteLater()
        self.ready = False
        self.pending_nonce = None
        self.last_activity = None
        self.deadline.stop()
        self.update_timer.stop()
        self.endpoint_index = (self.endpoint_index + 1) % len(self.endpoints)
        if self.enabled:
            self._status(message)
            self.retry.start(30000 if backoff or self.endpoint_index == 0 else 20)

    def set_activity(self, activity):
        self.activity = activity
        self._publish()

    def _publish(self):
        if not self.enabled or not self.ready or self.activity is None or self.activity == self.last_activity:
            return
        remaining = 15 - (time.monotonic() - self.last_sent)
        if self.last_activity is not None and remaining > 0:
            self.update_timer.start(max(1, int(remaining * 1000)))
            return
        # One outstanding request at a time; the deadline also covers lost acknowledgements.
        if self.pending_nonce is not None:
            self.update_timer.start(1000)
            return
        self.pending_nonce = uuid.uuid4().hex
        self._send(1, {"cmd": "SET_ACTIVITY", "args": {"pid": os.getpid(), "activity": self.activity}, "nonce": self.pending_nonce})
        self.last_activity = self.activity.copy()
        self.last_sent = time.monotonic()
        self.deadline.start(5000)

    def stop(self):
        self.enabled = False
        self.retry.stop()
        self.deadline.stop()
        self.update_timer.stop()
        if self.socket is not None:
            if self.ready:
                self._send(1, {"cmd": "SET_ACTIVITY", "args": {"pid": os.getpid(), "activity": None}, "nonce": uuid.uuid4().hex})
            socket, self.socket = self.socket, None
            socket.disconnectFromServer()
            socket.deleteLater()
        self.ready = False
        self.pending_nonce = None
        self.last_activity = None
        self._status("Off")
