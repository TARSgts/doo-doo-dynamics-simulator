"""Layout for the desktop workbench."""
from PySide6.QtCore import Qt
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QComboBox, QDockWidget, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QSplitter, QTabWidget, QTreeWidget, QVBoxLayout, QWidget
from opensim.hover_help import FIELD_HELP, BUTTON_HELP
from opensim.ui.widgets import ScrollSafeDoubleSpinBox, ScrollSafeSpinBox


class LayoutMixin:
    def build_center(self):
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.ribbon = QTabWidget()
        self.ribbon.setObjectName("CommandRibbon")
        self.ribbon.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        groups = {
            "Home": [("New project", "Workspace", self.new_project), ("Open project", "Saved projects", self.open_project),
                     ("Import CAD", "STEP / STL / OBJ / 3MF", self.import_cad),
                     ("Generate mesh", "Gmsh tetrahedra", self.mesh),
                     ("Solve", "Selected study", self.run_selected_study), ("Results", "Selected study", self.show_selected_results)],
            "Geometry": [("Import CAD", "One closed solid", self.import_cad),
                         ("CAD editing", "Planned" , None), ("Assemblies", "Planned", None)],
            "Mesh": [("Generate mesh", "Linear tetrahedra", self.mesh), ("Show mesh", "Surface edges", lambda: self.change_view("mesh")),
                     ("Adaptive refinement", "Planned", None)],
            "Environment": [("Apply settings", "Material / axial force", self.save_parameters),
                            ("Pick fixed support", "Click model faces", lambda: self.begin_face_picking("support")),
                            ("Pick force faces", "Click model faces", lambda: self.begin_face_picking("load")), ("Contact", "Planned", None)],
            "Solution": [("Solve", "Selected study", self.run_selected_study), ("Displacement", "Static result", lambda: self.change_view("results")),
                         ("Result plots", "Charts and CSV export", self.show_plots),
                         ("Stress contours", "Recovered von Mises", self.show_stress), ("Convergence", "Mesh refinement study", self.convergence),
                         ("Convergence report", "Latest study", self.show_convergence_report),
                         ("Modal", "Natural frequencies", self.modal), ("Thermal", "Steady temperature and heat flow", self.thermal),
                         ("CFD", "Cylinder, pipe and flat-plate flow studies", self.show_cfd)],
            "Automation": [("MCP status", "Local tools", self.show_mcp), ("Refresh", "Shared workspace", self.refresh),
                           ("Remote access", "Planned", None)],
            "Examples": [("Test plate", "100 × 40 × 5 mm", self.create_demo),
                         ("Heat sink", "Finned thermal conduction example", self.create_heat_sink),
                         ("Cantilever", "1 m tip-loaded beam", self.create_beam)],
            "Validation": [("Reference report", "Euler–Bernoulli study", self.show_validation),
                           ("Timoshenko", "Bending + shear study", lambda: self.show_reference_report("timoshenko")),
                           ("Modal beam", "Frequency verification", lambda: self.show_reference_report("modal")),
                           ("Distributed load", "Uniform traction study", lambda: self.show_reference_report("distributed")),
                           ("Thermal bar", "Fourier conduction verification", lambda: self.show_reference_report("thermal")),
                           ("CFD checks", "Cylinder, pipe and flat-plate verification", self.show_cfd_validation),
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
        self.camera.addItems(["Iso", "Front XZ", "Top XY", "Front XZ · flipped", "Home"])
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
        self.modal_amplitude=QComboBox()
        for label,value in [('1% size',.01),('2% size',.02),('5% size',.05),('10% size',.1)]:self.modal_amplitude.addItem(label,value)
        self.modal_amplitude.setCurrentIndex(1)
        self.modal_amplitude.setToolTip('Visual mode amplitude as a fraction of model size. This is not a predicted vibration displacement. Playback is slowed to 1 Hz.')
        self.modal_amplitude.currentIndexChanged.connect(self.apply_view_options)
        modal_row.addWidget(self.modal_amplitude)
        self.animate_mode = QPushButton("Animate mode")
        self.animate_mode.setCheckable(True)
        self.animate_mode.toggled.connect(self.apply_view_options)
        modal_row.addWidget(self.animate_mode)
        self.export_gif_button = QPushButton("Export GIF")
        self.export_gif_button.setAccessibleName("Export the selected mode shape as an animated GIF")
        self.export_gif_button.clicked.connect(lambda checked=False: self.safe(self.export_mode_gif))
        modal_row.addWidget(self.export_gif_button)
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
        <script>function setTheme(theme){document.body.style.background=theme==='midnight'?'radial-gradient(#111a2b,#03050a)':theme==='dark'?'radial-gradient(#22344f,#101827)':'radial-gradient(#fff,#dfe7f0)';document.body.style.color=theme!=='light'?'#dce9f9':'#243b55';}</script></body></html>"""

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
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.project_context_menu)
        tree_panel = QWidget()
        tree_layout = QVBoxLayout(tree_panel)
        tree_layout.setContentsMargins(4, 2, 4, 0)
        tree_layout.setSpacing(2)
        tree_tools = QHBoxLayout()
        for title, handler in (("Open project…", self.open_project), ("Close project", self.close_project)):
            button = QPushButton(title)
            button.setToolTip(BUTTON_HELP[title.rstrip("…")])
            button.clicked.connect(lambda checked=False, action=handler: self.safe(action))
            tree_tools.addWidget(button)
            if handler == self.close_project:
                self.close_project_button = button
        tree_layout.addLayout(tree_tools)
        tree_layout.addWidget(self.tree)
        splitter.addWidget(tree_panel)
        details = QWidget()
        details.setObjectName("DetailsPanel")
        details.setMinimumWidth(0)
        layout = QVBoxLayout(details)
        heading = QLabel("DETAILS OF STATIC STRUCTURAL")
        self.details_heading = heading
        heading.setObjectName("DetailsHeading")
        heading.setWordWrap(True)
        layout.addWidget(heading)
        self.run_study_button = QPushButton("Run static study")
        self.run_study_button.setToolTip("Save settings and solve the selected static structural study.")
        self.run_study_button.clicked.connect(lambda checked=False: self.safe(self.run_selected_study))
        self.analysis_buttons.append(self.run_study_button)
        layout.addWidget(self.run_study_button)
        self.plots_button = QPushButton("Result plots…")
        self.plots_button.setToolTip(BUTTON_HELP["Result plots"])
        self.plots_button.clicked.connect(lambda checked=False: self.safe(self.show_plots))
        self.result_plot_buttons.append(self.plots_button)
        layout.addWidget(self.plots_button)
        form = QFormLayout()
        self.properties_form = form
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.fields = {}
        definitions = [("mesh_size_m", "Mesh size (mm)", 0.001, 100000, 4, 3),
                       ("cad_scale", "CAD scale to m", 0.000001, 100000, 1, 6),
                       ("young_Pa", "Young's E (GPa)", 0.001, 100000, 210, 3),
                       ("poisson", "Poisson ratio", -0.999, 0.499, 0.3, 3),
                       ("density_kg_m3", "Density (kg/m³)", 0.001, 1e9, 7850, 3),
                       ("load_N", "Total force (N)", -1e12, 1e12, 1000, 3),
                       ("thermal_conductivity_W_mK", "Conductivity (W/m·K)", .000001, 1e9, 1, 6),
                       ("thermal_fixed_temperature_K", "Fixed temperature (°C)", -273.15, 1e6, 20, 2),
                       ("thermal_source_temperature_K", "Second temperature (°C)", -273.15, 1e6, 100, 2),
                       ("thermal_power_W", "Total heat input (W)", -1e12, 1e12, 10, 4)]
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
                                                           ("Max von Mises stress", "stress")]),
            ("thermal_boundary_mode", "Thermal source", [("Prescribed temperature", "temperature"), ("Total heat input", "power")])):
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
        self.build_cfd_properties(form,layout)
        self.build_impact_properties(form,layout)
        for key, control in {**self.fields, **self.selectors}.items():
            label_widget = form.labelForField(control)
            label_widget.setToolTip(FIELD_HELP[key])
            label_widget.setWordWrap(True)
            label_widget.setMinimumWidth(0)
            label_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        note = QLabel("Default support: X-min face. Selected regions override defaults.\nTraction: total force (N) spread uniformly over the selected surface.\nBounding-plane selector is used when no load region is set.\nModal: no loads or prestress.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#6f8094;padding:6px")
        self.study_note = note
        layout.addWidget(note)
        self.apply_button = QPushButton("Apply settings")
        self.normal_load_note = QLabel("Perpendicular loading follows each surface's local normal. Positive force follows inward/outward; negative reverses it. On curved or multiple faces, the entered force is the sum of local magnitudes, not the net force.")
        self.normal_load_note.setWordWrap(True)
        layout.addWidget(self.normal_load_note)
        self.normal_load_note.hide()
        self.apply_button.clicked.connect(lambda: self.safe(self.save_parameters))
        layout.addWidget(self.apply_button)
        self.material_button=QPushButton('Material properties…')
        self.material_button.setToolTip('Edit stiffness, Poisson ratio, density and conductivity together, or use an editable steel, aluminum or solid ABS preset.')
        self.material_button.clicked.connect(lambda:self.safe(self.edit_material))
        self.loads_button=QPushButton('Independent forces / pressures…')
        self.loads_button.setToolTip('Each force has its own X/Y/Z components and faces. Pressure uses Pa and local normals. A nonempty list replaces the single load.')
        self.loads_button.clicked.connect(lambda:self.safe(self.edit_loads))
        for button in (self.material_button,self.loads_button):
            button.setMinimumWidth(100);button.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        layout.addWidget(self.material_button);layout.addWidget(self.loads_button)
        self.analysis_buttons.extend([self.material_button,self.loads_button])
        for title, mode in (("Pick fixed support", "support"), ("Pick force faces", "load")):
            button = QPushButton(title)
            button.setProperty("pickRole", mode)
            button.clicked.connect(lambda checked=False, role=mode: self.safe(lambda: self.begin_face_picking(role)))
            button.setToolTip(BUTTON_HELP[title])
            self.analysis_buttons.append(button)
            if mode == "load":
                self.force_pick_buttons.append(button)
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

    def build_logs(self):
        dock = QDockWidget("Messages / Solver Jobs", self)
        dock.setObjectName("messages")
        self.messages = QPlainTextEdit()
        self.messages.setReadOnly(True)
        self.messages.setMaximumBlockCount(3000)
        dock.setWidget(self.messages)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
        self.resizeDocks([dock], [150], Qt.Orientation.Vertical)
