import argparse
from pathlib import Path
import sys
import time

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QProgressBar, QSizePolicy, QWidget

from opensim.workspace import Workspace
from opensim.app_identity import ICON_PATH, set_process_identity
from opensim.discord_presence import DiscordPresence, load_presence_preferences
from opensim.desktop_cfd import CFDStudyMixin


from opensim.ui.commands import CommandsMixin
from opensim.ui.layout import LayoutMixin
from opensim.ui.projects import ProjectsMixin
from opensim.ui.study_panel import StudyPanelMixin
from opensim.ui.reports import ReportsMixin
from opensim.ui.selection import SelectionMixin
from opensim.ui.viewport import ViewportMixin
from opensim.ui.presentation import PresentationMixin
from opensim.ui.state import StateMixin
from opensim.ui.study_tree import StudyTreeMixin
from opensim.ui.styles import STYLE, DARK_STYLE, MIDNIGHT_STYLE
from opensim.ui.widgets import ScrollSafeDoubleSpinBox, ScrollSafeSpinBox, forward_wheel_to_panel


class SimulatorWindow(CommandsMixin,LayoutMixin,ProjectsMixin,StudyPanelMixin,ReportsMixin,SelectionMixin,ViewportMixin,PresentationMixin,StateMixin,StudyTreeMixin,CFDStudyMixin,QMainWindow):
    def __init__(self, workspace: Workspace):
        set_process_identity()
        super().__init__()
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        QApplication.instance().setWindowIcon(self.windowIcon())
        self.workspace = workspace
        self.project_id = None
        self.loaded_view = None
        self.tree_signature = None
        self.project_revision = None
        self.dirty = False
        self.theme = None
        self.language = None
        self.presentation_text = {}
        self.analysis_buttons = []
        self.force_pick_buttons = []
        self.project_actions = []
        self.stop_buttons = []
        self.opened_at = time.time()
        self.discord = DiscordPresence(self)
        try:
            self.discord.configure(*load_presence_preferences())
        except ValueError:
            self.discord._status("Invalid Application ID — open Discord Rich Presence settings")
        QApplication.instance().aboutToQuit.connect(self.discord.stop)
        self.gif_export = None
        self.gif_timer = QTimer(self)
        self.gif_timer.setInterval(150)
        self.gif_timer.timeout.connect(self.poll_gif_export)
        self.shown_convergence = set()
        self.reference_dialogs = {}
        self.file_dialogs = []
        self.plot_dialogs = {}
        self.result_plot_buttons = []
        self.face_pick_session = None
        self.panel_context = None
        self.selection_preview = None
        self.setWindowTitle("Doo Doo Dynamics Simulator — Structural Workbench")
        self.setMinimumSize(1100, 720)
        available = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1520, available.width() - 40), min(980, available.height() - 50))
        self.setStyleSheet(STYLE)
        self.build_menu()
        self.build_center()
        self.build_outline()
        self.build_toolbox()
        self.build_logs()
        self.install_hover_help()
        self.status_label = QLabel("Ready")
        self.status_label.setMinimumWidth(0)
        self.status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.statusBar().addWidget(self.status_label, 1)
        self.progress_panel = QWidget()
        progress_row = QHBoxLayout(self.progress_panel)
        progress_row.setContentsMargins(0, 0, 8, 0)
        progress_row.setSpacing(6)
        self.progress_label = QLabel("No active job")
        self.progress_label.setMinimumWidth(0)
        self.progress_label.setMaximumWidth(260)
        self.progress_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        progress_row.addWidget(self.progress_label, 1)
        self.job_progress = QProgressBar()
        self.job_progress.setAccessibleName("Simulation job progress")
        self.job_progress.setFixedWidth(150)
        self.job_progress.setFixedHeight(18)
        self.job_progress.setRange(0, 100)
        self.job_progress.setValue(0)
        self.job_progress.setTextVisible(False)
        progress_row.addWidget(self.job_progress)
        self.stop_button = self.make_stop_button()
        self.stop_button.setObjectName("StopComputing")
        progress_row.addWidget(self.stop_button)
        self.progress_panel.setMinimumWidth(400)
        self.progress_panel.setMaximumWidth(560)
        self.statusBar().addPermanentWidget(self.progress_panel, 1)
        self.units_label = QLabel("SI units  ·  CalculiX 2.23  ·  Local MCP workspace")
        self.statusBar().addPermanentWidget(self.units_label)
        self.apply_theme()
        self.timer = QTimer(self)
        self.timer.timeout.connect(lambda:self.refresh())
        self.timer.start(700)
        self.refresh()


    def show_discord_settings(self):
        from opensim.discord_dialog import DiscordPresenceDialog
        dialog = DiscordPresenceDialog(self.discord, self)
        dialog.exec()
        dialog.deleteLater()

    def closeEvent(self, event):
        self.discord.stop()
        super().closeEvent(event)


    def safe(self, callback):
        try:
            callback()
            self.refresh()
        except Exception as error:
            self.status_label.setText(str(error))
            QMessageBox.warning(self, "Simulation action", str(error))

    def require_project(self):
        if not self.project_id:
            raise ValueError("Create or select a project first")
        return self.project_id

    def save_before_project_change(self):
        if self.project_id and self.dirty:
            self.save_parameters()


    def stop_computing(self, confirm=True):
        job = self.workspace.active_job(self.require_project())
        if job is None:
            raise ValueError("Nothing is computing for this project")
        if confirm:
            answer = QMessageBox.question(
                self, "Stop computing",
                f"Stop this {job['kind']} job?\n\nThe solver is ended right away and this run produces no results. "
                "Your settings stay as they are, so you can change them and start again.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.workspace.cancel_job(job["id"])
        self.status_label.setText(f"Stopped {job['kind']} job {job['id'][:8]}")


    def show_mcp(self):
        QMessageBox.information(self, "Local MCP automation",
                                "Local stdio MCP tools share this desktop workspace, including thermal analysis.\n\n"
                                "Create/import projects, set inputs, mesh, solve, inspect jobs/results and select views.\n\n"
                                "Workspace: " + str(self.workspace.root) + "\n\n"
                                "Server: python -m opensim.mcp_server\nSee docs/DESKTOP_AND_MCP.md for client setup.")


def main():
    parser = argparse.ArgumentParser(description="Doo Doo Dynamics Simulator desktop workbench")
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--screenshot", type=Path)
    parser.add_argument("--exit-after", type=int)
    arguments = parser.parse_args()
    application = QApplication(sys.argv[:1])
    application.setApplicationName("Doo Doo Dynamics Simulator")
    application.setFont(QFont("Segoe UI", 10))
    window = SimulatorWindow(Workspace(arguments.workspace))
    window.show()
    if arguments.screenshot:
        def capture():
            arguments.screenshot.parent.mkdir(parents=True, exist_ok=True)
            window.grab().save(str(arguments.screenshot))
        QTimer.singleShot(3500, capture)
    if arguments.exit_after:
        QTimer.singleShot(arguments.exit_after, application.quit)
    sys.exit(application.exec())


if __name__ == "__main__":
    main()
