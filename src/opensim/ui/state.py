"""State for the desktop workbench."""
from opensim.application.studies import STUDIES, study_for_job
from opensim.ui.impact import IMPACT_UNITS
import json
from pathlib import Path
import time
from PySide6.QtCore import Qt, QSignalBlocker, QUrl
from PySide6.QtWidgets import QTreeWidgetItem
from opensim.cat_language import cat_text
from opensim.job_progress import STAGE_LABELS, elapsed_label
from opensim.load_settings import NORMAL_AXES
from opensim.discord_presence import activity_for


class StateMixin:
    def refresh(self):
        self.workspace.heartbeat()
        state = self.workspace.ui_state()
        thermal_view = state['view'] == 'thermal'
        flow_view=state['view'] in {'cfd','cfd_slice'}
        blocker = QSignalBlocker(self.result_component)
        labels = ('Heat flux |q|', 'Heat flux X', 'Heat flux Y', 'Heat flux Z', 'Temperature (°C)') if thermal_view else ('Total |U|', 'Ux', 'Uy', 'Uz', 'von Mises stress')
        if flow_view:labels=('Speed (m/s)','Velocity X','Velocity Y','Velocity Z','Pressure (Pa)')
        for index, label in enumerate(labels):
            self.result_component.setItemText(index, label)
        if thermal_view != getattr(self, 'previous_thermal_view', False):
            self.result_component.setCurrentIndex(4 if thermal_view else 0)
        self.previous_thermal_view = thermal_view
        if flow_view and state['view']!=getattr(self,'previous_flow_view',None):self.result_component.setCurrentIndex(4 if state['view']=='cfd' else 0)
        self.previous_flow_view=state['view'] if flow_view else None
        del blocker
        self.result_component.model().item(4).setEnabled(state["view"] in {"results", "thermal",'cfd','cfd_slice'})
        self.result_component.setToolTip("Choose temperature in °C or heat-flux magnitude / signed global X/Y/Z components in W/m²." if thermal_view else "Choose total movement, movement along X/Y/Z, or recovered von Mises stress.")
        if flow_view:self.result_component.setToolTip('Choose solved speed, signed velocity X/Y/Z in m/s, or gauge pressure in Pa. Slice and surface fields use the same undeformed fluid solution.')
        if state["view"] == "modal" and self.result_component.currentIndex() == 4:
            blocker = QSignalBlocker(self.result_component)
            self.result_component.setCurrentIndex(0)
            del blocker
        if state["theme"] != self.theme:
            self.apply_theme()
        projects = self.workspace.list_open_projects()
        selected = state["project_id"]
        project_changed = selected != self.project_id
        if selected != self.project_id:
            self.project_id = selected
            self.project_revision = None
            self.dirty = False
        project = self.workspace.get_project(selected) if selected else None
        if self.face_pick_session and (not project or selected != self.face_pick_session["project_id"]
                or project["revision"] != self.face_pick_session["revision"] or state["study"] != self.face_pick_session["study"]):
            self.cancel_face_picking()
        if project:
            self.region_note.setText("Support region: " + json.dumps(project["parameters"]["support_region"]) + "\nLoad region: " + json.dumps(project["parameters"]["load_region"]))
        if project_changed and project:
            self.camera.setCurrentIndex(4)
        jobs = self.workspace.list_jobs(selected,limit=100) if selected else []
        signature = ([(entry["id"], entry["name"], entry["revision"]) for entry in projects],
                     [(job["id"], job["status"]) for job in jobs], selected, state["study"], state["view"])
        if signature != self.tree_signature:
            self.tree_signature = signature
            self.tree.clear()
            for entry in projects:
                root = QTreeWidgetItem([entry["name"]])
                root.setToolTip(0, str(self.workspace.root / entry["id"]) + "\nRight-click to rename, close or find files.")
                root.setData(0, Qt.ItemDataRole.UserRole, (entry["id"], "geometry"))
                self.tree.addTopLevelItem(root)
                self.add_study_tree(root, entry, state)
                root.setExpanded(entry["id"] == selected)
        if project and not self.dirty and self.project_revision != project["revision"]:
            for key, field in self.fields.items():
                value = project["parameters"][key]
                if key in IMPACT_UNITS:value/=IMPACT_UNITS[key]
                if key in {"mesh_size_m",'cfd_mesh_size_m'}:
                    value *= 1000
                if key == "young_Pa":
                    value /= 1e9
                if key in {"thermal_fixed_temperature_K", "thermal_source_temperature_K"}:
                    value -= 273.15
                blocker = QSignalBlocker(field)
                field.setValue(value)
                del blocker
            for key, selector in self.selectors.items():
                blocker = QSignalBlocker(selector)
                selector.setCurrentIndex(selector.findData(project["parameters"][key]))
                del blocker
            self.project_revision = project["revision"]
        active = next((job for job in jobs if job["status"] in {"queued", "running"}), None)
        self.discord.set_activity(activity_for(state, active, self.opened_at, has_project=bool(project)))
        for job in jobs:
            if (job["kind"] == "convergence" and job["status"] == "completed" and job["id"] not in self.shown_convergence
                    and job["updated"] >= self.opened_at and project and self.workspace.job_is_current(job,project)):
                self.shown_convergence.add(job["id"])  # open each finished study once, only if it finished while the app was open
                try:
                    self.show_convergence_report()
                except ValueError:
                    pass
        self.sync_force_direction()
        matching = next((job for job in jobs if project and study_for_job(job['kind'],job['payload'].get('study','static'))==state['study'] and self.workspace.job_is_current(job,project)), None)
        self.update_job_progress(active or matching)
        self.apply_button.setEnabled(bool(project) and not active)
        plot_kind = STUDIES[state["study"]].job_kind
        can_plot = bool(project) and not self.dirty and self.workspace.latest_result_job(selected,[plot_kind]) is not None
        for button in self.result_plot_buttons:
            button.setEnabled(can_plot)
        self.close_project_button.setEnabled(bool(project))
        for action in self.project_actions:
            action.setEnabled(bool(project))
        for field in self.fields.values():
            field.setEnabled(bool(project) and not active)
        for selector in self.selectors.values():
            selector.setEnabled(bool(project) and not active)
        self.selectors["load_surface"].setEnabled(bool(project) and not active and self.selectors["load_kind"].currentData() == "traction")
        if state["study"] == "modal":
            self.fields["load_N"].setEnabled(False)
            self.selectors["load_axis"].setEnabled(False)
            self.selectors["load_kind"].setEnabled(False)
            self.selectors["load_surface"].setEnabled(False)
        for button in self.analysis_buttons:
            button.setEnabled(bool(project) and not active)
        self.loads_button.setEnabled(bool(project) and not active and state['study'] in {'static','convergence'})
        self.update_study_panel()
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
            self.deformation.setEnabled(state["view"] not in {"modal", "thermal"} and state['study'] not in {'cfd','impact'})
            self.animate_mode.setEnabled(bool(modal_result))
            self.export_gif_button.setEnabled(bool(modal_result) and self.gif_export is None)
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
                    and preview["mesh"] == [project["parameters"][key] for key in ("mesh_size_m", "cad_scale", "element_order")]
                    and (state['study']!='cfd' or preview.get('flow_signature')==[project['parameters'][k] for k in ('cfd_backend','cfd_domain_mode','cfd_flow_axis','cfd_padding','cfd_mesh_size_m','cfd_cad_scale')])):
                candidate = Path(preview["artifact"])
                if candidate.is_file():
                    artifact = candidate
            view_key = str(artifact), state["view"]
            if self.face_pick_session and (view_key != self.face_pick_session["view"] or active):
                self.cancel_face_picking()
            if view_key != self.loaded_view:
                self.loaded_view = view_key
                view_title={'cfd_slice':'Velocity slice','cfd':'Surface pressure','cfd_report':'Flow convergence / exports','impact':'Elastic plate response'}.get(state['view'],state['view'])
                self.viewport_title.setText(project["name"].upper() + "  /  " + view_title.upper())
                if artifact:
                    url = QUrl.fromLocalFile(str(artifact if artifact.name=='report.html' else self.viewer_for_artifact(artifact)))
                    url.setQuery("desktop=1")
                    self.view.setUrl(url)
                else:
                    self.view.setHtml(self.impact_placeholder() if state['study']=='impact' else self.empty_view())
            output = []
            for job in jobs[:8]:
                output.append(f"[{job['status'].upper()}] {job['kind']}  ·  {job['id'][:8]}  ·  input revision {job['revision']}")
                if job["error"]:
                    output.append("  " + job["error"])
                if job["result"]:
                    result = job["result"]
                    output.append(f"  {result['plate_modes']} plate modes · {result['integration_steps']:,} integration steps" if result.get('analysis')=='impact' else f"  {result['nodes']:,} nodes · {result['tetrahedra']:,} tetrahedra")
                    repair = result.get("mesh_repair") or {}
                    if repair:
                        changes = [f"{repair.get('removed_duplicate_triangles', 0)} duplicate triangles removed",
                                   f"{repair.get('reoriented_triangles', 0)} triangles reoriented",
                                   f"{repair.get('removed_degenerate_triangles', 0)} degenerate triangles removed"]
                        if repair.get("patch_retry_used"):
                            changes.append("face patches automatically rebuilt; review picked support/load faces")
                        output.append("  Automatic surface preparation: " + "; ".join(changes) + ". Original file unchanged.")
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
                    elif result.get("analysis") == "thermal":
                        output.append(f"  Temperature: {result['minimum_temperature_K']-273.15:.5g} → {result['maximum_temperature_K']-273.15:.5g} °C; energy imbalance {result['relative_energy_imbalance']:.2e}")
            text = "\n".join(output) or "No jobs yet. Import CAD or create a test plate."
            if self.messages.toPlainText() != text:
                self.messages.setPlainText(text)
            try:
                if state['study']=='impact':
                    summary=self.workspace.get_impact_results(selected)['summary']
                    self.result_cards[0].setText(f"Peak contact force\n{summary['maximum_contact_force_N']:.5g} N")
                    self.result_cards[1].setText(f"Peak patch deflection\n{summary['maximum_patch_deflection_m']*1000:.5g} mm")
                    self.result_cards[2].setText(f"Energy balance error\n{summary['maximum_relative_energy_error']*100:.4g}%")
                    self.legend.setText('  Elastic plate drop test · Modal bending / compliant contact · No damage or CAD impact prediction')
                    self.apply_language();return
                if state['study']=='cfd' and state['view'] in {'cfd','cfd_slice','cfd_report'}:
                    summary=self.workspace.get_cfd_results(selected)['summary']
                    if summary.get('analysis') in {'cfd','cfd_validation'}:
                        self.result_cards[0].setText('CFD reference study\n'+summary.get('case','All three models'))
                        self.result_cards[1].setText('Verification\n'+summary.get('result','Numerical benchmark'))
                        self.result_cards[2].setText('Scope\nSee reference report')
                        self.legend.setText('  Analytical reference studies · Own CAD uses the Fluid Dynamics study’s model, fluid mesh and boundary conditions')
                        self.apply_language();return
                    self.result_cards[0].setText(f"Maximum speed\n{summary.get('maximum_speed_m_s',0):.5g} m/s")
                    self.result_cards[1].setText(f"Outlet flow\n{summary.get('outlet_flow_m3_s',0):.5g} m³/s")
                    self.result_cards[2].setText(f"Flow balance error\n{summary.get('relative_mass_imbalance',0):.2e}")
                    self.legend.setText('  Fluid dynamics · '+summary.get('method',summary.get('analysis',''))+' · Inspect convergence and refine the mesh before interpreting forces')
                    self.apply_language();return
                if state['view'] == 'thermal':
                    summary = self.workspace.get_thermal_results(selected)['summary']
                    self.result_cards[0].setText(f"Minimum temperature\n{summary['minimum_temperature_K']-273.15:.5g} °C")
                    self.result_cards[1].setText(f"Maximum temperature\n{summary['maximum_temperature_K']-273.15:.5g} °C")
                    self.result_cards[2].setText(f"Heat balance residual\n{summary['relative_energy_imbalance']:.2e}")
                    self.legend.setText(f"  Steady thermal conduction · Maximum |q| {summary['maximum_heat_flux_W_m2']:.5g} W/m² · Undeformed geometry · Other surfaces insulated")
                    self.apply_language()
                    return
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
                if summary.get('load_cases'):
                    self.result_cards[1].setText(f"Load-weighted response\n{summary['load_weighted_response_m']*1000:.6g} mm")
                elif axis in NORMAL_AXES:
                    self.result_cards[1].setText(f"Loaded mean · along normal force\n{summary['loaded_surface_mean_normal_displacement_m'] * 1000:.6g} mm")
                else:
                    self.result_cards[1].setText(f"{location_label} U{axis}\n{tip['xyz'.index(axis)] * 1000:.6g} mm")
                self.result_cards[2].setText(f"Force balance residual\n{summary['relative_force_imbalance']:.2e}")
                self.legend.setText(f"  Displacement |U|: 0 → {summary['maximum_displacement_m'] * 1000:.6g} mm   ·   "
                                    f"{summary['tetrahedra']:,} elements   ·   Display deformation is exaggerated   ·   Drag to rotate")
                if self.result_component.currentIndex() == 4 and "maximum_von_mises_Pa" in summary:
                    self.legend.setText(f"  Recovered von Mises: 0 → {summary['maximum_von_mises_Pa'] / 1e6:.6g} MPa · Ideal fixed-edge peaks may be singular · Display deformation is exaggerated")
            except ValueError:
                if state['study']=='impact':
                    for card,title in zip(self.result_cards,('Peak contact force','Peak patch deflection','Energy balance error')):card.setText(title+'\n—')
                    self.legend.setText('  Set the plate and low-height drop conditions, then Run elastic drop test')
                    self.apply_language();return
                for card, title in zip(self.result_cards, ("Maximum |U|", "Tip displacement", "Force balance")):
                    card.setText(title + "\n—")
                label = "No solved result for current settings" if state["view"] in {"results", "modal", "thermal"} else "Undeformed geometry / mesh preview"
                self.legend.setText(f"  {label}   ·   Drag to rotate")
        if not project:
            self.loaded_view = None
            if project_changed:
                self.view.setHtml(self.empty_view())
            self.modal_tools.hide()
            self.viewport_title.setText("NO PROJECT OPEN")
            self.status_label.setText("Open a saved project or create a new one")
            self.messages.clear()
            self.legend.setText("  Open project… shows your saved project library.")
            for card, title in zip(self.result_cards, ("Maximum |U|", "Tip displacement", "Force balance")):
                card.setText(title + "\n—")
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
