import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QPushButton, QToolButton
from opensim.desktop import SimulatorWindow
from opensim.workspace import Workspace


def test_hover_help_covers_controls_and_survives_refresh_and_theme_changes(tmp_path):
    from opensim.hover_help import FIELD_HELP
    from PySide6.QtWidgets import QComboBox
    application = QApplication.instance() or QApplication([])
    workspace = Workspace(tmp_path)
    project = workspace.create_project("Hover help")
    workspace.show_project(project["id"])
    window = SimulatorWindow(workspace)
    before = workspace.get_project(project["id"])
    try:
        for key, control in {**window.fields, **window.selectors}.items():
            assert control.toolTip() == FIELD_HELP[key]
        for control in window.findChildren(QPushButton) + window.findChildren(QToolButton) + window.findChildren(QComboBox):
            # Qt's own dock and combo internals are not user-facing controls.
            if isinstance(control, (QPushButton, QToolButton)) and not control.text():
                continue
            assert control.toolTip(), control
        assert "not kilograms" in window.fields["load_N"].toolTip()
        assert "does not turn on gravity" in window.fields["density_kg_m3"].toolTip()
        assert "viewing only" in window.deformation.toolTip()
        for language, theme in (("cat", "light"), ("en", "dark")):
            window.set_language(language)
            window.set_theme(theme)
            window.refresh()
            assert window.fields["load_N"].toolTip() == FIELD_HELP["load_N"]
            assert window.apply_button.toolTip()
        assert not window.dirty
        assert workspace.get_project(project["id"]) == before
    finally:
        window.close()
        window.view.setPage(None)
        window.deleteLater()
        application.processEvents()


def test_number_fields_ignore_wheel_without_changing_inputs_but_keep_keyboard_controls(tmp_path):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QScrollArea
    application = QApplication.instance() or QApplication([])
    workspace = Workspace(tmp_path)
    project = workspace.create_project("Wheel guard")
    workspace.show_project(project["id"])
    window = SimulatorWindow(workspace)
    try:
        scroll = window.findChild(QScrollArea, "PropertiesScroll")
        scroll.setFixedHeight(250)
        window.show()
        application.processEvents()
        bar = scroll.verticalScrollBar()
        assert bar.maximum() > 0
        field = window.fields["mesh_size_m"]
        event = QWheelEvent(QPointF(5, 5), QPointF(field.mapToGlobal(QPoint(5, 5))), QPoint(), QPoint(0, -120),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
        application.sendEvent(field, event)
        assert bar.value() > 0
        for field in window.fields.values():
            original = field.value()
            for focused in (False, True):
                field.setFocus() if focused else field.clearFocus()
                for delta in (-120, 120):
                    event = QWheelEvent(QPointF(5, 5), QPointF(field.mapToGlobal(QPoint(5, 5))), QPoint(), QPoint(0, delta),
                                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
                    application.sendEvent(field, event)
                    assert field.value() == original
        assert not window.dirty
        assert workspace.get_project(project["id"])["revision"] == 0
        field = window.fields["mode_count"]
        original = field.value()
        QTest.keyClick(field, Qt.Key.Key_Up)
        assert field.value() == original + 1
    finally:
        window.close()
        window.view.setPage(None)
        window.deleteLater()
        application.processEvents()


def test_bottom_progress_busy_completed_failed_and_project_switch(tmp_path):
    import time
    application = QApplication.instance() or QApplication([])
    workspace = Workspace(tmp_path)
    first = workspace.create_project("First")
    workspace.show_project(first["id"])
    window = SimulatorWindow(workspace)
    try:
        job = {"id": "progress-test", "kind": "solve", "status": "queued", "progress_stage": "queued",
               "created": time.time() - 65, "updated": time.time()}
        window.update_job_progress(job)
        assert window.job_progress.maximum() == 0
        assert "Waiting to start" in window.progress_label.text()
        assert "01:" in window.progress_label.text()
        job.update(status="running", progress_stage="solving")
        window.update_job_progress(job)
        assert window.job_progress.maximum() == 0
        assert "CalculiX solving" in window.progress_label.text()
        workspace.set_language("cat")
        window.update_job_progress(job)
        assert "Doing a science, meow" in window.progress_label.text()
        job.update(status="completed", progress_stage="completed")
        window.update_job_progress(job)
        assert window.job_progress.maximum() == 100 and window.job_progress.value() == 100
        job.update(status="failed", progress_stage="failed")
        window.update_job_progress(job)
        assert window.job_progress.value() == 0
        assert "bonked" in window.progress_label.text()
        with workspace.connect() as connection:
            connection.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)", ("stored-progress", first["id"], "mesh", "completed", 0,
                               "{}", None, None, time.time() - 5, time.time()))
        window.refresh()
        assert window.job_progress.value() == 100
        workspace.set_parameters(first["id"], {"load_N": 2000})
        window.refresh()
        assert window.progress_panel.isHidden()
        second = workspace.create_project("Second")
        workspace.show_project(second["id"])
        window.refresh()
        assert window.progress_panel.isHidden()
        assert window.job_progress.value() == 0
    finally:
        window.close()
        window.view.setPage(None)
        window.deleteLater()
        application.processEvents()


def test_property_fields_stay_inside_narrow_and_wide_dock_in_both_languages(tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDockWidget, QScrollArea
    application = QApplication.instance() or QApplication([])
    workspace = Workspace(tmp_path)
    project = workspace.create_project("Properties sizing")
    workspace.show_project(project["id"])
    window = SimulatorWindow(workspace)
    window.show()
    try:
        dock = window.findChild(QDockWidget, "outline")
        scroll = window.findChild(QScrollArea, "PropertiesScroll")
        for language in ("en", "cat"):
            window.set_language(language)
            for width in (330, 420, 550):
                window.resizeDocks([dock], [width], Qt.Orientation.Horizontal)
                for _ in range(3):
                    application.processEvents()
                assert scroll.widget().width() <= scroll.viewport().width()
                for control in list(window.fields.values()) + list(window.selectors.values()):
                    location = control.mapTo(scroll.widget(), control.rect().topLeft())
                    assert location.x() >= 0
                    assert location.x() + control.width() <= scroll.widget().width()
    finally:
        window.close()
        window.view.setPage(None)
        window.deleteLater()
        application.processEvents()


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
        assert not window.windowIcon().isNull()
        for size in (16, 32, 256):
            assert not window.windowIcon().pixmap(size, size).isNull()
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
