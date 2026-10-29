"""Commands for the desktop workbench."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QDockWidget, QHBoxLayout, QLabel, QMenuBar, QMessageBox, QPushButton, QToolButton, QVBoxLayout, QWidget
from opensim.workspace import CAPABILITIES
from opensim.hover_help import FIELD_HELP, BUTTON_HELP


class CommandsMixin:
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
        self.setMenuWidget(header)
        file_menu = self.application_menu.addMenu("File")
        for title, handler in (("New project", self.new_project), ("Open project…", self.open_project),
                               ("Rename project…", self.rename_project), ("Close project", self.close_project),
                               ("Import CAD…", self.import_cad), ("File locations…", self.show_file_locations),
                               ("Open project folder", self.open_project_folder), ("Open latest run folder", self.open_run_folder)):
            action = QAction(title, self)
            if handler not in (self.new_project, self.open_project):
                self.project_actions.append(action)
            if handler == self.open_project:
                action.setShortcut("Ctrl+O")
            elif handler == self.close_project:
                action.setShortcut("Ctrl+W")
            elif handler == self.rename_project:
                action.setShortcut("F2")
            action.setToolTip(BUTTON_HELP.get(title.rstrip("…"), title))
            action.triggered.connect(lambda checked=False, callback=handler: self.safe(callback))
            file_menu.addAction(action)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)
        self.settings_menu = self.application_menu.addMenu("Settings")
        appearance_menu = self.settings_menu.addMenu("Appearance")
        self.theme_group = QActionGroup(self)
        self.theme_group.setExclusive(True)
        self.theme_actions = {}
        for theme, title in (("light", "Light"), ("dark", "Dark"), ("midnight", "Midnight")):
            action = QAction(title, self)
            action.setCheckable(True)
            action.setToolTip({"light": "A bright background for daytime use.", "dark": "The original dark blue workbench.",
                               "midnight": "A deeper, near-black workbench for low-light use."}[theme])
            action.triggered.connect(lambda checked=False, value=theme: self.set_theme(value))
            self.theme_group.addAction(action)
            appearance_menu.addAction(action)
            self.theme_actions[theme] = action
        self.cat_action = QAction("Cat mode (joke translation)", self)
        self.cat_action.setCheckable(True)
        self.cat_action.toggled.connect(lambda checked: self.set_language("cat" if checked else "en"))
        self.cat_action.setToolTip("A joke feline translation. Turn off to return to English; model inputs and units stay the same.")
        self.settings_menu.addAction(self.cat_action)
        self.settings_menu.addSeparator()
        discord_action = self.settings_menu.addAction("Discord Rich Presence…", self.show_discord_settings)
        discord_action.setToolTip("Show basic simulator activity in Discord. Configure or disable sharing here; project names and file paths stay private.")
        help_menu = self.application_menu.addMenu("Help")
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
            if handler in (self.mesh, self.solve, self.modal, self.thermal, self.convergence, self.run_selected_study, self.import_cad) or title in {"Pick fixed support", "Pick force faces"}:
                self.analysis_buttons.append(button)
        else:
            button.setEnabled(False)
            button.setToolTip("Planned — not implemented")
        layout.addWidget(button)
        if title == "Pick force faces":
            self.force_pick_buttons.append(button)
        if title == "Pick fixed support":
            button.setProperty("pickRole", "support")
        if title == "Result plots":
            self.result_plot_buttons.append(button)
        return button

    def install_hover_help(self):
        for button in self.findChildren(QPushButton):
            if button.text() in BUTTON_HELP:
                button.setToolTip(BUTTON_HELP[button.text()])
        for key, control in {**self.fields, **self.selectors}.items():
            control.setToolTip(FIELD_HELP[key])
        self.deformation.setToolTip("Magnify movement for viewing only. True scale shows actual displacement; Auto targets 10% of model size.")
        self.camera.setToolTip("Choose a camera orientation or Home. Click ±X/±Y/±Z on the triad to view those planes; H restores Home and right-click H saves it. Geometry and forces do not rotate.")
        self.result_component.setToolTip("Choose total movement, movement along X/Y/Z, or von Mises stress for the color display.")
        self.modal_selector.setToolTip("Select a natural frequency and its vibration shape. Shape amplitude is normalized, not a predicted displacement.")
        for action in self.application_menu.findChildren(QAction):
            title = action.text().rstrip("…")
            if title in BUTTON_HELP:
                action.setToolTip(BUTTON_HELP[title])

    def build_toolbox(self):
        dock = QDockWidget("Analysis Toolbox", self)
        dock.setObjectName("toolbox")
        dock.setMinimumWidth(195)
        contents = QWidget()
        layout = QVBoxLayout(contents)
        layout.addWidget(QLabel("AVAILABLE NOW"))
        for label, callback in (("Static Structural", self.solve), ("Convergence study", self.convergence), ("Modal analysis", self.modal), ("Thermal analysis", self.thermal), ("Fluid dynamics", self.show_cfd),
                                ("Generate Mesh", self.mesh), ("MCP Controls", self.show_mcp)):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, handler=callback: self.safe(handler))
            layout.addWidget(button)
            if callback in (self.solve, self.modal, self.thermal, self.mesh, self.convergence):
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
