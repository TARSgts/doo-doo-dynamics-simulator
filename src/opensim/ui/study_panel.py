"""Study panel for the desktop workbench."""
from datetime import datetime
from opensim.application.studies import STUDIES
from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtWidgets import QPushButton, QScrollArea, QToolButton
from opensim.hover_help import FIELD_HELP, BUTTON_HELP
from opensim.load_settings import NORMAL_AXES


class StudyPanelMixin:
    def edit_material(self):
        from opensim.materials import edit_material
        edit_material(self)

    def edit_loads(self):
        from opensim.load_editor import LoadEditor
        self.save_parameters()
        if not hasattr(self,'loads_dialog') or self.loads_dialog.pid!=self.project_id:
            self.loads_dialog=LoadEditor(self)
        self.loads_dialog.show();self.loads_dialog.raise_()

    def show_cfd_validation(self):
        self.save_before_project_change()
        project=self.workspace.create_project('CFD analytical verification / '+datetime.now().strftime('%H:%M:%S'))
        self.workspace.select_study(project['id'],'cfd');self.workspace.start_job(project['id'],'cfd_validation')
        self.workspace.show_project(project['id'],'cfd_report');self.project_revision=None;self.refresh()

    def show_cfd(self):
        self.cfd_select()

    def mark_dirty(self):
        self.sync_force_direction()
        self.update_study_panel()
        self.apply_flow_preview()
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

    def update_study_panel(self):
        state = self.workspace.ui_state()
        study = state["study"]
        if self.cfd_panel(study):return
        modal = study == "modal"
        thermal = study == "thermal"
        common = {"mesh_size_m", "cad_scale", "young_Pa", "poisson", "element_order"}
        loads = {"load_N", "load_axis", "load_kind", "load_surface"}
        visible = common | ({"density_kg_m3", "mode_count"} if modal else loads)
        if thermal:
            visible = {"mesh_size_m", "cad_scale", "element_order", "thermal_conductivity_W_mK", "thermal_fixed_temperature_K", "thermal_boundary_mode"}
            visible.add("thermal_power_W" if self.selectors["thermal_boundary_mode"].currentData() == "power" else "thermal_source_temperature_K")
        if study == "convergence":
            visible |= {"convergence_levels", "convergence_ratio", "convergence_tolerance_percent", "convergence_target"}
        if self.selectors["load_kind"].currentData() != "traction":
            visible.discard("load_surface")
        cases=self.workspace.get_project(self.project_id)['parameters']['load_cases'] if self.project_id else []
        if cases and study in {'static','convergence'}:
            visible-= {'load_N','load_axis','load_kind','load_surface'}
        for key, control in {**self.fields, **self.selectors}.items():
            self.properties_form.setRowVisible(control, bool(self.project_id) and key in visible)
        headings = {"static": "DETAILS OF STATIC STRUCTURAL", "modal": "DETAILS OF MODAL ANALYSIS", "convergence": "DETAILS OF CONVERGENCE STUDY", "thermal": "DETAILS OF STEADY THERMAL"}
        self.details_heading.setText(headings[study] if self.project_id else "NO STUDY SELECTED")
        self.study_note.setText({
            "static": "Static deformation and stress. Enter total force in N and its direction. Geometry, material and fixed supports are shared between structural studies. CFD and thermal controls do not invalidate this result.",
            "modal": "Natural frequencies and vibration shapes. Uses density and fixed supports; ignores static loads and prestress. Geometry, material and supports are shared; changing static forces does not invalidate these modes.",
            "convergence": "Refine the static setup across several meshes. Choose a target and tolerance. Geometry, material, fixed supports and forces are shared with Static Structural.",
            "thermal": "Steady heat conduction. Temperatures use °C here; conductivity uses W/(m·K). Choose separate thermal faces; other surfaces are insulated. No convection, radiation or expansion."
        }[study])
        self.study_note.setVisible(bool(self.project_id))
        if cases and study in {'static','convergence'}:
            self.study_note.setText(f'{len(cases)} independent force/pressure entries replace the single load. Edit each entry’s faces and components using Independent forces / pressures.')
        self.normal_load_note.setVisible(bool(self.project_id) and not cases and not modal and not thermal and self.selectors["load_axis"].currentData() in NORMAL_AXES)
        # Only the properties-panel force button is hidden; ribbon commands remain
        # discoverable but are disabled for a modal study.
        for button in self.force_pick_buttons:
            if isinstance(button, QPushButton):
                button.setVisible(not modal and bool(self.project_id))
            if modal or (cases and not thermal):
                button.setEnabled(False)
        self.region_button.setText("Support region…" if modal or (cases and not thermal) else "Support / load regions…")
        if thermal:
            self.region_button.setText("Thermal boundary regions…")
        for button in self.force_pick_buttons:
            button.setText("Pick thermal source faces" if thermal else "Pick force faces")
            button.setToolTip("Pick the second temperature or heat-input surface (orange)." if thermal else BUTTON_HELP['Pick force faces'])
            if cases and not thermal:button.setToolTip('Each independent load has its own faces. Use Independent forces / pressures to select an entry and pick its faces.')
        for button in self.findChildren(QPushButton) + self.findChildren(QToolButton):
            if button.property('pickRole') == 'support':
                button.setText("Pick fixed-temperature faces" if thermal else "Pick fixed support")
                button.setToolTip("Pick the prescribed-temperature surface (cyan)." if thermal else BUTTON_HELP['Pick fixed support'])
        self.region_button.setToolTip("Choose fully fixed support faces. Modal analysis ignores static loads." if modal else BUTTON_HELP["Support / load regions…"])
        if thermal:
            self.region_button.setToolTip("Choose separate fixed-temperature and source faces; these are independent of structural supports and loads.")
        self.run_study_button.setText({"static": "Run static study", "modal": "Run modal study", "convergence": "Run convergence study", "thermal": "Run thermal study"}[study])
        self.run_study_button.setToolTip({"static": "Save settings and solve static deformation and stress.", "modal": "Save settings and calculate natural frequencies and mode shapes.", "convergence": "Save settings and run the static mesh convergence study.", "thermal": "Solve steady temperature and heat flow; unassigned surfaces are insulated."}[study])
        if self.project_id:
            parameters = self.workspace.get_project(self.project_id)["parameters"]
            def region_text(region, default):
                if region.get("faces"):
                    return "Faces " + ", ".join(map(str, region["faces"])) + (" · box filter" if region.get("box_m") else "")
                return "Box selection" if region.get("box_m") else default
            self.region_note.setText("Support: " + region_text(parameters["support_region"], "X-min face")
                                     + ("" if modal else "\nLoad: " + region_text(parameters["load_region"], parameters["load_surface"] if parameters["load_kind"] == "traction" else parameters["load_kind"])))
            if cases and not modal and not thermal:
                self.region_note.setText('Support: '+region_text(parameters['support_region'],'X-min face')+'\nForce/pressure regions are stored independently per entry.')
            if thermal:
                self.region_note.setText("Fixed temperature: " + region_text(parameters["thermal_fixed_region"], "X-min face") + "\nThermal source: " + region_text(parameters["thermal_source_region"], "X-max face"))
        context = self.project_id, study
        if not self.face_pick_session and context != self.panel_context:
            self.pick_note.setText("Pick a fixed support on the model, or enter its face IDs in Support region." if modal else "Pick faces on the model, or enter face IDs in Support / load regions.")
            if thermal:
                self.pick_note.setText("Cyan picks = fixed temperature; orange picks = second temperature or heat input. Thermal faces are separate from structural supports and forces.")
        if context != self.panel_context:
            self.findChild(QScrollArea, "PropertiesScroll").verticalScrollBar().setValue(0)
        self.panel_context = context

    def run_selected_study(self):
        definition=STUDIES[self.workspace.ui_state()['study']]
        getattr(self,definition.desktop_command)()


    def show_selected_results(self):
        study = self.workspace.ui_state()['study']
        if study == 'convergence':
            return self.show_convergence_report()
        self.change_view({'static':'results','modal':'modal','thermal':'thermal','cfd':'cfd_slice'}[study])

    def show_plots(self):
        if self.workspace.ui_state()['study']=='cfd':return self.change_view('cfd_report')
        if self.dirty:
            raise ValueError("Apply settings and solve this study before plotting edited inputs")
        from opensim.plots import load_plot_source
        try:
            from opensim.plot_dialog import PlotDialog
        except ImportError as error:
            raise ValueError("Install the desktop plotting dependencies to use result plots") from error
        source = load_plot_source(self.workspace, self.require_project())
        dialog = self.plot_dialogs.get(source.job_id)
        if dialog is None:
            dialog = PlotDialog(self.workspace, source, self.theme != "light", self)
            dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            self.plot_dialogs[source.job_id] = dialog
            dialog.finished.connect(lambda code, key=source.job_id: self.plot_dialogs.pop(key, None))
        dialog.show()
        dialog.raise_()
        return dialog

    def save_parameters(self):
        parameters = {key: field.value() for key, field in self.fields.items()}
        parameters["mesh_size_m"] /= 1000
        parameters['cfd_mesh_size_m']/=1000
        parameters["young_Pa"] *= 1e9
        for key in ("thermal_fixed_temperature_K", "thermal_source_temperature_K"):
            parameters[key] += 273.15
        parameters.update({key: selector.currentData() for key, selector in self.selectors.items()})
        if self.workspace.ui_state()['study']=='cfd':parameters['cfd_cad_scale']=parameters['cad_scale']
        from opensim.materials import material_name
        current=self.workspace.get_project(self.require_project())['parameters']
        parameters['material_name']=material_name(current|parameters)
        self.workspace.set_parameters(self.require_project(), parameters)
        self.dirty = False
        self.details_note.setText("Settings saved. Prior results are retained in job history.")

    def mesh(self):
        self.save_parameters()
        self.workspace.start_job(self.require_project(), 'cfd_mesh' if self.workspace.ui_state()['study']=='cfd' else "mesh")
        self.workspace.show_project(self.project_id, 'geometry' if self.workspace.ui_state()['study']=='cfd' else "mesh")

    def solve(self):
        self.save_parameters()
        self.workspace.start_job(self.require_project(), "solve")
        self.workspace.show_project(self.project_id, "results")

    def thermal(self):
        self.save_parameters()
        self.workspace.start_job(self.require_project(), "thermal")
        self.workspace.show_project(self.project_id, "thermal")

    def modal(self):
        self.save_parameters()
        self.workspace.start_job(self.require_project(), "modal")
        self.workspace.show_project(self.project_id, "modal")

    def convergence(self):
        self.save_parameters()
        self.workspace.select_study(self.require_project(), "convergence")
        self.workspace.start_job(self.require_project(), "convergence")
        self.status_label.setText("Convergence study started: each mesh is finer than the last. Stop computing ends it early.")
