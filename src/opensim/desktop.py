import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

from PySide6.QtCore import Qt, QSignalBlocker, QTimer, QUrl
from PySide6.QtGui import QAction, QFont
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (QApplication, QComboBox, QDockWidget, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QHBoxLayout, QInputDialog,
                               QLabel, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
                               QSplitter, QTabWidget, QToolButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from opensim.workspace import CAPABILITIES, Workspace


STYLE = """
QMainWindow { background: #e8edf3; }
QWidget { color: #27374a; font-family: 'Segoe UI'; font-size: 12px; }
QMenuBar { background: #172b43; color: #e7eff8; padding: 4px; }
QMenuBar::item:selected { background: #304961; }
QMenu { background: white; }
QTabWidget::pane { border: 0; background: #f6f8fb; }
QTabBar::tab { background: #e5eaf1; padding: 9px 19px; color: #45576c; }
QTabBar::tab:selected { background: #fff; color: #1c344f; border-top: 3px solid #d99530; }
QToolButton { background: transparent; border: 1px solid transparent; padding: 9px 15px; border-radius: 4px; }
QToolButton:hover { background: #e5edf7; border-color: #cad7e6; }
QToolButton:disabled { color: #a6aeba; background: #eff1f4; }
QPushButton { background: #f7f9fc; border: 1px solid #c6d0dc; border-radius: 4px; padding: 7px 13px; }
QPushButton:hover { background: #e8f0fa; }
QPushButton:disabled { color: #a8b0ba; background: #f1f3f6; border-color: #e2e6ec; }
QDockWidget { font-weight: 600; }
QDockWidget::title { background: #dce4ee; padding: 8px; }
QTreeWidget { border: 0; background: #fbfcfe; outline: 0; }
QTreeWidget::item { padding: 5px 2px; }
QTreeWidget::item:selected { background: #dceafa; color: #163f6b; }
QDoubleSpinBox, QComboBox { padding: 5px; border: 1px solid #cbd4df; background: white; border-radius: 3px; }
QPlainTextEdit { border: 0; background: #f9fbfd; font-family: Consolas; font-size: 11px; }
QStatusBar { background: #172b43; color: #e2edf7; }
QStatusBar QLabel { color: #e2edf7; padding: 3px 10px; }
QSplitter::handle { background: #d5dde7; height: 3px; width: 3px; }
"""


class SimulatorWindow(QMainWindow):
    def __init__(self, workspace: Workspace):
        super().__init__()
        self.workspace = workspace
        self.project_id = None
        self.loaded_view = None
        self.tree_signature = None
        self.project_revision = None
        self.dirty = False
        self.setWindowTitle("Doo Doo Dynamics Simulator — Structural Workbench")
        self.setMinimumSize(1100, 760)
        available = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1520, available.width() - 40), min(980, available.height() - 50))
        self.setStyleSheet(STYLE)
        self.build_menu()
        self.build_center()
        self.build_outline()
        self.build_toolbox()
        self.build_logs()
        self.status_label = QLabel("Ready")
        self.statusBar().addWidget(self.status_label, 1)
        self.statusBar().addPermanentWidget(QLabel("SI units  ·  CalculiX 2.23  ·  Local MCP workspace"))
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(700)
        self.refresh()

    def build_menu(self):
        file_menu = self.menuBar().addMenu("File")
        for title, handler in (("New project", self.new_project), ("Import CAD…", self.import_cad),
                               ("Create test plate", self.create_demo)):
            action = QAction(title, self)
            action.triggered.connect(lambda checked=False, callback=handler: self.safe(callback))
            file_menu.addAction(action)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)
        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction("About", lambda: QMessageBox.information(
            self, "Doo Doo Dynamics Simulator",
            "Independent open-source structural workbench\nGPL-2.0-or-later\n\n"
            "Single-solid, linear static prototype. Grey controls are planned and unavailable.\n"
            "Built with Gmsh, CalculiX and Qt for Python. Independent of Ansys."))

    def ribbon_button(self, layout, title, description, handler=None):
        button = QToolButton()
        button.setText(title + "\n" + description)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        button.setMinimumHeight(64)
        if handler:
            button.clicked.connect(lambda checked=False: self.safe(handler))
        else:
            button.setEnabled(False)
            button.setToolTip("Planned — not implemented")
        layout.addWidget(button)
        return button

    def build_center(self):
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        banner = QLabel("   DD   /   DOO DOO DYNAMICS SIMULATOR                         STRUCTURAL WORKBENCH")
        banner.setStyleSheet("background:#20364f;color:#f4f7fb;padding:14px 8px;font-size:15px;font-weight:600;border-bottom:3px solid #d99530")
        layout.addWidget(banner)
        self.ribbon = QTabWidget()
        self.ribbon.setFixedHeight(116)
        groups = {
            "Home": [("New project", "Workspace", self.new_project), ("Import CAD", "STEP / IGES / BREP", self.import_cad),
                     ("Test plate", "Built-in example", self.create_demo), ("Generate mesh", "Gmsh tetrahedra", self.mesh),
                     ("Solve", "Static structural", self.solve), ("Results", "Displacement", lambda: self.change_view("results"))],
            "Geometry": [("Import CAD", "One closed solid", self.import_cad), ("Test plate", "100 × 40 × 5 mm", self.create_demo),
                         ("CAD editing", "Planned" , None), ("Assemblies", "Planned", None)],
            "Mesh": [("Generate mesh", "Linear tetrahedra", self.mesh), ("Show mesh", "Surface edges", lambda: self.change_view("mesh")),
                     ("Adaptive refinement", "Planned", None), ("Quadratic elements", "Planned", None)],
            "Environment": [("Apply settings", "Material / axial force", self.save_parameters),
                            ("Face selection", "Planned", None), ("Contact", "Planned", None)],
            "Solution": [("Solve", "CalculiX static", self.solve), ("Displacement", "Current result", lambda: self.change_view("results")),
                         ("Stress contours", "Planned", None), ("Modal", "Planned", None), ("Thermal", "Planned", None)],
            "Automation": [("MCP status", "12 local tools", self.show_mcp), ("Refresh", "Shared workspace", self.refresh),
                           ("Remote access", "Planned", None)],
        }
        for name, buttons in groups.items():
            page = QWidget()
            row = QHBoxLayout(page)
            row.setContentsMargins(10, 2, 10, 2)
            for title, description, handler in buttons:
                self.ribbon_button(row, title, description, handler)
            row.addStretch()
            self.ribbon.addTab(page, name)
        layout.addWidget(self.ribbon)
        tools = QWidget()
        tools.setStyleSheet("background:white;border-bottom:1px solid #d3dde7")
        tool_row = QHBoxLayout(tools)
        tool_row.setContentsMargins(12, 5, 12, 5)
        self.viewport_title = QLabel("MODEL VIEWPORT")
        self.viewport_title.setStyleSheet("font-weight:600;color:#53667c")
        tool_row.addWidget(self.viewport_title, 1)
        for title, script in (("Fit view", "resetViewport()"), ("Edges", "setEdgeVisibility(!edgeVisibility)")):
            button = QPushButton(title)
            button.clicked.connect(lambda checked=False, command=script: self.view.page().runJavaScript(command))
            tool_row.addWidget(button)
        tool_row.addWidget(QLabel("Deformation"))
        self.deformation = QComboBox()
        self.deformation.addItems(["True scale", "100×", "500×", "1500×"])
        self.deformation.setCurrentIndex(2)
        self.deformation.currentIndexChanged.connect(self.apply_view_options)
        tool_row.addWidget(self.deformation)
        layout.addWidget(tools)
        self.view = QWebEngineView()
        self.view.setAccessibleName("Simulation 3D viewport")
        self.view.loadFinished.connect(self.apply_view_options)
        self.view.setHtml(self.empty_view())
        layout.addWidget(self.view, 1)
        self.legend = QLabel("  Import a solid or create the test plate to begin.  ·  Drag in the viewport to rotate.")
        self.legend.setStyleSheet("background:#fff;padding:9px;color:#55697e;border-top:1px solid #d3dde7")
        layout.addWidget(self.legend)
        self.setCentralWidget(central)

    def empty_view(self):
        return """<html><body style="margin:0;background:radial-gradient(#fff,#dfe7f0);font-family:Segoe UI;color:#243b55;display:grid;place-items:center;height:100vh">
        <div style="text-align:center"><div style="font-size:54px;font-weight:700;color:#b6c6d7">DD</div>
        <h2>Your next simulation starts here</h2><p style="color:#6d8197">New project → Import CAD or Test plate → Generate mesh → Solve</p>
        <p style="color:#8c9bab;font-size:12px">Static structural · Gmsh meshing · CalculiX solver · MCP automation</p></div></body></html>"""

    def build_outline(self):
        dock = QDockWidget("Outline / Model", self)
        dock.setObjectName("outline")
        dock.setMinimumWidth(290)
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemClicked.connect(self.select_tree_item)
        splitter.addWidget(self.tree)
        details = QWidget()
        layout = QVBoxLayout(details)
        heading = QLabel("DETAILS OF STATIC STRUCTURAL")
        heading.setStyleSheet("background:#e0e7f0;padding:10px;font-weight:600")
        layout.addWidget(heading)
        form = QFormLayout()
        self.fields = {}
        definitions = [("mesh_size_m", "Mesh size (mm)", 0.001, 100000, 4, 3),
                       ("cad_scale", "CAD scale to m", 0.000001, 100000, 1, 6),
                       ("young_Pa", "Young's E (GPa)", 0.001, 100000, 210, 3),
                       ("poisson", "Poisson ratio", -0.999, 0.499, 0.3, 3),
                       ("load_N", "Axial force (N)", -1e12, 1e12, 1000, 3)]
        for key, label, minimum, maximum, value, decimals in definitions:
            field = QDoubleSpinBox()
            field.setRange(minimum, maximum)
            field.setDecimals(decimals)
            field.setValue(value)
            field.setKeyboardTracking(False)
            field.setAccessibleName(label)
            field.valueChanged.connect(self.mark_dirty)
            self.fields[key] = field
            form.addRow(label, field)
        layout.addLayout(form)
        note = QLabel("Fixed support: X-min face\nAxial force: X-max face\nSingle solid · isotropic elasticity")
        note.setStyleSheet("color:#6f8094;padding:6px")
        layout.addWidget(note)
        self.apply_button = QPushButton("Apply settings")
        self.apply_button.clicked.connect(lambda: self.safe(self.save_parameters))
        layout.addWidget(self.apply_button)
        self.details_note = QLabel("SI units are stored with every job.")
        self.details_note.setWordWrap(True)
        self.details_note.setStyleSheet("color:#8290a2;padding:6px")
        layout.addWidget(self.details_note)
        layout.addStretch()
        splitter.addWidget(details)
        splitter.setSizes([320, 400])
        dock.setWidget(splitter)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

    def build_toolbox(self):
        dock = QDockWidget("Analysis Toolbox", self)
        dock.setObjectName("toolbox")
        dock.setMinimumWidth(195)
        contents = QWidget()
        layout = QVBoxLayout(contents)
        layout.addWidget(QLabel("AVAILABLE NOW"))
        for label, callback in (("Static Structural", self.solve), ("Generate Mesh", self.mesh), ("MCP Controls", self.show_mcp)):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, handler=callback: self.safe(handler))
            layout.addWidget(button)
        heading = QLabel("PLANNED FEATURES")
        heading.setStyleSheet("margin-top:18px;color:#8390a2")
        layout.addWidget(heading)
        for feature in CAPABILITIES:
            if not feature["enabled"]:
                button = QPushButton(feature["name"])
                button.setEnabled(False)
                button.setToolTip(feature["detail"])
                layout.addWidget(button)
        label = QLabel("Grey controls are unavailable.\nThey do not run placeholder solves.")
        label.setWordWrap(True)
        label.setStyleSheet("color:#8b98a8;font-size:11px;padding-top:10px")
        layout.addWidget(label)
        layout.addStretch()
        dock.setWidget(contents)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    def build_logs(self):
        dock = QDockWidget("Messages / Solver Jobs", self)
        dock.setObjectName("messages")
        self.messages = QPlainTextEdit()
        self.messages.setReadOnly(True)
        self.messages.setMaximumBlockCount(3000)
        dock.setWidget(self.messages)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
        self.resizeDocks([dock], [150], Qt.Orientation.Vertical)

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

    def new_project(self):
        name, accepted = QInputDialog.getText(self, "New simulation project", "Project name:")
        if accepted and name.strip():
            project = self.workspace.create_project(name)
            self.workspace.show_project(project["id"])
            self.dirty = False

    def create_demo(self):
        project = self.workspace.create_project("Perforated plate / " + datetime.now().strftime("%H:%M:%S"))
        self.workspace.show_project(project["id"], "mesh")
        self.workspace.start_job(project["id"], "example")
        self.dirty = False

    def import_cad(self):
        project_id = self.require_project()
        path, _ = QFileDialog.getOpenFileName(self, "Import a single CAD solid", "", "CAD (*.step *.stp *.iges *.igs *.brep)")
        if path:
            self.workspace.import_cad(project_id, path)
            self.workspace.show_project(project_id, "geometry")
            self.workspace.start_job(project_id, "mesh")
            self.dirty = False

    def mark_dirty(self):
        self.dirty = True
        self.details_note.setText("Settings changed. Apply settings or Solve to use them.")

    def save_parameters(self):
        parameters = {key: field.value() for key, field in self.fields.items()}
        parameters["mesh_size_m"] /= 1000
        parameters["young_Pa"] *= 1e9
        self.workspace.set_parameters(self.require_project(), parameters)
        self.dirty = False
        self.details_note.setText("Settings saved. Prior results are retained in job history.")

    def mesh(self):
        self.save_parameters()
        self.workspace.start_job(self.require_project(), "mesh")
        self.workspace.show_project(self.project_id, "mesh")

    def solve(self):
        self.save_parameters()
        self.workspace.start_job(self.require_project(), "solve")
        self.workspace.show_project(self.project_id, "results")

    def change_view(self, view):
        self.workspace.show_project(self.require_project(), view)

    def select_tree_item(self, item, column):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data:
            if data[0] != self.project_id:
                self.dirty = False
            self.workspace.show_project(*data)
            self.refresh()

    def show_mcp(self):
        QMessageBox.information(self, "Local MCP automation",
                                "12 stdio MCP tools share this desktop workspace.\n\n"
                                "Create/import projects, set inputs, mesh, solve, inspect jobs/results and select views.\n\n"
                                "Workspace: " + str(self.workspace.root) + "\n\n"
                                "Server: python -m opensim.mcp_server\nSee docs/DESKTOP_AND_MCP.md for client setup.")

    def apply_view_options(self, *args):
        state = self.workspace.ui_state()
        mode = state["view"]
        scale = [1, 100, 500, 1500][self.deformation.currentIndex()]
        self.view.page().runJavaScript(
            f"if(typeof setViewportMode==='function'){{setViewportMode({json.dumps(mode)});setDeformationScale({scale});}}")

    def refresh(self):
        self.workspace.heartbeat()
        state = self.workspace.ui_state()
        projects = self.workspace.list_projects()
        if not state["project_id"] and projects:
            state = self.workspace.show_project(projects[0]["id"])
        selected = state["project_id"]
        if selected != self.project_id:
            self.project_id = selected
            self.project_revision = None
            self.dirty = False
        project = self.workspace.get_project(selected) if selected else None
        jobs = self.workspace.list_jobs(selected) if selected else []
        signature = [(entry["id"], entry["name"], entry["revision"]) for entry in projects], [(job["id"], job["status"]) for job in jobs], selected
        if signature != self.tree_signature:
            self.tree_signature = signature
            self.tree.clear()
            for entry in projects:
                root = QTreeWidgetItem([entry["name"]])
                root.setData(0, Qt.ItemDataRole.UserRole, (entry["id"], "geometry"))
                self.tree.addTopLevelItem(root)
                for label, view in (("Geometry (single solid)", "geometry"), ("Mesh / C3D4", "mesh"),
                                    ("Static Structural", "geometry"), ("  Fixed Support / X-min", "geometry"),
                                    ("  Force / X-max", "geometry"), ("Solution / Displacement", "results")):
                    child = QTreeWidgetItem([label])
                    child.setData(0, Qt.ItemDataRole.UserRole, (entry["id"], view))
                    root.addChild(child)
                root.setExpanded(entry["id"] == selected)
                if entry["id"] == selected:
                    self.tree.setCurrentItem(root)
        if project and not self.dirty and self.project_revision != project["revision"]:
            for key, field in self.fields.items():
                value = project["parameters"][key]
                if key == "mesh_size_m":
                    value *= 1000
                if key == "young_Pa":
                    value /= 1e9
                blocker = QSignalBlocker(field)
                field.setValue(value)
                del blocker
            self.project_revision = project["revision"]
        active = next((job for job in jobs if job["status"] in {"queued", "running"}), None)
        self.apply_button.setEnabled(bool(project) and not active)
        for field in self.fields.values():
            field.setEnabled(bool(project) and not active)
        if project:
            self.status_label.setText(f"{project['name']}  |  " + (f"{active['kind'].title()} {active['status']}…" if active else "Ready"))
            artifact = self.workspace.current_artifact(selected, state["view"])
            view_key = str(artifact), state["view"]
            if view_key != self.loaded_view:
                self.loaded_view = view_key
                self.viewport_title.setText(project["name"].upper() + "  /  " + state["view"].upper())
                if artifact:
                    url = QUrl.fromLocalFile(str(artifact))
                    url.setQuery("desktop=1")
                    self.view.setUrl(url)
                else:
                    self.view.setHtml(self.empty_view())
            output = []
            for job in jobs[:8]:
                output.append(f"[{job['status'].upper()}] {job['kind']}  ·  {job['id'][:8]}  ·  input revision {job['revision']}")
                if job["error"]:
                    output.append("  " + job["error"])
                if job["result"]:
                    result = job["result"]
                    output.append(f"  {result['nodes']:,} nodes · {result['tetrahedra']:,} tetrahedra")
                    if "maximum_displacement_m" in result:
                        output.append(f"  Maximum displacement: {result['maximum_displacement_m'] * 1e6:.4f} µm  |  "
                                      f"Reaction X: {result['reaction_N'][0]:.4f} N  |  "
                                      f"Force imbalance: {result['relative_force_imbalance']:.2e}")
            text = "\n".join(output) or "No jobs yet. Import CAD or create a test plate."
            if self.messages.toPlainText() != text:
                self.messages.setPlainText(text)
            try:
                if state["view"] != "results":
                    raise ValueError("Geometry or mesh view")
                summary = self.workspace.get_results(selected)["summary"]
                self.legend.setText(f"  Displacement |U|: 0 → {summary['maximum_displacement_m'] * 1e6:.4f} µm   ·   "
                                    f"{summary['tetrahedra']:,} elements   ·   Display deformation is exaggerated   ·   Drag to rotate")
            except ValueError:
                label = "No solved result for current settings" if state["view"] == "results" else "Undeformed geometry / mesh preview"
                self.legend.setText(f"  {label}   ·   Drag to rotate")


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
