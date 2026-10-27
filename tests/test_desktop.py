import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QPushButton, QToolButton
from opensim.desktop import SimulatorWindow
from opensim.workspace import Workspace


def test_reference_report_starts_at_top_and_expands_without_changing_model(tmp_path):
    from PySide6.QtWidgets import QLabel
    from PySide6.QtWebEngineWidgets import QWebEngineView
    application = QApplication.instance() or QApplication([])
    workspace = Workspace(tmp_path)
    project = workspace.create_project("Preserved model")
    workspace.show_project(project["id"])
    before = workspace.get_project(project["id"])
    window = SimulatorWindow(workspace)
    try:
        for benchmark in ("timoshenko", "hole"):
            dialog = window.show_reference_report(benchmark)
            notice = dialog.findChild(QLabel, "ReferenceNotice")
            content = dialog.findChild(QWebEngineView, "ReferenceContent")
            for width, height in ((1250, 850), (800, 600), (640, 420)):
                dialog.resize(width, height)
                dialog.layout().activate()
                application.processEvents()
                assert notice.height() < 65
                assert content.y() < 85
                assert content.height() > dialog.height() * 0.65
            dialog.close()
            assert window.show_reference_report(benchmark) is dialog
            assert content.y() < 85
            dialog.close()
        assert workspace.get_project(project["id"]) == before
        assert workspace.ui_state()["project_id"] == project["id"]
    finally:
        for dialog in window.reference_dialogs.values():
            dialog.findChild(QWebEngineView).setPage(None)
            dialog.close()
        window.close()
        window.view.setPage(None)
        window.deleteLater()
        application.processEvents()


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
        modal_actions = [button for button in window.findChildren(QPushButton) if button.text() == "Modal analysis"]
        assert modal_actions and all(button.isEnabled() for button in modal_actions)
        assert window.fields["density_kg_m3"].value() == 7850
        assert window.fields["mode_count"].value() == 6
        assert window.project_id == project["id"]
        assert window.application_title.parentWidget() is window.menuWidget()
        assert "DOO DOO DYNAMICS" in window.application_title.text()
        workspace.set_parameters(project["id"], {"load_N": 2500})
        window.refresh()
        assert window.fields["load_N"].value() == 2500
        workspace.show_project(project["id"], "mesh")
        window.refresh()
        assert "MESH" in window.viewport_title.text()
        assert workspace.ui_state()["desktop_connected"]
        assert window.theme == "dark"
        window.theme_button.click()
        assert window.theme == "light"
        assert Workspace(tmp_path).ui_state()["theme"] == "light"
        window.theme_button.click()
        assert window.theme == "dark"
        assert window.dark_action.isChecked()
        window.selectors["element_order"].setCurrentIndex(1)
        window.selectors["load_axis"].setCurrentIndex(2)
        window.selectors["load_kind"].setCurrentIndex(1)
        window.save_parameters()
        parameters = workspace.get_project(project["id"])["parameters"]
        assert (parameters["element_order"], parameters["load_axis"], parameters["load_kind"]) == (2, "z", "point")
    finally:
        window.close()
        window.view.setPage(None)
        window.deleteLater()
        application.processEvents()


def test_cat_translation_toggle_refresh_and_return_to_english_preserve_inputs(tmp_path):
    application = QApplication.instance() or QApplication([])
    workspace = Workspace(tmp_path)
    project = workspace.create_project("Geometry Modal Solve — my own project name")
    workspace.show_project(project["id"])
    window = SimulatorWindow(workspace)
    before = workspace.get_project(project["id"])
    disabled_before = [button.isEnabled() for button in window.findChildren(QPushButton)]
    try:
        window.cat_button.click()
        assert window.language == "cat"
        assert window.ribbon.tabText(0) == "Cat bed"
        assert "MEOWMULATOR" in window.application_title.text()
        assert window.tree.topLevelItem(0).text(0) == project["name"]
        assert "Do a science, meow" in next(button.text() for button in window.analysis_buttons if "science, meow" in button.text())
        assert window.fields["young_Pa"].value() == 210
        assert not window.dirty
        window.refresh()
        window.refresh()
        assert window.ribbon.tabText(0) == "Cat bed"
        assert workspace.get_project(project["id"]) == before
        window.cat_button.click()
        assert window.language == "en"
        assert window.ribbon.tabText(0) == "Home"
        assert window.application_title.text() == "DOO DOO DYNAMICS  /  SIMULATOR"
        assert window.animate_mode.text() == "Animate mode"
        assert workspace.get_project(project["id"]) == before
        assert [button.isEnabled() for button in window.findChildren(QPushButton)] == disabled_before
    finally:
        window.close()
        window.view.setPage(None)
        window.deleteLater()
        application.processEvents()
