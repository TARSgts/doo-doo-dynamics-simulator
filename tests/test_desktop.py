import os
import json
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QPushButton, QToolButton
from opensim.desktop import SimulatorWindow
from opensim.workspace import Workspace


def test_study_tree_switches_properties_without_solving_or_losing_hidden_inputs(tmp_path, monkeypatch):
    from PySide6.QtCore import Qt
    application = QApplication.instance() or QApplication([])
    workspace = Workspace(tmp_path)
    project = workspace.create_project("Study settings")
    workspace.show_project(project["id"])
    window = SimulatorWindow(workspace)
    def select(study):
        root = window.tree.topLevelItem(0)
        branch = next(root.child(index) for index in range(root.childCount())
                      if root.child(index).data(0, Qt.ItemDataRole.UserRole + 1) == study)
        window.select_tree_item(branch, 0)
    def visible(key):
        control = (window.fields | window.selectors)[key]
        assert control.isHidden() == window.properties_form.labelForField(control).isHidden()
        return not control.isHidden()
    try:
        root = window.tree.topLevelItem(0)
        assert root.childCount() == 5
        assert [root.child(i).text(0) for i in (2, 3, 4)] == ["Static Structural", "Modal Analysis", "Convergence Study"]
        assert visible("load_N") and not visible("density_kg_m3") and not visible("convergence_levels")
        window.fields["load_N"].setValue(23.4)
        select("modal")
        assert workspace.ui_state()["study"] == "modal"
        assert "MODAL" in window.details_heading.text()
        assert visible("density_kg_m3") and visible("mode_count")
        assert not visible("load_N") and not visible("load_axis") and not visible("convergence_target")
        assert window.region_button.text() == "Support region…"
        assert window.run_study_button.text() == "Run modal study"
        assert all(not button.isEnabled() for button in window.force_pick_buttons)
        assert window.fields["load_N"].value() == 23.4
        window.fields["density_kg_m3"].setValue(1040)
        select("convergence")
        assert visible("convergence_levels") and visible("convergence_target") and visible("load_N")
        assert not visible("mode_count")
        assert window.run_study_button.text() == "Run convergence study"
        select("static")
        assert visible("load_N") and not visible("convergence_levels")
        assert window.fields["density_kg_m3"].value() == 1040
        assert window.fields["load_N"].value() == 23.4
        assert workspace.get_project(project["id"]) == project
        assert workspace.list_jobs(project["id"]) == []
        select("modal")
        calls = []
        monkeypatch.setattr(window, "modal", lambda: calls.append("modal"))
        window.run_selected_study()
        assert calls == ["modal"]
        window.save_parameters()
        assert workspace.get_project(project["id"])["parameters"]["load_N"] == 23.4
        assert workspace.get_project(project["id"])["parameters"]["density_kg_m3"] == 1040
    finally:
        window.close()
        window.view.setPage(None)
        window.deleteLater()
        application.processEvents()


def test_modal_region_dialog_only_edits_support(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QDialog, QLineEdit
    application = QApplication.instance() or QApplication([])
    workspace = Workspace(tmp_path)
    project = workspace.create_project("Modal support")
    workspace.select_study(project["id"], "modal")
    window = SimulatorWindow(workspace)
    before = workspace.get_project(project["id"])
    checked = []
    def inspect(dialog):
        assert dialog.windowTitle() == "Modal fixed support region"
        assert len(dialog.findChildren(QLineEdit)) == 2
        checked.append(True)
        return QDialog.DialogCode.Rejected
    monkeypatch.setattr(QDialog, "exec", inspect)
    try:
        window.edit_regions()
        assert checked
        assert workspace.get_project(project["id"]) == before
    finally:
        window.close()
        window.view.setPage(None)
        window.deleteLater()
        application.processEvents()


def test_switching_study_cancels_face_picking_without_saving_draft(tmp_path):
    application = QApplication.instance() or QApplication([])
    workspace = Workspace(tmp_path)
    project = workspace.create_project("Draft face selection")
    workspace.show_project(project["id"])
    window = SimulatorWindow(workspace)
    try:
        window.face_pick_session = {"project_id": project["id"], "revision": project["revision"],
                                   "view": window.loaded_view, "study": "static"}
        workspace.select_study(project["id"], "modal")
        window.refresh()
        assert window.face_pick_session is None
        assert workspace.get_project(project["id"]) == project
    finally:
        window.close()
        window.view.setPage(None)
        window.deleteLater()
        application.processEvents()


def test_outline_only_open_projects_close_saves_draft_and_empty_stays_empty(tmp_path):
    application = QApplication.instance() or QApplication([])
    workspace = Workspace(tmp_path)
    first = workspace.create_project("Open first")
    second = workspace.create_project("Open second")
    closed = workspace.create_project("Saved but closed")
    workspace.show_project(first["id"])
    workspace.show_project(second["id"])
    window = SimulatorWindow(workspace)
    try:
        assert window.tree.topLevelItemCount() == 2
        window.fields["load_N"].setValue(42)
        window.close_project()
        assert workspace.get_project(second["id"])["parameters"]["load_N"] == 42
        assert window.project_id == first["id"]
        assert window.tree.topLevelItemCount() == 1
        window.close_project()
        window.refresh()
        assert window.tree.topLevelItemCount() == 0
        assert window.project_id is None
        assert window.loaded_view is None
        assert "NO PROJECT" in window.viewport_title.text()
        assert not window.close_project_button.isEnabled()
        assert len(workspace.list_projects()) == 3
        workspace.show_project(closed["id"])
        window.refresh()
        assert window.project_id == closed["id"]
        assert window.tree.topLevelItemCount() == 1
        assert window.tree.topLevelItem(0).text(0) == "Saved but closed"
    finally:
        window.close()
        window.view.setPage(None)
        window.deleteLater()
        application.processEvents()


def test_project_library_search_and_locations_keep_user_names_and_exact_paths(tmp_path):
    from opensim.project_dialogs import FileLocationsDialog, ProjectLibraryDialog
    application = QApplication.instance() or QApplication([])
    workspace = Workspace(tmp_path / "workspace")
    project = workspace.create_project("Home / my own project name")
    workspace.create_project("Other project")
    source = tmp_path / "tail model.step"
    source.write_text("model")
    workspace.import_cad(project["id"], source)
    library = ProjectLibraryDialog(workspace)
    locations = FileLocationsDialog(workspace, project["id"])
    try:
        assert library.projects.count() == 2
        library.search.setText("TAIL MODEL")
        assert library.projects.count() == 1
        assert library.current_id() == project["id"]
        assert not workspace.list_open_projects()
        library.accept_project()
        assert library.selected_project_id == project["id"]
        assert locations.path_fields["source_file"].text() == str(source)
        assert Path(locations.path_fields["cad_file"].text()).read_text() == "model"
        assert all(field.isReadOnly() for field in locations.path_fields.values())
        library.search.setText("does not exist")
        assert not library.open_button.isEnabled()
        assert not library.rename_button.isEnabled()
    finally:
        library.close()
        locations.close()
        application.processEvents()


def test_perpendicular_direction_selects_surface_loading_and_saves_without_unit_changes(tmp_path):
    from opensim.hover_help import FIELD_HELP
    application = QApplication.instance() or QApplication([])
    workspace = Workspace(tmp_path)
    project = workspace.create_project("Perpendicular force")
    workspace.show_project(project["id"])
    window = SimulatorWindow(workspace)
    try:
        axis, kind = window.selectors["load_axis"], window.selectors["load_kind"]
        original = window.fields["load_N"].value()
        for direction in ("normal-in", "normal-out"):
            axis.setCurrentIndex(axis.findData(direction))
            assert kind.currentData() == "traction"
            assert not kind.model().item(kind.findData("point")).isEnabled()
            assert not kind.model().item(kind.findData("face")).isEnabled()
            assert not window.normal_load_note.isHidden()
            assert "net force" in window.fields["load_N"].toolTip()
            window.save_parameters()
            saved = workspace.get_project(project["id"])["parameters"]
            assert saved["load_axis"] == direction
            assert saved["load_kind"] == "traction"
            assert saved["load_N"] == original
            window.refresh()
        axis.setCurrentIndex(axis.findData("x"))
        assert kind.model().item(kind.findData("point")).isEnabled()
        assert window.normal_load_note.isHidden()
        assert window.fields["load_N"].toolTip() == FIELD_HELP["load_N"]
    finally:
        window.close()
        window.view.setPage(None)
        window.deleteLater()
        application.processEvents()


def test_face_picking_saves_both_regions_cancels_and_rejects_stale_drafts(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    workspace = Workspace(tmp_path)
    project = workspace.create_project("Picked faces")
    workspace.show_project(project["id"])
    window = SimulatorWindow(workspace)
    scripts = []
    selection = None
    def javascript(script, callback=None):
        scripts.append(script)
        if callback:
            callback(json.dumps(selection) if "JSON.stringify(getFaceSelection())" in script else True)
    monkeypatch.setattr(window.view.page(), "runJavaScript", javascript)
    try:
        before = workspace.get_project(project["id"])
        window.begin_face_picking("support")
        assert not window.pick_actions.isHidden()
        session = window.face_pick_session
        window.begin_face_picking("load")
        assert window.face_pick_session is session
        assert "switchFacePicking" in scripts[-1]
        window.cancel_face_picking()
        assert workspace.get_project(project["id"]) == before
        window.begin_face_picking("support")
        session = window.face_pick_session
        selection = {"mode": "load", "support": [1], "load": [2, 3], "available": [1, 2, 3],
                     "touched": {"support": True, "load": True}}
        window.save_picked_faces()
        updated = workspace.get_project(project["id"])
        assert updated["parameters"]["support_region"] == {"faces": [1]}
        assert updated["parameters"]["load_region"] == {"faces": [2, 3]}
        assert updated["parameters"]["load_kind"] == "traction"
        assert updated["parameters"]["load_N"] == before["parameters"]["load_N"]
        assert updated["revision"] == before["revision"] + 1
        window.refresh()
        window.begin_face_picking("load")
        session = window.face_pick_session
        workspace.set_parameters(project["id"], {"load_N": 500})
        with pytest.raises(ValueError, match="project changed"):
            window.commit_picked_faces(session, selection)
        assert workspace.get_project(project["id"])["parameters"]["load_N"] == 500
        assert window.face_pick_session is None
        window.refresh()
        window.begin_face_picking("load")
        with pytest.raises(ValueError, match="at least one face"):
            window.commit_picked_faces(window.face_pick_session, selection | {"load": []})
        window.cancel_face_picking()
    finally:
        monkeypatch.undo()  # Restore the Qt page method before its C++ object is deleted.
        window.close()
        window.view.setPage(None)
        window.deleteLater()
        application.processEvents()


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
    from PySide6.QtWidgets import QDockWidget, QScrollArea, QSplitter
    from PySide6.QtTest import QTest
    from PySide6.QtCore import QPoint
    application = QApplication.instance() or QApplication([])
    workspace = Workspace(tmp_path)
    project = workspace.create_project("Properties sizing")
    workspace.show_project(project["id"])
    window = SimulatorWindow(workspace)
    window.show()
    try:
        dock = window.findChild(QDockWidget, "outline")
        scroll = window.findChild(QScrollArea, "PropertiesScroll")
        splitter = window.findChild(QSplitter, "ModelPropertiesSplitter")
        handle = splitter.handle(1)
        assert handle.height() >= 8
        assert not splitter.childrenCollapsible()
        before = splitter.sizes()
        point = handle.rect().center()
        QTest.mousePress(handle, Qt.MouseButton.LeftButton, pos=point)
        QTest.mouseMove(handle, point + QPoint(0, 70))
        QTest.mouseRelease(handle, Qt.MouseButton.LeftButton, pos=point + QPoint(0, 70))
        application.processEvents()
        assert splitter.sizes()[0] > before[0]
        assert splitter.sizes()[1] < before[1]
        splitter.setSizes(before)
        application.processEvents()
        assert abs(splitter.sizes()[0] - before[0]) <= 1
        for language in ("en", "cat"):
            window.set_language(language)
            for width in (330, 420, 550):
                window.resizeDocks([dock], [width], Qt.Orientation.Horizontal)
                for _ in range(3):
                    application.processEvents()
                assert scroll.widget().width() <= scroll.viewport().width()
                for control in list(window.fields.values()) + list(window.selectors.values()):
                    if control.isHidden():
                        continue  # Other study types retain values without occupying layout space.
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
        window.theme_actions['light'].trigger()
        assert window.theme == "light"
        assert Workspace(tmp_path).ui_state()["theme"] == "light"
        window.theme_actions['dark'].trigger()
        assert window.theme == "dark"
        assert window.theme_actions['dark'].isChecked()
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


def test_settings_menu_consolidates_preferences_and_midnight_preserves_model(tmp_path):
    application = QApplication.instance() or QApplication([])
    workspace = Workspace(tmp_path)
    project = workspace.create_project('Settings check')
    workspace.show_project(project['id'])
    window = SimulatorWindow(workspace)
    before = workspace.get_project(project['id'])
    try:
        assert [action.text() for action in window.application_menu.actions()] == ['File', 'Settings', 'Help']
        assert not hasattr(window, 'theme_button') and not hasattr(window, 'cat_button')
        assert window.cat_action in window.settings_menu.actions()
        assert any(action.text() == 'Discord Rich Presence…' for action in window.settings_menu.actions())
        assert set(window.theme_actions) == {'light', 'dark', 'midnight'}
        window.fields['load_N'].setValue(321)
        assert window.dirty
        for theme in ('midnight', 'light', 'dark', 'midnight'):
            window.theme_actions[theme].trigger()
            assert window.theme == theme
            assert sum(action.isChecked() for action in window.theme_actions.values()) == 1
            assert window.theme_actions[theme].isChecked()
            assert Workspace(tmp_path).ui_state()['theme'] == theme
            assert window.fields['load_N'].value() == 321 and window.dirty
            assert workspace.get_project(project['id']) == before
        assert '#080b12' in window.styleSheet()
        window.cat_action.trigger()
        window.refresh()
        assert window.cat_action.isChecked() and window.language == 'cat'
        assert window.theme_actions['midnight'].isChecked()
        window.cat_action.trigger()
        assert window.settings_menu.title() == 'Settings'
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
        window.cat_action.trigger()
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
        window.cat_action.trigger()
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


def test_stop_computing_button_only_works_while_a_job_is_active(tmp_path):
    import time
    application = QApplication.instance() or QApplication([])
    workspace = Workspace(tmp_path)
    project = workspace.create_project("Stop button")
    workspace.show_project(project["id"])
    window = SimulatorWindow(workspace)
    try:
        buttons = [button for button in window.findChildren(QPushButton) if button.text() == "Stop computing"]
        assert len(buttons) == 2 and buttons == window.stop_buttons
        assert all(not button.isEnabled() and button.toolTip() for button in buttons)
        with pytest.raises(ValueError, match="Nothing is computing"):
            window.stop_computing(confirm=False)
        now = time.time()
        with workspace.connect() as connection:
            connection.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)", ("long-solve", project["id"], "solve", "running", 0,
                               "{}", None, None, now - 600, now))
        window.refresh()
        assert all(button.isEnabled() for button in buttons)
        assert not window.stop_button.isHidden()
        assert not any(button.isEnabled() for button in window.analysis_buttons)
        window.stop_computing(confirm=False)
        window.refresh()
        assert workspace.get_job("long-solve")["status"] == "cancelled"
        assert not any(button.isEnabled() for button in buttons)
        assert window.stop_button.isHidden()
        assert "Stopped by user" in window.progress_label.text()
        assert window.job_progress.format() == "Stopped"
        assert all(button.isEnabled() for button in window.analysis_buttons)
        assert "[CANCELLED]" in window.messages.toPlainText()
        window.set_language("cat")
        assert window.stop_buttons[1].text() == "Stop da science"
        window.set_language("en")
        assert window.stop_buttons[1].text() == "Stop computing"
    finally:
        window.close()
        window.view.setPage(None)
        window.deleteLater()
        application.processEvents()


def test_importing_a_mesh_file_assumes_millimeters_once(tmp_path, monkeypatch):
    import struct
    from PySide6.QtWidgets import QFileDialog
    application = QApplication.instance() or QApplication([])
    workspace = Workspace(tmp_path / "workspace")
    project = workspace.create_project("STL import")
    workspace.show_project(project["id"])
    stl = tmp_path / "part.stl"
    with stl.open("wb") as handle:
        handle.write(b"x".ljust(80, b" ") + struct.pack("<I", 0))
    started = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(stl), ""))
    monkeypatch.setattr(workspace, "start_job", lambda project_id, kind, **kwargs: started.append(kind))
    window = SimulatorWindow(workspace)
    try:
        window.import_cad()
        assert workspace.get_project(project["id"])["parameters"]["cad_scale"] == 0.001
        assert "millimeters" in window.details_note.text()
        assert started == ["mesh"]
        workspace.set_parameters(project["id"], {"cad_scale": 2.0})
        window.import_cad()
        assert workspace.get_project(project["id"])["parameters"]["cad_scale"] == 2.0  # a chosen scale is kept
    finally:
        window.close()
        window.view.setPage(None)
        window.deleteLater()
        application.processEvents()


def test_convergence_controls_save_settings_and_report_opens_once_after_finishing(tmp_path, monkeypatch):
    import time
    from opensim.convergence import analyse, write_report
    application = QApplication.instance() or QApplication([])
    workspace = Workspace(tmp_path / "workspace")
    project = workspace.create_project("Convergence UI")
    workspace.show_project(project["id"])
    window = SimulatorWindow(workspace)
    started = []
    monkeypatch.setattr(workspace, "start_job", lambda project_id, kind, **kwargs: started.append(kind))
    try:
        assert window.fields["convergence_levels"].value() == 4
        assert window.fields["convergence_ratio"].value() == pytest.approx(1.4)
        window.fields["convergence_levels"].setValue(5)
        window.fields["convergence_tolerance_percent"].setValue(1.0)
        window.selectors["convergence_target"].setCurrentIndex(window.selectors["convergence_target"].findData("response"))
        window.convergence()
        saved = workspace.get_project(project["id"])["parameters"]
        assert (saved["convergence_levels"], saved["convergence_tolerance_percent"], saved["convergence_target"]) == (5, 1.0, "response")
        assert started == ["convergence"]
        buttons = [button for button in window.findChildren(QToolButton) + window.findChildren(QPushButton)
                   if button.text() in {"Convergence", "Convergence study"}]
        assert len(buttons) == 2 and all(button in window.analysis_buttons and button.toolTip() for button in buttons)
        # A study that finishes while the app is open shows its report automatically, once.
        revision = workspace.get_project(project["id"])["revision"]
        study = tmp_path / "workspace" / project["id"] / "jobs" / "study" / "convergence"
        study.mkdir(parents=True)
        levels = [{"level": n, "mesh_size_m": 0.01 / 1.4 ** (n - 1), "nodes": 10 * n, "tetrahedra": 100 * 3 ** n,
                   "viewer": f"mesh-{n}/results.html", "values": {"displacement": 1 + 0.1 / n ** 2, "response": 1.0, "stress": 2.0}}
                  for n in (1, 2, 3)]
        result = {"analysis": "convergence", "target": "displacement", "tolerance_percent": 2, "refinement_ratio": 1.4,
                  "requested_levels": 5, "element_type": "C3D10", "levels": levels, "quantities": analyse(levels, 0.02),
                  "stop_reason": "test", "verdict": "converged", "nodes": 30, "tetrahedra": 2700}
        write_report(study / "report.html", result)
        now = time.time() + 1
        with workspace.connect() as connection:
            connection.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)", ("study", project["id"], "convergence", "completed",
                               revision, "{}", __import__("json").dumps(result), None, now, now))
        window.refresh()
        dialog = window.reference_dialogs[("convergence", "study")]
        assert dialog.isVisible() and dialog.windowTitle() == "Mesh convergence study"
        dialog.close()
        window.refresh()
        assert not dialog.isVisible()  # not reopened on later refreshes
        assert "Convergence study (displacement)" in window.messages.toPlainText()
        assert window.show_convergence_report() is dialog
        from PySide6.QtCore import QUrl
        from PySide6.QtWebEngineWidgets import QWebEngineView
        view = dialog.findChild(QWebEngineView, "ConvergenceReport")
        view.setUrl(QUrl.fromLocalFile(str(study / "mesh-1" / "results.html")))
        window.set_theme("light")
        assert window.show_convergence_report() is dialog
        assert Path(view.url().toLocalFile()) == study / "report.html"
        assert view.url().query() == "theme=light"
    finally:
        from PySide6.QtWebEngineWidgets import QWebEngineView
        for dialog in window.reference_dialogs.values():
            dialog.findChild(QWebEngineView).setPage(None)
            dialog.close()
        window.close()
        window.view.setPage(None)
        window.deleteLater()
        application.processEvents()


def test_export_gif_saves_file_reports_progress_and_handles_failures(tmp_path, monkeypatch):
    import base64
    import time
    application = QApplication.instance() or QApplication([])
    workspace = Workspace(tmp_path / "workspace")
    project = workspace.create_project("GIF export")
    revision = workspace.get_project(project["id"])["revision"]
    now = time.time()
    result = {"analysis": "modal", "frequencies_Hz": [12.5, 80.0], "mode_count": 2, "nodes": 4, "tetrahedra": 1}
    with workspace.connect() as connection:
        connection.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)", ("modal-job", project["id"], "modal", "completed", revision,
                           "{}", __import__("json").dumps(result), None, now, now))
    from opensim.results import write_viewer_data
    directory = tmp_path / "workspace" / project["id"] / "jobs" / "modal-job" / "modal"
    directory.mkdir(parents=True)
    for mode in (1, 2):
        write_viewer_data(directory / f"mode-{mode}.html", {"points": [[0, 0, 0], [1, 0, 0], [0, 1, 0]], "faces": [[0, 1, 2]],
                          "displacement": [[0, 0, 0], [0, 0, 1], [0, 0, 0]],
                          "summary": {"analysis": "modal", "mode_number": mode, "frequency_Hz": result["frequencies_Hz"][mode - 1]}})
    window = SimulatorWindow(workspace)
    gif = b"GIF89a" + b"\x00" * 20
    script = {"states": [], "data": base64.b64encode(gif).decode(), "calls": []}
    def javascript(source, callback=None):
        script["calls"].append(source)
        if callback is None:
            return
        if "startModeGifExport" in source:
            callback(script.get("started", True))
        elif "gifExportState" in source:
            callback(script["states"].pop(0) if script["states"] else None)
        elif "takeGifExport" in source:
            callback(script["data"])
    monkeypatch.setattr(window.view.page(), "runJavaScript", javascript)
    def run_to_end():
        for _ in range(20):
            if window.gif_export is None:
                return
            window.poll_gif_export()
    try:
        with pytest.raises(ValueError, match="modal result"):
            window.export_mode_gif(tmp_path / "x.gif")
        workspace.show_project(project["id"], "modal", 2)
        window.refresh()
        assert not window.export_gif_button.isHidden() and window.export_gif_button.isEnabled()
        assert window.export_gif_button.toolTip()
        script["states"] = ['{"status":"running","progress":0.5,"error":null,"bytes":0}', '{"status":"done","progress":1,"error":null,"bytes":26}']
        window.export_mode_gif(tmp_path / "out" / "mode2", width=640, frames=24)
        assert '"frames": 24' in next(call for call in script["calls"] if "startModeGifExport" in call)
        assert not window.export_gif_button.isEnabled()
        window.poll_gif_export()
        assert "50%" in window.status_label.text()
        run_to_end()
        assert (tmp_path / "out" / "mode2.gif").read_bytes() == gif
        assert "Saved GIF" in window.status_label.text() and window.export_gif_button.isEnabled()
        warnings = []
        monkeypatch.setattr("opensim.desktop.QMessageBox.warning", lambda *args: warnings.append(args[2]))
        script["states"] = ['{"status":"error","progress":0.2,"error":"boom","bytes":0}']
        window.export_mode_gif(tmp_path / "bad.gif")
        run_to_end()
        assert "boom" in warnings[-1] and not (tmp_path / "bad.gif").exists()
        script["states"] = [None]  # page reloaded mid-export
        window.export_mode_gif(tmp_path / "interrupted.gif")
        run_to_end()
        assert "interrupted" in warnings[-1]
        script["started"] = False
        window.export_mode_gif(tmp_path / "old.gif")
        assert "cannot export" in warnings[-1] and window.gif_export is None
        script["started"], script["data"] = True, base64.b64encode(b"not a gif").decode()
        script["states"] = ['{"status":"done","progress":1,"error":null,"bytes":9}']
        window.export_mode_gif(tmp_path / "corrupt.gif")
        run_to_end()
        assert "no GIF data" in warnings[-1] and not (tmp_path / "corrupt.gif").exists()
    finally:
        monkeypatch.undo()  # restore the page method before Qt deletes the page
        window.close()
        window.view.setPage(None)
        window.deleteLater()
        application.processEvents()
