"""Selection for the desktop workbench."""
import json
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QLabel, QPlainTextEdit, QVBoxLayout


class SelectionMixin:
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
        roles = (("support_region", "Fixed support"),) if self.workspace.ui_state()["study"] == "modal" or project['parameters']['load_cases'] else (("support_region", "Fixed support"), ("load_region", "Uniform traction"))
        if self.workspace.ui_state()['study']=='cfd':
            roles=(('cfd_inlet_region','Flow inlet'),('cfd_outlet_region','Flow outlet'));dialog.setWindowTitle('Flow inlet / outlet')
            note.setText('Choose faces from the fluid mesh. Empty selections use automatic ports. The regions are independent of structural and thermal boundaries.')
        if self.workspace.ui_state()["study"] == "thermal":
            roles = (("thermal_fixed_region", "Fixed temperature"), ("thermal_source_region", "Second temperature / heat input"))
            dialog.setWindowTitle("Thermal boundary regions")
            note.setText("Choose two separate thermal surfaces by face IDs or boxes in mm. Empty regions use X-min and X-max. These thermal selections do not change structural supports or forces. Other surfaces are insulated.")
        if len(roles) == 1:
            dialog.setWindowTitle("Modal fixed support region" if self.workspace.ui_state()['study']=='modal' else "Fixed support region")
            note.setText("Choose fully fixed support faces, optionally filtered by a box in mm. Empty support uses X-min. Independent force surfaces are edited per load entry; modal analysis ignores static forces.")
        for key, caption in roles:
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
            if job["status"] == "completed" and self.workspace.job_is_current(job,project) and job.get("result"):
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
                if parameters.get("load_region"):
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
        if self.workspace.ui_state()['study']=='cfd' and self.workspace.ui_state()['view']!='mesh':
            if not any(j['kind']=='cfd_mesh' and j['status']=='completed' for j in self.workspace.list_jobs(self.require_project())):
                raise ValueError('Build the fluid mesh before selecting inlet/outlet faces')
            def ready(ok):
                self.view.loadFinished.disconnect(ready)
                if ok:self.safe(lambda:self.begin_face_picking(mode))
            self.view.loadFinished.connect(ready);self.workspace.show_project(self.project_id,'mesh');self.refresh();return
        project = self.workspace.get_project(self.require_project())
        if mode == "load" and self.workspace.ui_state()["study"] == "modal":
            raise ValueError("Modal studies use fixed supports only. Select Static Structural or Convergence to apply forces")
        if mode=='load' and project['parameters']['load_cases'] and self.workspace.ui_state()['study'] in {'static','convergence'} and not getattr(self,'load_pick_callback',None):
            raise ValueError('Use Independent forces / pressures, choose an entry, then Pick faces for this load')
        if self.dirty:
            raise ValueError("Apply settings and generate a mesh before picking faces")
        if any(job["status"] in {"queued", "running"} for job in self.workspace.list_jobs(project["id"])):
            raise ValueError("Wait for the current job before picking faces")
        if self.face_pick_session:
            self.view.page().runJavaScript(f"switchFacePicking({json.dumps(mode)})")
            self.pick_note.setText("Click faces to toggle. Switch between support and force faces, then Save picked faces. Drag to rotate.")
            return
        session = {"project_id": project["id"], "revision": project["revision"], "view": self.loaded_view,
                   "study": self.workspace.ui_state()["study"]}
        self.face_pick_session = session
        parameters = project["parameters"]
        fixed_key = "thermal_fixed_region" if session['study'] == 'thermal' else "support_region"
        source_key = "thermal_source_region" if session['study'] == 'thermal' else "load_region"
        if session['study']=='cfd':fixed_key,source_key='cfd_inlet_region','cfd_outlet_region'
        initial_load_faces=getattr(self,'load_pick_initial_faces',[]) if getattr(self,'load_pick_callback',None) else parameters[source_key].get('faces',[])
        script = ("typeof setFacePicking==='function' && "
                  f"setFacePicking('support',{json.dumps(parameters[fixed_key].get('faces', []))}) && "
                  f"setFacePicking('load',{json.dumps([] if session['study'] == 'modal' else initial_load_faces)}) && "
                  f"switchFacePicking({json.dumps(mode)})")
        def started(ready):
            if self.face_pick_session is not session:
                return
            if not ready:
                self.cancel_face_picking()
                self.pick_note.setText("Generate a new mesh once to enable clickable CAD faces for this model.")
                return
            self.pick_actions.show()
            self.pick_note.setText("Click fixed support faces (cyan), then Save picked faces. Edited support faces replace box filters." if session["study"] == "modal" else "Click to toggle whole faces. Cyan = fixed support; orange = force. Switch roles, then Save picked faces. Edited regions replace box filters.")
            if session['study'] == 'thermal':
                self.pick_note.setText("Cyan = fixed temperature; orange = second temperature or heat input. Select separate faces, then Save picked faces.")
        self.view.page().runJavaScript(script, started)

    def clear_picked_faces(self):
        if self.face_pick_session:
            self.view.page().runJavaScript("clearPickedFaces()")

    def cancel_face_picking(self):
        self.face_pick_session = None
        self.pick_actions.hide()
        self.view.page().runJavaScript("if(typeof setFacePicking==='function')setFacePicking(null)")
        self.pick_note.setText("Pick fixed support faces or use Support region." if self.workspace.ui_state()["study"] == "modal" else "Pick faces on the model, or enter face IDs in Support / load regions.")
        callback=getattr(self,'load_pick_callback',None);self.load_pick_callback=None
        if callback:callback()

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
                or project["revision"] != session["revision"] or self.loaded_view != session["view"] or self.dirty
                or self.workspace.ui_state()["study"] != session["study"]):
            self.cancel_face_picking()
            raise ValueError("The project changed. Generate a mesh and pick faces again")
        if not isinstance(selection, dict) or selection.get("mode") not in {"support", "load"}:
            raise ValueError("No face selection is available")
        available = selection.get("available", [])
        updates = {}
        independent_region=None
        for role in ("support", "load"):
            if not selection.get("touched", {}).get(role):
                continue
            faces = selection.get(role)
            if not isinstance(faces, list) or any(type(face) is not int or face <= 0 or face not in available for face in faces):
                raise ValueError("Choose valid CAD faces from the model")
            if not faces:
                raise ValueError("Select at least one face for each edited region. Use the regions dialog to restore defaults")
            key = ("thermal_fixed_region" if role == "support" else "thermal_source_region") if session['study'] == 'thermal' else role + "_region"
            if session['study']=='cfd':key='cfd_inlet_region' if role=='support' else 'cfd_outlet_region'
            if role=='load' and getattr(self,'load_pick_callback',None):
                independent_region={'faces':sorted(set(faces))}
                continue
            updates[key] = {"faces": sorted(set(faces))}
            if role == "load" and session['study'] not in {'thermal','cfd'}:
                updates["load_kind"] = "traction"
        if updates:
            self.workspace.set_parameters(project["id"], updates)
            self.selection_preview = {"project_id": project["id"], "cad": project["cad"],
                                      "mesh": [project["parameters"][key] for key in ("mesh_size_m", "cad_scale", "element_order")],
                                      "artifact": session["view"][0]}
            if session['study']=='cfd':self.selection_preview['flow_signature']=[project['parameters'][k] for k in ('cfd_backend','cfd_domain_mode','cfd_flow_axis','cfd_padding','cfd_mesh_size_m','cfd_cad_scale')]
            self.workspace.show_project(project["id"], "geometry")
        callback=getattr(self,'load_pick_callback',None);self.load_pick_callback=None
        self.cancel_face_picking()
        if callback:callback(independent_region or updates.get('load_region'))
        self.pick_note.setText("Faces saved. Set total force and direction, then Solve." if updates else "No changes to save.")
        if independent_region:self.pick_note.setText('Faces returned to the selected independent load. Apply loads in the editor to save the change.')
        if updates and session['study'] == 'thermal':
            self.pick_note.setText("Thermal faces saved. Set temperatures or heat input, then Run thermal study.")
        self.project_revision = None
