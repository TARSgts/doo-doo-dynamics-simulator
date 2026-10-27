"""Project library and readable storage locations for the desktop."""
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout)


def open_folder(path):
    target = Path(path)
    folder = target if target.is_dir() else target.parent
    if not folder.is_dir():
        raise ValueError("This folder has not been created yet")
    if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
        raise ValueError("Windows could not open this folder")


def ask_project_name(parent, title, name=""):
    dialog = QInputDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setLabelText("Project name:")
    dialog.setTextValue(name)
    for field in dialog.findChildren(QLineEdit):
        field.setMaxLength(120)
        field.setToolTip("A name for this project. Renaming keeps its model, settings and result folders in place.")
    buttons = dialog.findChild(QDialogButtonBox)
    if buttons:
        for button in buttons.buttons():
            button.setToolTip("Save this project name." if buttons.buttonRole(button) == QDialogButtonBox.ButtonRole.AcceptRole else "Close without changing the name.")
    if dialog.exec():
        return dialog.textValue().strip()
    return None


class FileLocationsDialog(QDialog):
    def __init__(self, workspace, project_id, parent=None):
        super().__init__(parent)
        project = workspace.get_project(project_id)
        self.setWindowTitle("File locations — " + project["name"])
        self.resize(850, 430)
        layout = QVBoxLayout(self)
        note = QLabel("Your model is copied into the project. Each run saves its own inputs, logs and results. Renaming the project keeps these folders in place.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.path_fields = {}
        locations = workspace.project_locations(project_id)
        for key, caption in (("project_folder", "Project folder"), ("cad_file", "Model copy used by the simulator"),
                             ("source_file", "Original imported file"), ("latest_run", "Latest run folder"),
                             ("jobs_folder", "All runs"), ("library_file", "Saved project library")):
            layout.addWidget(QLabel(caption))
            row = QHBoxLayout()
            value = locations[key]
            field = QLineEdit(value or "")
            field.setReadOnly(True)
            field.setCursorPosition(0)
            field.setPlaceholderText("No runs yet" if key == "latest_run" else "Not available")
            field.setToolTip((value + "\n" if value else "") + "Select text to copy it, or use Copy path.")
            self.path_fields[key] = field
            row.addWidget(field, 1)
            copy = QPushButton("Copy path")
            copy.setToolTip("Copy this storage path to the clipboard.")
            copy.setEnabled(bool(value))
            copy.clicked.connect(lambda checked=False, text=value: QApplication.clipboard().setText(text))
            row.addWidget(copy)
            show = QPushButton("Open folder")
            show.setToolTip("Open this folder in the system file manager. For a file, open its containing folder.")
            target = Path(value) if value else None
            folder = target if key in {"project_folder", "jobs_folder", "latest_run"} else target.parent if target else None
            show.setEnabled(bool(folder and folder.is_dir()))
            show.clicked.connect(lambda checked=False, path=value: self.show_folder(path))
            row.addWidget(show)
            layout.addLayout(row)
        done = QPushButton("Done")
        done.setToolTip("Close file locations and return to the model.")
        done.clicked.connect(self.close)
        layout.addWidget(done)

    def show_folder(self, path):
        try:
            open_folder(path)
        except ValueError as error:
            QMessageBox.warning(self, "Open folder", str(error))


class ProjectLibraryDialog(QDialog):
    def __init__(self, workspace, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        self.selected_project_id = None
        self.setWindowTitle("Open project")
        self.resize(680, 480)
        layout = QVBoxLayout(self)
        note = QLabel("Open just the projects you need. Closed projects stay saved here, including their models and results.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search project names or model files…")
        self.search.setToolTip("Filter saved projects by name or imported model filename.")
        layout.addWidget(self.search)
        self.projects = QListWidget()
        self.projects.setToolTip("Select a saved project, then Open. Double-click also opens it.")
        layout.addWidget(self.projects, 1)
        self.count = QLabel()
        layout.addWidget(self.count)
        row = QHBoxLayout()
        self.open_button = QPushButton("Open project")
        self.open_button.setToolTip("Open the selected project in the outline.")
        self.open_button.clicked.connect(self.accept_project)
        row.addWidget(self.open_button)
        self.rename_button = QPushButton("Rename…")
        self.rename_button.setToolTip("Change the selected project's name without moving its files.")
        self.rename_button.clicked.connect(self.rename_selected)
        row.addWidget(self.rename_button)
        self.files_button = QPushButton("File locations…")
        self.files_button.setToolTip("See where the selected project's model and run files are stored.")
        self.files_button.clicked.connect(self.show_files)
        row.addWidget(self.files_button)
        cancel = QPushButton("Cancel")
        cancel.setToolTip("Close the library without opening a project.")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        layout.addLayout(row)
        self.search.textChanged.connect(self.populate)
        self.projects.itemSelectionChanged.connect(self.update_buttons)
        self.projects.itemDoubleClicked.connect(lambda item: self.accept_project())
        self.populate()

    def current_id(self):
        item = self.projects.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def populate(self):
        selected = self.current_id()
        self.projects.clear()
        query = self.search.text().strip().casefold()
        opened = {project["id"] for project in self.workspace.list_open_projects()}
        projects = self.workspace.list_projects()
        for project in projects:
            paths = self.workspace.project_locations(project["id"])
            model = paths["source_file"] or paths["cad_file"]
            filename = Path(model).name if model else "No model imported"
            if query not in (project["name"] + " " + filename).casefold():
                continue
            item = QListWidgetItem(project["name"] + ("  ·  Open" if project["id"] in opened else "") + "\n" + filename)
            item.setData(Qt.ItemDataRole.UserRole, project["id"])
            item.setToolTip(paths["project_folder"])
            self.projects.addItem(item)
            if project["id"] == selected:
                self.projects.setCurrentItem(item)
        if self.projects.currentRow() < 0 and self.projects.count():
            self.projects.setCurrentRow(0)
        self.count.setText(f"{self.projects.count()} of {len(projects)} saved projects")
        self.update_buttons()

    def update_buttons(self):
        for button in (self.open_button, self.rename_button, self.files_button):
            button.setEnabled(self.current_id() is not None)

    def accept_project(self):
        if self.current_id():
            self.selected_project_id = self.current_id()
            self.accept()

    def rename_selected(self):
        project_id = self.current_id()
        if project_id:
            name = ask_project_name(self, "Rename project", self.workspace.get_project(project_id)["name"])
            if name:
                self.workspace.rename_project(project_id, name)
                self.populate()

    def show_files(self):
        if self.current_id():
            FileLocationsDialog(self.workspace, self.current_id(), self).exec()
