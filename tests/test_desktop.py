import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QPushButton, QToolButton
from opensim.desktop import SimulatorWindow
from opensim.workspace import Workspace


def test_desktop_has_real_actions_disabled_roadmap_and_shared_state(tmp_path):
    application = QApplication.instance() or QApplication([])
    workspace = Workspace(tmp_path)
    project = workspace.create_project("Desktop check")
    workspace.show_project(project["id"])
    window = SimulatorWindow(workspace)
    try:
        disabled = {button.text() for button in window.findChildren(QPushButton) if not button.isEnabled()}
        assert {"Thermal analysis", "Contact", "GPU solve"}.issubset(disabled)
        actions = [button for button in window.findChildren(QToolButton) if button.text().startswith("Solve")]
        assert actions and all(button.isEnabled() for button in actions)
        assert window.project_id == project["id"]
        workspace.set_parameters(project["id"], {"load_N": 2500})
        window.refresh()
        assert window.fields["load_N"].value() == 2500
        workspace.show_project(project["id"], "mesh")
        window.refresh()
        assert "MESH" in window.viewport_title.text()
        assert workspace.ui_state()["desktop_connected"]
    finally:
        window.close()
        window.view.setPage(None)
        window.deleteLater()
        application.processEvents()
