"""Projects for the desktop workbench."""
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialogButtonBox, QFileDialog, QInputDialog, QLineEdit, QMenu, QPushButton
from opensim.hover_help import BUTTON_HELP
from opensim.project_dialogs import FileLocationsDialog, ProjectLibraryDialog, ask_project_name, open_folder


class ProjectsMixin:
    def open_project(self):
        dialog = ProjectLibraryDialog(self.workspace, self)
        if dialog.exec() and dialog.selected_project_id:
            self.save_before_project_change()
            self.workspace.show_project(dialog.selected_project_id)
            self.dirty = False

    def rename_project(self, project_id=None):
        project_id = project_id or self.require_project()
        name = ask_project_name(self, "Rename project", self.workspace.get_project(project_id)["name"])
        if name:
            self.workspace.rename_project(project_id, name)

    def close_project(self, project_id=None):
        project_id = project_id or self.require_project()
        if project_id == self.project_id:
            self.save_before_project_change()
        self.workspace.close_project(project_id)
        self.refresh()

    def close_other_projects(self, project_id):
        self.save_before_project_change()
        self.workspace.show_project(project_id)
        for project in self.workspace.list_open_projects():
            if project["id"] != project_id:
                self.workspace.close_project(project["id"])
        self.refresh()

    def show_file_locations(self, project_id=None):
        dialog = FileLocationsDialog(self.workspace, project_id or self.require_project(), self)
        self.file_dialogs.append(dialog)
        dialog.show()
        return dialog

    def open_project_folder(self, project_id=None):
        open_folder(self.workspace.project_locations(project_id or self.require_project())["project_folder"])

    def open_run_folder(self):
        path = self.workspace.project_locations(self.require_project())["latest_run"]
        if not path:
            raise ValueError("This project has no runs yet")
        open_folder(path)

    def project_context_menu(self, position):
        item = self.tree.itemAt(position)
        if not item:
            return
        project_id = item.data(0, Qt.ItemDataRole.UserRole)[0]
        menu = QMenu(self)
        for title, callback in (("Rename project…", lambda: self.rename_project(project_id)),
                                ("Open project folder", lambda: self.open_project_folder(project_id)),
                                ("File locations…", lambda: self.show_file_locations(project_id)),
                                ("Close project", lambda: self.close_project(project_id)),
                                ("Close other projects", lambda: self.close_other_projects(project_id))):
            action = menu.addAction(title)
            action.setToolTip(BUTTON_HELP[title.rstrip("…")])
            action.triggered.connect(lambda checked=False, handler=callback: self.safe(handler))
        menu.exec(self.tree.viewport().mapToGlobal(position))

    def new_project(self):
        dialog = QInputDialog(self)
        dialog.setWindowTitle("New simulation project")
        dialog.setLabelText("Project name:")
        for field in dialog.findChildren(QLineEdit):
            field.setToolTip("Give this simulation a name so you can find it in the project outline.")
        for button in dialog.findChildren(QPushButton):
            button.setToolTip("Create the named project." if dialog.findChild(QDialogButtonBox).buttonRole(button) == QDialogButtonBox.ButtonRole.AcceptRole else "Close without creating a project.")
        accepted = dialog.exec()
        name = dialog.textValue()
        if accepted and name.strip():
            self.save_before_project_change()
            project = self.workspace.create_project(name)
            self.workspace.show_project(project["id"])
            self.dirty = False

    def create_demo(self):
        self.save_before_project_change()
        project = self.workspace.create_project("Perforated plate / " + datetime.now().strftime("%H:%M:%S"))
        self.workspace.show_project(project["id"], "mesh")
        self.workspace.start_job(project["id"], "example")
        self.dirty = False

    def create_beam(self):
        self.save_before_project_change()
        from opensim.validation import BEAM_PARAMETERS
        project = self.workspace.create_project("Cantilever beam / " + datetime.now().strftime("%H:%M:%S"))
        self.workspace.set_parameters(project["id"], BEAM_PARAMETERS)
        self.workspace.show_project(project["id"], "mesh")
        self.workspace.start_job(project["id"], "example", example="cantilever_beam")
        self.dirty = False

    def create_heat_sink(self):
        self.save_before_project_change()
        project = self.workspace.create_project("Sample heat sink / conduction / " + datetime.now().strftime("%H:%M:%S"))
        self.workspace.start_job(project['id'], 'example', example='heat_sink')
        self.workspace.show_project(project['id'], 'mesh')
        self.dirty = False

    def import_cad(self):
        project_id = self.require_project()
        path, _ = QFileDialog.getOpenFileName(
            self, "Import a single solid", "",
            "All supported (*.step *.stp *.iges *.igs *.brep *.stl *.obj *.3mf);;"
            "Exact CAD (*.step *.stp *.iges *.igs *.brep);;Mesh files (*.stl *.obj *.3mf)")
        if path:
            project = self.workspace.import_cad(project_id, path)
            if Path(path).suffix.lower() in {".stl", ".obj", ".3mf"} and project["parameters"]["cad_scale"] == 1:
                # STL/OBJ default to mm; 3MF's declared units are normalized to mm by the reader.
                self.workspace.set_parameters(project_id, {"cad_scale": 0.001})
                self.project_revision = None
                self.details_note.setText("Mesh file imported: CAD scale set to 0.001 (millimeters). "
                                          "Change it to 1 if the file is in meters, then mesh again.")
            self.workspace.show_project(project_id, "geometry")
            self.workspace.start_job(project_id, "mesh")
            self.dirty = False
