from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout,
                               QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout)

from opensim.discord_presence import DEFAULT_APPLICATION_ID, application_id, presence_settings


class DiscordPresenceDialog(QDialog):
    def __init__(self, presence, parent=None):
        super().__init__(parent)
        self.presence = presence
        self.setWindowTitle("Discord Rich Presence")
        self.resize(540, 310)
        layout = QVBoxLayout(self)
        description = QLabel("Let Discord show that you're using Doo Doo Dynamics Simulator, with basic activity such as meshing, solving or viewing results. Project names, file paths, geometry and numerical results are never included.")
        description.setWordWrap(True)
        layout.addWidget(description)
        self.enabled = QCheckBox("Show simulator activity on Discord")
        self.enabled.setToolTip("Share basic simulator activity with the Discord desktop app. Turn off to clear the simulator's Rich Presence.")
        self.enabled.setChecked(presence.enabled)
        layout.addWidget(self.enabled)
        form = QFormLayout()
        self.client_id = QLineEdit(presence.client_id or DEFAULT_APPLICATION_ID)
        self.client_id.setToolTip("Public Application ID from Discord's Developer Portal. The simulator's official ID is prefilled; no token, password or client secret is needed.")
        form.addRow("Application ID", self.client_id)
        layout.addLayout(form)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        note = QLabel("Keep Discord's desktop app open and enable activity sharing in Discord. The displayed application name and icon come from the Discord application. Changes may take a few seconds to appear.")
        note.setWordWrap(True)
        layout.addWidget(note)
        portal = QPushButton("Open Discord Developer Portal")
        portal.setToolTip("Open Discord's application settings to manage the application's name and icon.")
        portal.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://discord.com/developers/applications")))
        layout.addWidget(portal)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_status)
        self.timer.start(500)
        self.update_status()

    def update_status(self):
        self.status.setText("Status: " + self.presence.status)

    def apply(self):
        try:
            value = self.client_id.text().strip()
            if self.enabled.isChecked():
                value = application_id(value)
            self.presence.configure(self.enabled.isChecked(), value)
            settings = presence_settings()
            settings.setValue("discord/application_id", value)
            settings.setValue("discord/enabled", self.enabled.isChecked())
            settings.sync()
            self.update_status()
        except ValueError as error:
            QMessageBox.warning(self, "Discord Rich Presence", str(error))
