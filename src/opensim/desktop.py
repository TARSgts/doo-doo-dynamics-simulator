import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import time

from PySide6.QtCore import Qt, QPointF, QSignalBlocker, QTimer, QUrl
from PySide6.QtGui import QAction, QFont, QIcon, QTextDocument, QWheelEvent
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDockWidget, QDoubleSpinBox,
                               QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QInputDialog, QLineEdit,
                               QLabel, QMainWindow, QMenuBar, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
                               QScrollArea, QSizePolicy, QSpinBox, QSplitter, QTabWidget, QToolButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from opensim.workspace import CAPABILITIES, Workspace
from opensim.results import refresh_viewer
from opensim.cat_language import cat_text
from opensim.app_identity import ICON_PATH, set_process_identity
from opensim.job_progress import STAGE_LABELS, elapsed_label
from opensim.hover_help import FIELD_HELP, BUTTON_HELP
from opensim.load_settings import NORMAL_AXES


STYLE = """
QMainWindow { background: #e8edf3; }
QWidget { color: #27374a; font-family: 'Segoe UI'; font-size: 12px; }
QToolTip { color:#27374a; background:#fffbe8; border:1px solid #9aaec7; padding:6px; }
QMenuBar { background: #172b43; color: #e7eff8; padding: 4px; }
QMenuBar::item:selected { background: #304961; }
QMenu { background: white; }
QTabWidget::pane { border: 0; background: #f6f8fb; }
QTabBar::tab { background: #e5eaf1; padding: 9px 19px; color: #45576c; }
QTabBar::tab:selected { background: #fff; color: #1c344f; border-top: 3px solid #d99530; }
QTabWidget#CommandRibbon QTabBar::tab { padding:5px 13px; }
QTabWidget#CommandRibbon QToolButton { padding:5px 10px; }
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
QProgressBar { border:1px solid #9aaec7; border-radius:4px; background:#dbe5f0; text-align:center; color:#27374a; }
QProgressBar::chunk { background:#d99b35; border-radius:3px; }
QSplitter::handle { background: #d5dde7; }
QSplitter::handle:hover { background:#d99530; }
QWidget#ViewportTools { background:#f8fafc; }
QLabel#DetailsHeading { background:#dce5ef; padding:9px; font-weight:600; }
QLabel#ResultCard { background:white; color:#31485f; border:1px solid #d9e2ec; padding:5px 10px; border-radius:5px; }
QWidget#DetailsPanel, QScrollArea#PropertiesScroll { background:#f2f5fa; }
QScrollBar:vertical { background:#e0e7f0; width:10px; margin:0; }
QScrollBar::handle:vertical { background:#9caec5; min-height:24px; border-radius:4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QWidget#ApplicationHeader { background:#172b43; border-bottom:2px solid #d99530; }
QLabel#ApplicationTitle { color:#edf4ff; font-size:14px; font-weight:600; background:transparent; }
"""

DARK_STYLE = """
QMainWindow, QWidget { background:#121b2b; color:#d8e4f1; }
QToolTip { color:#e6eefb; background:#22334a; border:1px solid #6b819c; }
QMenuBar, QStatusBar { background:#0d1420; color:#dce6f4; }
QProgressBar { border-color:#405674; background:#17263b; color:#e6eefb; }
QMenu { background:#1c293d; border:1px solid #35445b; }
QMenu::item:selected { background:#2e4565; }
QTabWidget::pane { background:#182538; }
QTabBar::tab { background:#142034; color:#9faec2; }
QTabBar::tab:selected { background:#20324b; color:#f1c576; border-top-color:#dba24a; }
QToolButton { background:#182538; color:#d7e4f6; }
QToolButton:hover { background:#263c59; border-color:#405776; }
QToolButton:disabled, QPushButton:disabled { color:#6a7a92; background:#182234; border-color:#243248; }
QPushButton { color:#d5e4f7; background:#22334a; border-color:#3a506c; }
QPushButton:hover { background:#304a6a; }
QDockWidget::title { background:#1c2a3f; color:#cfdbed; }
QTreeWidget { background:#121d2e; color:#b9cbe0; }
QTreeWidget::item:selected { background:#264364; color:#eef6ff; }
QDoubleSpinBox, QComboBox { background:#15243a; color:#e6eefb; border-color:#3a4e68; }
QComboBox QAbstractItemView { background:#1d2e45; color:#e4eefb; selection-background-color:#36567a; }
QPlainTextEdit { background:#0e1827; color:#9eb6cf; }
QSplitter::handle { background:#28384e; }
QSplitter::handle:hover { background:#dba24a; }
QScrollArea { border:0; background:#121b2b; }
QLabel#DetailsHeading { background:#1c2c44; color:#c3d5ec; }
QWidget#ViewportTools { background:#17263b; }
QLabel#ResultCard { background:#1b2c43; color:#c5ddf5; border-color:#31475f; }
QWidget#DetailsPanel, QScrollArea#PropertiesScroll { background:#121b2b; }
QScrollBar:vertical { background:#19273b; }
QScrollBar::handle:vertical { background:#425c7e; }
QWidget#ApplicationHeader { background:#0d1420; }
"""


def forward_wheel_to_panel(control, event):
    parent = control.parentWidget()
    while parent is not None and not isinstance(parent, QScrollArea):
        parent = parent.parentWidget()
    if parent is None:
        event.ignore()
        return
    viewport = parent.viewport()
    position = QPointF(viewport.mapFromGlobal(event.globalPosition().toPoint()))
    forwarded = QWheelEvent(position, event.globalPosition(), event.pixelDelta(), event.angleDelta(), event.buttons(),
                            event.modifiers(), event.phase(), event.inverted(), event.source(), event.pointingDevice())
    QApplication.sendEvent(viewport, forwarded)
    event.accept()


class ScrollSafeDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event):
        forward_wheel_to_panel(self, event)


class ScrollSafeSpinBox(QSpinBox):
    def wheelEvent(self, event):
        forward_wheel_to_panel(self, event)


class SimulatorWindow(QMainWindow):
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
        self.stop_buttons = []
        self.opened_at = time.time()
        self.shown_convergence = set()
        self.reference_dialogs = {}
        self.face_pick_session = None
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
        self.timer.timeout.connect(self.refresh)
        self.timer.start(700)
        self.refresh()

    def build_menu(self):
        header = QWidget()
        header.setObjectName("ApplicationHeader")
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(8, 4, 10, 4)
        self.application_menu = QMenuBar()
        self.application_menu.setNativeMenuBar(False)
        header_row.addWidget(self.application_menu)
        self.application_title = QLabel("DOO DOO DYNAMICS  /  SIMULATOR")
        self.application_title.setObjectName("ApplicationTitle")
        self.application_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_row.addWidget(self.application_title, 1)
        self.cat_button = QPushButton("Cat mode: OFF")
        self.cat_button.setCheckable(True)
        self.cat_button.setAccessibleName("Cat mode joke translation")
        self.cat_button.toggled.connect(lambda checked: self.set_language("cat" if checked else "en"))
        header_row.addWidget(self.cat_button)
        self.theme_button = QPushButton("Light mode")
        self.theme_button.setAccessibleName("Toggle dark mode")
        self.theme_button.clicked.connect(lambda: self.set_theme("light" if self.theme == "dark" else "dark"))
        header_row.addWidget(self.theme_button)
        self.setMenuWidget(header)
        file_menu = self.application_menu.addMenu("File")
        for title, handler in (("New project", self.new_project), ("Import CAD…", self.import_cad)):
            action = QAction(title, self)
            action.triggered.connect(lambda checked=False, callback=handler: self.safe(callback))
            file_menu.addAction(action)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)
        help_menu = self.application_menu.addMenu("Help")
        view_menu = self.application_menu.addMenu("View")
        self.dark_action = QAction("Dark mode", self)
        self.dark_action.setCheckable(True)
        self.dark_action.toggled.connect(lambda checked: self.set_theme("dark" if checked else "light"))
        view_menu.addAction(self.dark_action)
        self.cat_action = QAction("Cat mode (joke translation)", self)
        self.cat_action.setCheckable(True)
        self.cat_action.toggled.connect(lambda checked: self.set_language("cat" if checked else "en"))
        view_menu.addAction(self.cat_action)
        help_menu.addAction("About", lambda: QMessageBox.information(
            self, "Doo Doo Dynamics Simulator",
            "Independent open-source structural workbench\nGPL-2.0-or-later\n\n"
            "Single-solid linear static and modal prototype. Grey controls are planned and unavailable.\n"
            "Built with Gmsh, CalculiX and Qt for Python. Independent of Ansys."))

    def make_stop_button(self):
        button = QPushButton("Stop computing")
        button.setAccessibleName("Stop the running simulation job")
        button.setToolTip(BUTTON_HELP["Stop computing"])
        button.setEnabled(False)
        button.clicked.connect(lambda checked=False: self.safe(self.stop_computing))
        self.stop_buttons.append(button)
        return button

    def ribbon_button(self, layout, title, description, handler=None):
        button = QToolButton()
        button.setText(title)
        button.setAccessibleDescription(description)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        button.setMinimumHeight(30)
        if handler:
            button.setToolTip(BUTTON_HELP[title])
            button.clicked.connect(lambda checked=False: self.safe(handler))
            if handler in (self.mesh, self.solve, self.modal, self.convergence, self.import_cad) or title in {"Pick fixed support", "Pick force faces"}:
                self.analysis_buttons.append(button)
        else:
            button.setEnabled(False)
            button.setToolTip("Planned — not implemented")
        layout.addWidget(button)
        return button

    def install_hover_help(self):
        for button in self.findChildren(QPushButton):
            if button.text() in BUTTON_HELP:
                button.setToolTip(BUTTON_HELP[button.text()])
        for key, control in {**self.fields, **self.selectors}.items():
            control.setToolTip(FIELD_HELP[key])
        self.theme_button.setToolTip("Switch between light and dark colors without changing your model or results.")
        self.deformation.setToolTip("Magnify movement for viewing only. True scale shows actual displacement; Auto targets 10% of model size.")
        self.camera.setToolTip("View the model from a corner, the front, above, or the flipped front. This does not rotate the model or loads.")
        self.result_component.setToolTip("Choose total movement, movement along X/Y/Z, or von Mises stress for the color display.")
        self.modal_selector.setToolTip("Select a natural frequency and its vibration shape. Shape amplitude is normalized, not a predicted displacement.")
        for action in self.application_menu.findChildren(QAction):
            title = action.text().rstrip("…")
            if title in BUTTON_HELP:
                action.setToolTip(BUTTON_HELP[title])

    def build_center(self):
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.ribbon = QTabWidget()
        self.ribbon.setObjectName("CommandRibbon")
        self.ribbon.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        groups = {
            "Home": [("New project", "Workspace", self.new_project), ("Import CAD", "STEP / STL / OBJ / 3MF", self.import_cad),
                     ("Generate mesh", "Gmsh tetrahedra", self.mesh),
                     ("Solve", "Static structural", self.solve), ("Results", "Displacement", lambda: self.change_view("results"))],
            "Geometry": [("Import CAD", "One closed solid", self.import_cad),
                         ("CAD editing", "Planned" , None), ("Assemblies", "Planned", None)],
            "Mesh": [("Generate mesh", "Linear tetrahedra", self.mesh), ("Show mesh", "Surface edges", lambda: self.change_view("mesh")),
                     ("Adaptive refinement", "Planned", None)],
            "Environment": [("Apply settings", "Material / axial force", self.save_parameters),
                            ("Pick fixed support", "Click model faces", lambda: self.begin_face_picking("support")),
                            ("Pick force faces", "Click model faces", lambda: self.begin_face_picking("load")), ("Contact", "Planned", None)],
            "Solution": [("Solve", "CalculiX static", self.solve), ("Displacement", "Current result", lambda: self.change_view("results")),
                         ("Stress contours", "Recovered von Mises", self.show_stress), ("Convergence", "Mesh refinement study", self.convergence),
                         ("Convergence report", "Latest study", self.show_convergence_report),
                         ("Modal", "Natural frequencies", self.modal), ("Thermal", "Planned", None)],
            "Automation": [("MCP status", "19 local tools", self.show_mcp), ("Refresh", "Shared workspace", self.refresh),
                           ("Remote access", "Planned", None)],
            "Examples": [("Test plate", "100 × 40 × 5 mm", self.create_demo),
                         ("Cantilever", "1 m tip-loaded beam", self.create_beam)],
            "Validation": [("Reference report", "Euler–Bernoulli study", self.show_validation),
                           ("Timoshenko", "Bending + shear study", lambda: self.show_reference_report("timoshenko")),
                           ("Modal beam", "Frequency verification", lambda: self.show_reference_report("modal")),
                           ("Distributed load", "Uniform traction study", lambda: self.show_reference_report("distributed")),
                           ("Circular hole", "Kirsch stress study", lambda: self.show_reference_report("hole"))],
        }
        for name, buttons in groups.items():
            page = QWidget()
            row = QHBoxLayout(page)
            row.setContentsMargins(8, 2, 8, 2)
            row.setSpacing(4)
            for title, description, handler in buttons:
                self.ribbon_button(row, title, description, handler)
            row.addStretch()
            row.setSizeConstraint(QHBoxLayout.SizeConstraint.SetMinimumSize)
            scroller = QScrollArea()
            scroller.setWidgetResizable(True)
            scroller.setFrameShape(QScrollArea.Shape.NoFrame)
            scroller.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroller.setWidget(page)
            self.ribbon.addTab(scroller, name)
        self.update_ribbon_height()
        layout.addWidget(self.ribbon)
        card_panel = QWidget()
        card_row = QHBoxLayout(card_panel)
        card_row.setContentsMargins(8, 3, 8, 3)
        card_row.setSpacing(6)
        self.result_cards = []
        for caption in ("Maximum displacement", "Tip-section displacement", "Force balance"):
            card = QLabel(caption + "\n—")
            card.setObjectName("ResultCard")
            card_row.addWidget(card, 1)
            self.result_cards.append(card)
        layout.addWidget(card_panel)
        tools = QWidget()
        tools.setObjectName("ViewportTools")
        tool_row = QHBoxLayout(tools)
        tool_row.setContentsMargins(8, 2, 8, 2)
        self.viewport_title = QLabel("MODEL VIEWPORT")
        self.viewport_title.setWordWrap(True)
        tool_row.addWidget(self.viewport_title, 1)
        for title, script in (("Fit view", "resetViewport()"), ("Edges", "setEdgeVisibility(!edgeVisibility)")):
            button = QPushButton(title)
            button.clicked.connect(lambda checked=False, command=script: self.view.page().runJavaScript(command))
            tool_row.addWidget(button)
        tool_row.addWidget(QLabel("Deformation"))
        self.deformation = QComboBox()
        self.deformation.addItems(["Auto (10%)", "True scale", "10×", "100×", "500×"])
        self.deformation.setCurrentIndex(0)
        self.deformation.currentIndexChanged.connect(self.apply_view_options)
        tool_row.addWidget(self.deformation)
        self.camera = QComboBox()
        self.camera.addItems(["Iso", "Front XZ", "Top XY", "Front XZ · flipped"])
        self.camera.setToolTip("Camera orientation")
        self.camera.currentIndexChanged.connect(self.apply_camera)
        tool_row.addWidget(self.camera)
        self.result_component = QComboBox()
        self.result_component.addItems(["Total |U|", "Ux", "Uy", "Uz"])
        self.result_component.addItem("von Mises stress")
        self.result_component.currentIndexChanged.connect(self.apply_view_options)
        self.result_component.currentIndexChanged.connect(lambda: self.refresh())
        tool_row.addWidget(self.result_component)
        layout.addWidget(tools)
        self.pick_actions = QWidget()
        pick_layout = QHBoxLayout(self.pick_actions)
        pick_layout.setContentsMargins(8, 2, 8, 2)
        for title, callback in (("Save picked faces", self.save_picked_faces), ("Clear current faces", self.clear_picked_faces), ("Cancel picking", self.cancel_face_picking)):
            button = QPushButton(title)
            button.setToolTip(BUTTON_HELP[title])
            button.clicked.connect(lambda checked=False, action=callback: self.safe(action))
            pick_layout.addWidget(button)
        pick_layout.addStretch()
        layout.addWidget(self.pick_actions)
        self.pick_actions.hide()
        self.modal_tools = QWidget()
        modal_row = QHBoxLayout(self.modal_tools)
        modal_row.setContentsMargins(12, 4, 12, 4)
        modal_row.addWidget(QLabel("Mode"))
        self.modal_selector = QComboBox()
        self.modal_selector.setMinimumWidth(190)
        self.modal_selector.setMinimumContentsLength(20)
        self.modal_selector.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.modal_selector.setAccessibleName("Select mode shape")
        self.modal_selector.currentIndexChanged.connect(self.select_mode)
        modal_row.addWidget(self.modal_selector)
        self.animate_mode = QPushButton("Animate mode")
        self.animate_mode.setCheckable(True)
        self.animate_mode.toggled.connect(self.apply_view_options)
        modal_row.addWidget(self.animate_mode)
        modal_note = QLabel("Normalized shape · arbitrary amplitude · animation plays at 1 Hz")
        modal_note.setWordWrap(True)
        modal_row.addWidget(modal_note, 1)
        layout.addWidget(self.modal_tools)
        self.modal_tools.hide()
        self.view = QWebEngineView()
        self.view.setAccessibleName("Simulation 3D viewport")
        self.view.loadFinished.connect(self.apply_view_options)
        self.view.loadFinished.connect(self.apply_camera)
        self.view.setHtml(self.empty_view())
        layout.addWidget(self.view, 1)
        self.legend = QLabel("  Import a solid or create the test plate to begin.  ·  Drag in the viewport to rotate.")
        self.legend.setStyleSheet("background:#fff;padding:9px;color:#55697e;border-top:1px solid #d3dde7")
        layout.addWidget(self.legend)
        self.setCentralWidget(central)

    def update_ribbon_height(self):
        command_height = max(self.ribbon.widget(i).widget().sizeHint().height() for i in range(self.ribbon.count()))
        scroll_height = self.ribbon.widget(0).horizontalScrollBar().sizeHint().height()
        self.ribbon.setFixedHeight(self.ribbon.tabBar().sizeHint().height() + command_height + scroll_height + 4)

    def empty_view(self):
        return """<html><body style="margin:0;background:radial-gradient(#fff,#dfe7f0);font-family:Segoe UI;color:#243b55;display:grid;place-items:center;height:100vh">
        <div style="text-align:center"><div style="font-size:54px;font-weight:700;color:#b6c6d7">DD</div>
        <h2>Your next simulation starts here</h2><p style="color:#6d8197">New project → Import CAD → Generate mesh → Solve</p>
        <p style="color:#6d8197">Or open the Examples tab to try a plate or cantilever beam.</p>
        <p style="color:#8c9bab;font-size:12px">Static structural · Gmsh meshing · CalculiX solver · MCP automation</p></div>
        <script>function setTheme(theme){document.body.style.background=theme==='dark'?'radial-gradient(#22344f,#101827)':'radial-gradient(#fff,#dfe7f0)';document.body.style.color=theme==='dark'?'#dce9f9':'#243b55';}</script></body></html>"""

    def build_outline(self):
        dock = QDockWidget("Outline / Model", self)
        dock.setObjectName("outline")
        dock.setMinimumWidth(330)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setObjectName("ModelPropertiesSplitter")
        splitter.setHandleWidth(8)
        splitter.setChildrenCollapsible(False)
        self.tree = QTreeWidget()
        self.tree.setMinimumHeight(80)
        self.tree.setHeaderHidden(True)
        self.tree.itemClicked.connect(self.select_tree_item)
        splitter.addWidget(self.tree)
        details = QWidget()
        details.setObjectName("DetailsPanel")
        details.setMinimumWidth(0)
        layout = QVBoxLayout(details)
        heading = QLabel("DETAILS OF STATIC STRUCTURAL")
        self.details_heading = heading
        heading.setObjectName("DetailsHeading")
        heading.setWordWrap(True)
        layout.addWidget(heading)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.fields = {}
        definitions = [("mesh_size_m", "Mesh size (mm)", 0.001, 100000, 4, 3),
                       ("cad_scale", "CAD scale to m", 0.000001, 100000, 1, 6),
                       ("young_Pa", "Young's E (GPa)", 0.001, 100000, 210, 3),
                       ("poisson", "Poisson ratio", -0.999, 0.499, 0.3, 3),
                       ("density_kg_m3", "Density (kg/m³)", 0.001, 1e9, 7850, 3),
                       ("load_N", "Total force (N)", -1e12, 1e12, 1000, 3)]
        for key, label, minimum, maximum, value, decimals in definitions:
            field = ScrollSafeDoubleSpinBox()
            field.setRange(minimum, maximum)
            field.setDecimals(decimals)
            field.setValue(value)
            field.setKeyboardTracking(False)
            field.setMinimumWidth(100)
            field.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            field.setAccessibleName(label)
            field.valueChanged.connect(self.mark_dirty)
            self.fields[key] = field
            form.addRow(label, field)
        layout.addLayout(form)
        mode_count = ScrollSafeSpinBox()
        mode_count.setRange(1, 30)
        mode_count.setValue(6)
        mode_count.setAccessibleName("Requested modes")
        mode_count.setMinimumWidth(100)
        mode_count.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        mode_count.valueChanged.connect(self.mark_dirty)
        self.fields["mode_count"] = mode_count
        form.addRow("Requested modes", mode_count)
        levels = ScrollSafeSpinBox()
        levels.setRange(3, 6)
        levels.setValue(4)
        levels.setAccessibleName("Convergence meshes")
        for key, label, control in (("convergence_levels", "Convergence meshes", levels),
                                    ("convergence_ratio", "Refinement ratio", ScrollSafeDoubleSpinBox()),
                                    ("convergence_tolerance_percent", "Converged below (%)", ScrollSafeDoubleSpinBox())):
            if isinstance(control, QDoubleSpinBox):
                control.setRange(*((1.15, 2.5) if key == "convergence_ratio" else (0.01, 50)))
                control.setDecimals(2)
                control.setSingleStep(0.05 if key == "convergence_ratio" else 0.5)
                control.setValue(1.4 if key == "convergence_ratio" else 2.0)
                control.setKeyboardTracking(False)
                control.setAccessibleName(label)
            control.setMinimumWidth(100)
            control.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            control.valueChanged.connect(self.mark_dirty)
            self.fields[key] = control
            form.addRow(label, control)
        self.selectors = {}
        for key, label, options in (
            ("element_order", "Elements", [("Linear · C3D4", 1), ("Quadratic · C3D10", 2)]),
            ("load_axis", "Force direction", [("X · axial", "x"), ("Y · transverse", "y"), ("Z · transverse", "z"),
                                               ("Perpendicular · inward", "normal-in"), ("Perpendicular · outward", "normal-out")]),
            ("load_kind", "Force application", [("End face · equal nodes", "face"), ("Tip center · point", "point"), ("Uniform surface traction", "traction")]),
            ("load_surface", "Traction surface", [(f"{axis.upper()}-{side}", f"{axis}-{side}") for axis in "xyz" for side in ("min", "max")]),
            ("convergence_target", "Convergence target", [("Max displacement", "displacement"), ("Loaded-area displacement", "response"),
                                                           ("Max von Mises stress", "stress")])):
            selector = QComboBox()
            selector.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            selector.setMinimumContentsLength(10)
            selector.setMinimumWidth(100)
            selector.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            for text, value in options:
                selector.addItem(text, value)
            selector.currentIndexChanged.connect(self.mark_dirty)
            form.addRow(label, selector)
            self.selectors[key] = selector
        for key, control in {**self.fields, **self.selectors}.items():
            label_widget = form.labelForField(control)
            label_widget.setToolTip(FIELD_HELP[key])
            label_widget.setWordWrap(True)
            label_widget.setMinimumWidth(0)
            label_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        note = QLabel("Default support: X-min face. Selected regions override defaults.\nTraction: total force (N) spread uniformly over the selected surface.\nBounding-plane selector is used when no load region is set.\nModal: no loads or prestress.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#6f8094;padding:6px")
        layout.addWidget(note)
        self.apply_button = QPushButton("Apply settings")
        self.normal_load_note = QLabel("Perpendicular loading follows each surface's local normal. Positive force follows inward/outward; negative reverses it. On curved or multiple faces, the entered force is the sum of local magnitudes, not the net force.")
        self.normal_load_note.setWordWrap(True)
        layout.addWidget(self.normal_load_note)
        self.normal_load_note.hide()
        self.apply_button.clicked.connect(lambda: self.safe(self.save_parameters))
        layout.addWidget(self.apply_button)
        for title, mode in (("Pick fixed support", "support"), ("Pick force faces", "load")):
            button = QPushButton(title)
            button.clicked.connect(lambda checked=False, role=mode: self.safe(lambda: self.begin_face_picking(role)))
            button.setToolTip(BUTTON_HELP[title])
            self.analysis_buttons.append(button)
            layout.addWidget(button)
        self.pick_note = QLabel("Pick faces on the model, or enter face IDs in Support / load regions.")
        self.pick_note.setWordWrap(True)
        layout.addWidget(self.pick_note)
        self.region_button = QPushButton("Support / load regions…")
        self.region_button.setMinimumWidth(100)
        self.region_button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.region_button.clicked.connect(lambda: self.safe(self.edit_regions))
        self.analysis_buttons.append(self.region_button)
        layout.addWidget(self.region_button)
        self.region_note = QLabel("Support: X-min default. Load: selected bounding plane.")
        self.region_note.setWordWrap(True)
        layout.addWidget(self.region_note)
        self.details_note = QLabel("SI units are stored with every job.")
        self.details_note.setWordWrap(True)
        self.details_note.setStyleSheet("color:#8290a2;padding:6px")
        layout.addWidget(self.details_note)
        layout.addStretch()
        scroll = QScrollArea()
        scroll.setObjectName("PropertiesScroll")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(100)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        scroll.setWidget(details)
        splitter.addWidget(scroll)
        splitter.handle(1).setCursor(Qt.CursorShape.SplitVCursor)
        splitter.handle(1).setToolTip("Drag up or down to resize the model tree and settings panel.")
        splitter.setSizes([220, 480])
        dock.setWidget(splitter)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

    def build_toolbox(self):
        dock = QDockWidget("Analysis Toolbox", self)
        dock.setObjectName("toolbox")
        dock.setMinimumWidth(195)
        contents = QWidget()
        layout = QVBoxLayout(contents)
        layout.addWidget(QLabel("AVAILABLE NOW"))
        for label, callback in (("Static Structural", self.solve), ("Convergence study", self.convergence), ("Modal analysis", self.modal),
                                ("Generate Mesh", self.mesh), ("MCP Controls", self.show_mcp)):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, handler=callback: self.safe(handler))
            layout.addWidget(button)
            if callback in (self.solve, self.modal, self.mesh, self.convergence):
                self.analysis_buttons.append(button)
        layout.addWidget(self.make_stop_button())
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
            project = self.workspace.create_project(name)
            self.workspace.show_project(project["id"])
            self.dirty = False

    def create_demo(self):
        project = self.workspace.create_project("Perforated plate / " + datetime.now().strftime("%H:%M:%S"))
        self.workspace.show_project(project["id"], "mesh")
        self.workspace.start_job(project["id"], "example")
        self.dirty = False

    def create_beam(self):
        from opensim.validation import BEAM_PARAMETERS
        project = self.workspace.create_project("Cantilever beam / " + datetime.now().strftime("%H:%M:%S"))
        self.workspace.set_parameters(project["id"], BEAM_PARAMETERS)
        self.workspace.show_project(project["id"], "mesh")
        self.workspace.start_job(project["id"], "example", example="cantilever_beam")
        self.dirty = False

    def show_validation(self):
        report_path = Path(__file__).resolve().parents[2] / "docs" / "cantilever" / "report.json"
        if not report_path.is_file():
            raise ValueError("Run open-sim validate-cantilever --out <new folder> to produce the validation study")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        fine = report["cases"][-1]
        QMessageBox.information(self, "Published reference benchmark",
                                f"1 m × 20 mm × 20 mm beam · 10 N tip force\n\n"
                                f"Euler–Bernoulli: {report['euler_bernoulli_tip_z_m'] * 1000:.6f} mm\n"
                                f"C3D10 tip-section mean: {fine['tip_mean_z_m'] * 1000:.6f} mm\n"
                                f"Error: {fine['tip_error_fraction'] * 100:.4f}%\n"
                                f"Final mesh change: {report['last_mesh_change_fraction'] * 100:.4f}%\n\n"
                                "This reference study is independent of the currently selected project.\n"
                                "See docs/cantilever/REPORT.md for assumptions, criteria and plots.")

    def show_reference_report(self, benchmark):
        titles = {"timoshenko": "Timoshenko beam validation", "hole": "Circular-hole stress validation", "modal": "Modal beam validation", "distributed": "Distributed-load validation"}
        if benchmark not in titles:
            raise ValueError("Unknown reference benchmark")
        if benchmark in self.reference_dialogs:
            dialog = self.reference_dialogs[benchmark]
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
            return dialog
        directory = Path(__file__).resolve().parents[2] / "docs" / benchmark
        report = directory / "REPORT.md"
        if not report.is_file():
            raise ValueError("This checkout does not include the reference report")
        document = QTextDocument()
        document.setMarkdown(report.read_text(encoding="utf-8"))
        dark = self.theme == "dark"
        background, foreground = ("#121b2b", "#d8e4f1") if dark else ("#ffffff", "#27374a")
        style = ("<style>body{background:" + background + ";color:" + foreground + ";font:14px 'Segoe UI';margin:24px;line-height:1.55}"
                 "img{max-width:100%;height:auto}table{border-collapse:collapse;width:100%;font-size:13px}"
                 "td,th{border:1px solid #50627a;padding:7px}a{color:#65b5ff}pre{white-space:pre-wrap}</style>")
        html = document.toHtml().replace("</head>", style + "</head>")
        dialog = QDialog(self)
        dialog.setWindowTitle(titles[benchmark] + " — Published reference study")
        dialog.setMinimumSize(640, 420)
        dialog.resize(min(1250, self.width()), min(850, self.height()))
        layout = QVBoxLayout(dialog)
        note = QLabel("Published reference benchmark — independent of the currently selected project's settings.")
        note.setObjectName("ReferenceNotice")
        note.setWordWrap(True)
        note.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(note)
        view = QWebEngineView(dialog)
        view.setObjectName("ReferenceContent")
        view.setAccessibleName(titles[benchmark] + " report")
        view.setHtml(html, QUrl.fromLocalFile(str(directory) + "/"))
        layout.addWidget(view, 1)
        close = QPushButton("Back to model")
        close.setToolTip(BUTTON_HELP["Back to model"])
        close.clicked.connect(dialog.close)
        layout.addWidget(close)
        self.reference_dialogs[benchmark] = dialog
        dialog.show()
        return dialog

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

    def mark_dirty(self):
        self.sync_force_direction()
        self.dirty = True
        self.details_note.setText("Settings changed. Apply settings or Solve to use them.")
        if "load_surface" in self.selectors:
            self.selectors["load_surface"].setEnabled(self.selectors["load_kind"].currentData() == "traction")

    def sync_force_direction(self):
        normal = self.selectors["load_axis"].currentData() in NORMAL_AXES
        kind = self.selectors["load_kind"]
        for index in range(kind.count()):
            kind.model().item(index).setEnabled(not normal or kind.itemData(index) == "traction")
        if normal and kind.currentData() != "traction":
            blocker = QSignalBlocker(kind)
            kind.setCurrentIndex(kind.findData("traction"))
            del blocker
        self.normal_load_note.setVisible(normal)
        self.fields["load_N"].setToolTip(
            "Force magnitude summed over the selected surface in newtons. Positive follows inward/outward; negative reverses it. On curved faces the net force can be smaller or zero."
            if normal else FIELD_HELP["load_N"])

    def save_parameters(self):
        parameters = {key: field.value() for key, field in self.fields.items()}
        parameters["mesh_size_m"] /= 1000
        parameters["young_Pa"] *= 1e9
        parameters.update({key: selector.currentData() for key, selector in self.selectors.items()})
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

    def modal(self):
        self.save_parameters()
        self.workspace.start_job(self.require_project(), "modal")
        self.workspace.show_project(self.project_id, "modal")

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

    def convergence(self):
        self.save_parameters()
        self.workspace.start_job(self.require_project(), "convergence")
        self.status_label.setText("Convergence study started: each mesh is finer than the last. Stop computing ends it early.")

    def show_convergence_report(self, results=None):
        results = results or self.workspace.get_convergence_results(self.require_project())
        key = ("convergence", results["job_id"])
        url = QUrl.fromLocalFile(results["artifacts"]["report.html"])
        url.setQuery("theme=" + (self.theme or "dark"))
        if key in self.reference_dialogs:
            dialog = self.reference_dialogs[key]
            dialog.findChild(QWebEngineView, "ConvergenceReport").setUrl(url)
            dialog.show()
            dialog.raise_()
            return dialog
        summary = results["summary"]
        dialog = QDialog(self)
        dialog.setWindowTitle("Mesh convergence study")
        dialog.setMinimumSize(640, 420)
        dialog.resize(min(1250, self.width()), min(900, self.height()))
        layout = QVBoxLayout(dialog)
        note = QLabel(f"{len(summary['levels'])} meshes · {summary['levels'][0]['tetrahedra']:,} → {summary['levels'][-1]['tetrahedra']:,} elements · "
                      "Click “open” in the table to inspect any mesh's result.")
        note.setObjectName("ReferenceNotice")
        note.setWordWrap(True)
        layout.addWidget(note)
        view = QWebEngineView(dialog)
        view.setObjectName("ConvergenceReport")
        view.setAccessibleName("Convergence study report")
        view.setUrl(url)
        layout.addWidget(view, 1)
        close = QPushButton("Back to model")
        close.setToolTip(BUTTON_HELP["Back to model"])
        close.clicked.connect(dialog.close)
        layout.addWidget(close)
        self.reference_dialogs[key] = dialog
        dialog.show()
        return dialog

    def show_stress(self):
        result = self.workspace.get_results(self.require_project())
        if "maximum_von_mises_Pa" not in result["summary"]:
            raise ValueError("Solve again to generate recovered stress contours")
        self.workspace.show_project(self.project_id, "results")
        self.result_component.setCurrentIndex(4)
        self.refresh()

    def edit_regions(self):
        self.cancel_face_picking()
        self.save_parameters()
        project = self.workspace.get_project(self.require_project())
        dialog = QDialog(self)
        dialog.setWindowTitle("Support and load surface regions")
        dialog.resize(600, 380)
        layout = QVBoxLayout(dialog)
        note = QLabel("Enter CAD face IDs separated by commas. An optional box selects triangles whose centers lie inside it. Box values are xmin,ymin,zmin,xmax,ymax,zmax in mm. Empty support uses X-min; empty load uses the bounding plane. A selected support is fully fixed—this does not simulate contact or sliding.")
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        entries = {}
        for key, caption in (("support_region", "Fixed support"), ("load_region", "Uniform traction")):
            region = project["parameters"][key]
            face_input = QLineEdit(", ".join(str(value) for value in region.get("faces", [])))
            box_input = QLineEdit(", ".join(f"{value * 1000:g}" for value in region.get("box_m", [])))
            face_input.setToolTip("Enter CAD face IDs separated by commas, for example 8, 15. See the face list below; leave blank to use the default region.")
            box_input.setToolTip("Optional limits in mm: xmin, ymin, zmin, xmax, ymax, zmax. Selects surface triangles by their centers; leave blank for no box filter.")
            form.addRow(caption + " CAD faces", face_input)
            form.addRow(caption + " box (mm)", box_input)
            entries[key] = face_input, box_input
        layout.addLayout(form)
        error = QLabel()
        error.setWordWrap(True)
        layout.addWidget(error)
        catalogue = []
        for job in self.workspace.list_jobs(project["id"]):
            if job["status"] == "completed" and job["revision"] == project["revision"] and job.get("result"):
                catalogue = job["result"].get("cad_faces", [])
                if catalogue:
                    break
        face_list = QPlainTextEdit()
        face_list.setReadOnly(True)
        face_list.setPlainText("CAD face | area mm² | center X,Y,Z mm\n" + "\n".join(
            f"{face['id']} | {face['area_m2'] * 1e6:.4g} | " + ", ".join(f"{value * 1000:.4g}" for value in face["centroid_m"])
            for face in catalogue) if catalogue else "Generate a mesh to list CAD face IDs and centers.")
        layout.addWidget(face_list)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setToolTip("Save these support and load regions for the project.")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setToolTip("Close without saving changes to these regions.")
        layout.addWidget(buttons)
        buttons.rejected.connect(dialog.reject)
        def save():
            try:
                parameters = {}
                for key, (face_input, box_input) in entries.items():
                    region = {}
                    if face_input.text().strip():
                        region["faces"] = json.loads("[" + face_input.text() + "]")
                    if box_input.text().strip():
                        region["box_m"] = [value / 1000 for value in json.loads("[" + box_input.text() + "]")]
                    parameters[key] = region
                if parameters["load_region"]:
                    parameters["load_kind"] = "traction"
                self.workspace.set_parameters(project["id"], parameters)
                self.project_revision = None
                dialog.accept()
                self.refresh()
            except (ValueError, TypeError) as failure:
                error.setText(str(failure))
        buttons.accepted.connect(save)
        dialog.exec()

    def begin_face_picking(self, mode):
        if mode not in {"support", "load"}:
            raise ValueError("Choose support or load faces")
        project = self.workspace.get_project(self.require_project())
        if self.dirty:
            raise ValueError("Apply settings and generate a mesh before picking faces")
        if any(job["status"] in {"queued", "running"} for job in self.workspace.list_jobs(project["id"])):
            raise ValueError("Wait for the current job before picking faces")
        if self.face_pick_session:
            self.view.page().runJavaScript(f"switchFacePicking({json.dumps(mode)})")
            self.pick_note.setText("Click faces to toggle. Switch between support and force faces, then Save picked faces. Drag to rotate.")
            return
        session = {"project_id": project["id"], "revision": project["revision"], "view": self.loaded_view}
        self.face_pick_session = session
        parameters = project["parameters"]
        script = ("typeof setFacePicking==='function' && "
                  f"setFacePicking('support',{json.dumps(parameters['support_region'].get('faces', []))}) && "
                  f"setFacePicking('load',{json.dumps(parameters['load_region'].get('faces', []))}) && "
                  f"switchFacePicking({json.dumps(mode)})")
        def started(ready):
            if self.face_pick_session is not session:
                return
            if not ready:
                self.cancel_face_picking()
                self.pick_note.setText("Generate a new mesh once to enable clickable CAD faces for this model.")
                return
            self.pick_actions.show()
            self.pick_note.setText("Click to toggle whole faces. Cyan = fixed support; orange = force. Switch roles, then Save picked faces. Edited regions replace box filters.")
        self.view.page().runJavaScript(script, started)

    def clear_picked_faces(self):
        if self.face_pick_session:
            self.view.page().runJavaScript("clearPickedFaces()")

    def cancel_face_picking(self):
        self.face_pick_session = None
        self.pick_actions.hide()
        self.view.page().runJavaScript("if(typeof setFacePicking==='function')setFacePicking(null)")
        self.pick_note.setText("Pick faces on the model, or enter face IDs in Support / load regions.")

    def save_picked_faces(self):
        session = self.face_pick_session
        if session is None:
            return
        def received(selection):
            if self.face_pick_session is session:
                self.safe(lambda: self.commit_picked_faces(session, json.loads(selection) if isinstance(selection, str) else None))
        self.view.page().runJavaScript("typeof getFaceSelection==='function'?JSON.stringify(getFaceSelection()):null", received)

    def commit_picked_faces(self, session, selection):
        project = self.workspace.get_project(self.require_project())
        if (self.face_pick_session is not session or project["id"] != session["project_id"]
                or project["revision"] != session["revision"] or self.loaded_view != session["view"] or self.dirty):
            self.cancel_face_picking()
            raise ValueError("The project changed. Generate a mesh and pick faces again")
        if not isinstance(selection, dict) or selection.get("mode") not in {"support", "load"}:
            raise ValueError("No face selection is available")
        available = selection.get("available", [])
        updates = {}
        for role in ("support", "load"):
            if not selection.get("touched", {}).get(role):
                continue
            faces = selection.get(role)
            if not isinstance(faces, list) or any(type(face) is not int or face <= 0 or face not in available for face in faces):
                raise ValueError("Choose valid CAD faces from the model")
            if not faces:
                raise ValueError("Select at least one face for each edited region. Use the regions dialog to restore defaults")
            updates[role + "_region"] = {"faces": sorted(set(faces))}
            if role == "load":
                updates["load_kind"] = "traction"
        if updates:
            self.workspace.set_parameters(project["id"], updates)
            self.selection_preview = {"project_id": project["id"], "cad": project["cad"],
                                      "mesh": [project["parameters"][key] for key in ("mesh_size_m", "cad_scale", "element_order")],
                                      "artifact": session["view"][0]}
            self.workspace.show_project(project["id"], "geometry")
        self.cancel_face_picking()
        self.pick_note.setText("Faces saved. Set total force and direction, then Solve." if updates else "No changes to save.")
        self.project_revision = None

    def select_mode(self, *args):
        if self.modal_selector.currentData() is not None and self.project_id:
            self.workspace.show_project(self.project_id, "modal", self.modal_selector.currentData())
            self.refresh()

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
                                "16 stdio MCP tools share this desktop workspace.\n\n"
                                "Create/import projects, set inputs, mesh, solve, inspect jobs/results and select views.\n\n"
                                "Workspace: " + str(self.workspace.root) + "\n\n"
                                "Server: python -m opensim.mcp_server\nSee docs/DESKTOP_AND_MCP.md for client setup.")

    def apply_view_options(self, *args):
        state = self.workspace.ui_state()
        mode = state["view"]
        animation_label = "Pause mode" if self.animate_mode.isChecked() else "Animate mode"
        self.animate_mode.setText(cat_text(animation_label) if self.language == "cat" else animation_label)
        scale = ["auto", 1, 10, 100, 500][self.deformation.currentIndex()]
        if mode == "modal":
            scale = "auto"
        component = ["magnitude", "x", "y", "z", "stress"][self.result_component.currentIndex()]
        self.view.page().runJavaScript(
            f"if(typeof setViewportMode==='function'){{setViewportMode({json.dumps(mode)});setDeformationScale({json.dumps(scale)});}}"
            f"if(typeof setTheme==='function')setTheme({json.dumps(self.theme)});"
            f"if(typeof setCatMode==='function')setCatMode({json.dumps(self.workspace.ui_state()['language'] == 'cat')});"
            f"if(typeof setModeAnimation==='function')setModeAnimation({json.dumps(mode == 'modal' and self.animate_mode.isChecked())});"
            f"if(typeof setResultComponent==='function')setResultComponent({json.dumps(component)});")

    def apply_camera(self, *args):
        orientation = ["isometric", "front", "top", "flipped-front"][self.camera.currentIndex()]
        self.view.page().runJavaScript(f"if(typeof setViewOrientation==='function')setViewOrientation({json.dumps(orientation)});")

    def viewer_for_artifact(self, artifact):
        sources = [artifact, Path(__file__).with_name("viewer.html"), Path(__file__).with_name("viewport.js")]
        identity = "|".join(str(path.resolve()) + ":" + str(path.stat().st_mtime_ns) for path in sources)
        target = self.workspace.root / ".viewer-cache" / (hashlib.sha256(identity.encode()).hexdigest() + ".html")
        if not target.is_file():
            refresh_viewer(artifact, target)
        return target

    def set_theme(self, theme):
        self.workspace.set_theme(theme)
        self.apply_theme()
        self.apply_language()

    def set_language(self, language):
        self.workspace.set_language(language)
        self.apply_language()
        self.apply_view_options()

    def present_text(self, identity, current, setter):
        source, rendered = self.presentation_text.get(identity, (current, None))
        if current != rendered:
            source = current
        target = cat_text(source) if self.language == "cat" else source
        if current != target:
            setter(target)
        self.presentation_text[identity] = source, target

    def apply_language(self):
        previous = self.language
        self.language = self.workspace.ui_state()["language"]
        active = self.language == "cat"
        for control in (self.cat_button, self.cat_action):
            blocker = QSignalBlocker(control)
            control.setChecked(active)
            del blocker
        self.cat_button.setText("Cat mode: ON" if active else "Cat mode: OFF")
        self.cat_button.setToolTip("Switch back to English" if active else "A deeply unserious feline translation. Meow.")
        skipped = {self.cat_button, self.viewport_title, self.status_label, self.progress_label}
        for widget in self.findChildren(QLabel) + self.findChildren(QPushButton) + self.findChildren(QToolButton):
            if widget not in skipped:
                self.present_text((widget, "text"), widget.text(), widget.setText)
        for action in self.findChildren(QAction):
            if action is not self.cat_action:
                self.present_text((action, "text"), action.text(), action.setText)
        for dock in self.findChildren(QDockWidget):
            self.present_text((dock, "title"), dock.windowTitle(), dock.setWindowTitle)
        self.present_text((self, "title"), self.windowTitle(), self.setWindowTitle)
        for index in range(self.ribbon.count()):
            self.present_text((self.ribbon, index), self.ribbon.tabText(index), lambda value, tab=index: self.ribbon.setTabText(tab, value))
        for combo in self.findChildren(QComboBox):
            blocker = QSignalBlocker(combo)
            for index in range(combo.count()):
                self.present_text((combo, index), combo.itemText(index), lambda value, item=index, control=combo: control.setItemText(item, value))
            del blocker
        for index in range(self.tree.topLevelItemCount()):
            root = self.tree.topLevelItem(index)
            for child_index in range(root.childCount()):
                child = root.child(child_index)
                self.present_text((self.tree, index, child_index), child.text(0), lambda value, item=child: item.setText(0, value))
        self.update_ribbon_height()
        if previous != self.language:
            self.apply_view_options()

    def apply_theme(self):
        self.theme = self.workspace.ui_state()["theme"]
        self.setStyleSheet(STYLE + (DARK_STYLE if self.theme == "dark" else ""))
        blocker = QSignalBlocker(self.dark_action)
        self.dark_action.setChecked(self.theme == "dark")
        del blocker
        self.theme_button.setText("Light mode" if self.theme == "dark" else "Dark mode")
        self.legend.setStyleSheet("padding:9px;color:" + ("#9fb9d7;background:#132238" if self.theme == "dark" else "#55697e;background:#fff"))
        self.apply_view_options()

    def refresh(self):
        self.workspace.heartbeat()
        state = self.workspace.ui_state()
        self.result_component.model().item(4).setEnabled(state["view"] == "results")
        if state["view"] == "modal" and self.result_component.currentIndex() == 4:
            blocker = QSignalBlocker(self.result_component)
            self.result_component.setCurrentIndex(0)
            del blocker
        if state["theme"] != self.theme:
            self.apply_theme()
        projects = self.workspace.list_projects()
        if not state["project_id"] and projects:
            state = self.workspace.show_project(projects[0]["id"])
        selected = state["project_id"]
        project_changed = selected != self.project_id
        if selected != self.project_id:
            self.project_id = selected
            self.project_revision = None
            self.dirty = False
        project = self.workspace.get_project(selected) if selected else None
        if self.face_pick_session and (not project or selected != self.face_pick_session["project_id"]
                or project["revision"] != self.face_pick_session["revision"]):
            self.cancel_face_picking()
        if project:
            self.region_note.setText("Support region: " + json.dumps(project["parameters"]["support_region"]) + "\nLoad region: " + json.dumps(project["parameters"]["load_region"]))
        if project_changed and project:
            transverse_point = project["parameters"]["load_kind"] == "point" and project["parameters"]["load_axis"] == "z"
            self.camera.setCurrentIndex(1 if transverse_point else 0)
        jobs = self.workspace.list_jobs(selected) if selected else []
        signature = [(entry["id"], entry["name"], entry["revision"]) for entry in projects], [(job["id"], job["status"]) for job in jobs], selected
        if signature != self.tree_signature:
            self.tree_signature = signature
            self.tree.clear()
            for entry in projects:
                root = QTreeWidgetItem([entry["name"]])
                root.setData(0, Qt.ItemDataRole.UserRole, (entry["id"], "geometry"))
                self.tree.addTopLevelItem(root)
                element = "C3D10" if entry["parameters"]["element_order"] == 2 else "C3D4"
                axis = entry["parameters"]["load_axis"].upper()
                application = ("selected load region" if entry["parameters"]["load_region"] else "uniform traction / " + entry["parameters"]["load_surface"] if entry["parameters"]["load_kind"] == "traction"
                               else "tip point" if entry["parameters"]["load_kind"] == "point" else "end face (equal nodes)")
                support_caption = "Selected region" if entry["parameters"]["support_region"] else "X-min"
                for label, view in (("Geometry (single solid)", "geometry"), (f"Mesh / {element}", "mesh"),
                                    ("Static Structural", "geometry"), ("  Fixed Support / " + support_caption, "geometry"),
                                    (f"  Static force / {axis} · {application}", "geometry"), ("Solution / Displacement", "results"),
                                    ("Modal / Natural frequencies", "modal")):
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
            for key, selector in self.selectors.items():
                blocker = QSignalBlocker(selector)
                selector.setCurrentIndex(selector.findData(project["parameters"][key]))
                del blocker
            self.project_revision = project["revision"]
        active = next((job for job in jobs if job["status"] in {"queued", "running"}), None)
        for job in jobs:
            if (job["kind"] == "convergence" and job["status"] == "completed" and job["id"] not in self.shown_convergence
                    and job["updated"] >= self.opened_at and project and job["revision"] == project["revision"]):
                self.shown_convergence.add(job["id"])  # open each finished study once, only if it finished while the app was open
                try:
                    self.show_convergence_report()
                except ValueError:
                    pass
        self.sync_force_direction()
        matching = next((job for job in jobs if project and job["revision"] == project["revision"]), None)
        self.update_job_progress(active or matching)
        self.apply_button.setEnabled(bool(project) and not active)
        for field in self.fields.values():
            field.setEnabled(bool(project) and not active)
        for selector in self.selectors.values():
            selector.setEnabled(bool(project) and not active)
        self.selectors["load_surface"].setEnabled(bool(project) and not active and self.selectors["load_kind"].currentData() == "traction")
        self.details_heading.setText("DETAILS OF MODAL ANALYSIS" if state["view"] == "modal" else "DETAILS OF STATIC STRUCTURAL")
        if state["view"] == "modal":
            self.fields["load_N"].setEnabled(False)
            self.selectors["load_axis"].setEnabled(False)
            self.selectors["load_kind"].setEnabled(False)
            self.selectors["load_surface"].setEnabled(False)
        for button in self.analysis_buttons:
            button.setEnabled(bool(project) and not active)
        for button in self.stop_buttons:
            button.setEnabled(bool(active))
        if project:
            self.status_label.setText(f"{project['name']}  |  " + (f"{active['kind'].title()} {active['status']}…" if active else "Ready"))
            modal_result = None
            if state["view"] == "modal":
                try:
                    modal_result = self.workspace.get_modal_results(selected)
                except ValueError:
                    pass
            self.modal_tools.setVisible(state["view"] == "modal")
            self.deformation.setEnabled(state["view"] != "modal")
            self.animate_mode.setEnabled(bool(modal_result))
            self.modal_selector.setEnabled(bool(modal_result))
            blocker = QSignalBlocker(self.modal_selector)
            frequencies = modal_result["summary"]["frequencies_Hz"] if modal_result else []
            if frequencies and not 1 <= state["modal_mode"] <= len(frequencies):
                state = self.workspace.show_project(selected, "modal", 1)
            labels = [f"{index} · {frequency:.6g} Hz" for index, frequency in enumerate(frequencies, start=1)]
            if labels != [self.modal_selector.itemText(index) for index in range(self.modal_selector.count())]:
                self.modal_selector.clear()
                for index, label in enumerate(labels, start=1):
                    self.modal_selector.addItem(label, index)
            self.modal_selector.setCurrentIndex(self.modal_selector.findData(state["modal_mode"]))
            del blocker
            artifact = self.workspace.current_artifact(selected, state["view"], state["modal_mode"])
            preview = self.selection_preview
            if (not artifact and state["view"] == "geometry" and preview and preview["project_id"] == selected
                    and preview["cad"] == project["cad"]
                    and preview["mesh"] == [project["parameters"][key] for key in ("mesh_size_m", "cad_scale", "element_order")]):
                candidate = Path(preview["artifact"])
                if candidate.is_file():
                    artifact = candidate
            view_key = str(artifact), state["view"]
            if self.face_pick_session and (view_key != self.face_pick_session["view"] or active):
                self.cancel_face_picking()
            if view_key != self.loaded_view:
                self.loaded_view = view_key
                self.viewport_title.setText(project["name"].upper() + "  /  " + state["view"].upper())
                if artifact:
                    url = QUrl.fromLocalFile(str(self.viewer_for_artifact(artifact)))
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
                        direction = result.get("load_axis", "x")
                        reaction = ("Reaction XYZ: " + ", ".join(f"{value:.4f}" for value in result["reaction_N"]) + " N"
                                    if direction in NORMAL_AXES else f"Reaction {direction.upper()}: {result['reaction_N']['xyz'.index(direction)]:.4f} N")
                        output.append(f"  Maximum displacement: {result['maximum_displacement_m'] * 1000:.6g} mm  |  "
                                      f"{reaction}  |  "
                                      f"Force imbalance: {result['relative_force_imbalance']:.2e}")
                    elif result.get("analysis") == "convergence":
                        target = result["quantities"][result["target"]]
                        output.append(f"  Convergence study ({result['target']}): {target['verdict']} · {len(result['levels'])} meshes · "
                                      f"last change {target['last_change'] * 100:.3g}% · open Solution → Convergence report")
                    elif result.get("analysis") == "modal":
                        output.append("  Frequencies (Hz): " + ", ".join(f"{frequency:.6g}" for frequency in result["frequencies_Hz"]))
            text = "\n".join(output) or "No jobs yet. Import CAD or create a test plate."
            if self.messages.toPlainText() != text:
                self.messages.setPlainText(text)
            try:
                if state["view"] == "modal" and modal_result:
                    summary = modal_result["summary"]
                    selected_mode = state["modal_mode"]
                    frequency = summary["frequencies_Hz"][selected_mode - 1]
                    self.result_cards[0].setText(f"Mode {selected_mode} frequency\n{frequency:.6g} Hz")
                    self.result_cards[1].setText(f"Extracted modes\n{summary['mode_count']}")
                    self.result_cards[2].setText("Mode shape\nNormalized · dimensionless")
                    support_label = "selected support fixed" if summary.get("support_region") else "X-min fixed"
                    self.legend.setText(f"  Mode {selected_mode}: {frequency:.6g} Hz · {support_label} · no prestress · arbitrary amplitude · 1 Hz animation playback")
                    self.apply_language()
                    return
                if state["view"] != "results":
                    raise ValueError("Geometry or mesh view")
                summary = self.workspace.get_results(selected)["summary"]
                self.result_cards[0].setText(f"Maximum recovered von Mises\n{summary['maximum_von_mises_Pa'] / 1e6:.6g} MPa" if self.result_component.currentIndex() == 4 and "maximum_von_mises_Pa" in summary
                                           else f"Maximum |U|\n{summary['maximum_displacement_m'] * 1000:.6g} mm")
                selected_load = bool(summary.get("load_region"))
                tip = summary.get("loaded_surface_mean_displacement_m", [0, 0, 0]) if selected_load else summary.get("tip_mean_displacement_m") or summary.get("loaded_surface_mean_displacement_m", [0, 0, 0])
                axis = summary.get("load_axis", "x")
                location_label = "Tip mean" if summary.get("tip_mean_displacement_m") and not selected_load else "Loaded surface mean"
                if axis in NORMAL_AXES:
                    self.result_cards[1].setText(f"Loaded mean · along normal force\n{summary['loaded_surface_mean_normal_displacement_m'] * 1000:.6g} mm")
                else:
                    self.result_cards[1].setText(f"{location_label} U{axis}\n{tip['xyz'.index(axis)] * 1000:.6g} mm")
                self.result_cards[2].setText(f"Force balance residual\n{summary['relative_force_imbalance']:.2e}")
                self.legend.setText(f"  Displacement |U|: 0 → {summary['maximum_displacement_m'] * 1000:.6g} mm   ·   "
                                    f"{summary['tetrahedra']:,} elements   ·   Display deformation is exaggerated   ·   Drag to rotate")
                if self.result_component.currentIndex() == 4 and "maximum_von_mises_Pa" in summary:
                    self.legend.setText(f"  Recovered von Mises: 0 → {summary['maximum_von_mises_Pa'] / 1e6:.6g} MPa · Ideal fixed-edge peaks may be singular · Display deformation is exaggerated")
            except ValueError:
                for card, title in zip(self.result_cards, ("Maximum |U|", "Tip displacement", "Force balance")):
                    card.setText(title + "\n—")
                label = "No solved result for current settings" if state["view"] in {"results", "modal"} else "Undeformed geometry / mesh preview"
                self.legend.setText(f"  {label}   ·   Drag to rotate")
        self.apply_language()

    def update_job_progress(self, job):
        if job is None:
            self.job_progress.setRange(0, 100)
            self.job_progress.setValue(0)
            self.progress_label.setText("No active job")
            self.progress_panel.hide()
            self.units_label.show()
            return
        self.progress_panel.show()
        active = job["status"] in {"queued", "running"}
        stage = job.get("progress_stage", "starting") if active else job["status"]
        label = STAGE_LABELS.get(stage, "Working")
        if job["status"] == "running" and stage == "queued":
            label = "Working"
        if self.workspace.ui_state()["language"] == "cat":
            label = cat_text(label)
        elapsed = elapsed_label((time.time() if active else job["updated"]) - job["created"])
        self.progress_label.setText(f"{label} · {elapsed}")
        self.progress_label.setToolTip(f"{job['kind'].title()} · {job['id']}\n{label} · elapsed {elapsed}")
        self.units_label.setVisible(not active)
        self.stop_button.setVisible(active)
        self.job_progress.setTextVisible(not active)
        if active:
            self.job_progress.setRange(0, 0)
            self.job_progress.setToolTip("Work is in progress. This stage has no reliable percentage estimate.")
        else:
            self.job_progress.setRange(0, 100)
            self.job_progress.setValue(100 if job["status"] == "completed" else 0)
            self.job_progress.setFormat({"completed": "Complete", "cancelled": "Stopped"}.get(job["status"], "Failed"))
            self.job_progress.setToolTip(label)


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
