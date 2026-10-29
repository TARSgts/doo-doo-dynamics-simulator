"""A separate CFD workbench keeps benchmark settings away from CAD supports."""
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtWidgets import (QComboBox, QDialog, QDoubleSpinBox, QFileDialog,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QSpinBox, QSplitter, QVBoxLayout, QWidget)
from PySide6.QtWebEngineWidgets import QWebEngineView

from opensim.cfd_parameters import CFD_DEFAULTS, CASE_LABELS, CASE_LIMITS
from opensim.job_progress import STAGE_LABELS


class CFDDialog(QDialog):
    def __init__(self, workspace, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        self.project_id = None
        self.job_id = None
        self.result_folder = None
        self.setWindowTitle('Doo Doo Dynamics · CFD workbench')
        self.resize(1250, 850)
        self.setMinimumSize(800, 560)
        layout = QVBoxLayout(self)
        heading = QLabel('CFD · numerical flow studies')
        heading.setStyleSheet('font-size:22px;font-weight:600;padding:4px')
        layout.addWidget(heading)
        intro = QLabel('Choose a flow model or import a CAD fluid volume. Flow studies have their own projects and do not change your structural model.')
        intro.setWordWrap(True); layout.addWidget(intro)
        history = QHBoxLayout()
        self.history = QComboBox()
        self.history.setMinimumWidth(250)
        history.addWidget(QLabel('Saved CFD studies')); history.addWidget(self.history, 1)
        self.new_button = QPushButton('New study')
        self.new_button.setToolTip('Start a separate CFD study without changing any CAD project.')
        history.addWidget(self.new_button)
        layout.addLayout(history)
        split = QSplitter(Qt.Orientation.Horizontal)
        panel = QWidget(); left = QVBoxLayout(panel)
        self.case = QComboBox()
        for key, label in CASE_LABELS.items(): self.case.addItem(label, key)
        self.case.setToolTip('Cylinder and plate use 2D inviscid flow; pipe uses viscous laminar flow.')
        left.addWidget(self.case)
        self.scope = QLabel(); self.scope.setWordWrap(True)
        self.scope.setStyleSheet('padding:10px;border:1px solid #71829a;border-radius:5px;')
        left.addWidget(self.scope)
        self.cad_controls=QWidget();cad_layout=QVBoxLayout(self.cad_controls);cad_layout.setContentsMargins(0,0,0,0)
        self.cad_note=QLabel('No fluid volume imported');self.cad_note.setWordWrap(True);cad_layout.addWidget(self.cad_note)
        import_button=QPushButton('Import CAD fluid volume');import_button.clicked.connect(self.import_fluid);cad_layout.addWidget(import_button)
        import_button.setToolTip('Import the closed volume occupied by fluid. A solid body is not an external-flow domain; construct the surrounding fluid volume in CAD first.')
        inspect=QPushButton('Inspect mesh / choose ports');inspect.clicked.connect(self.inspect_mesh);cad_layout.addWidget(inspect)
        inspect.setToolTip('Generate the fluid mesh, inspect face IDs and pick inlet/outlet faces. Defaults are X-min and X-max.')
        self.inlet_ids=QLineEdit();self.outlet_ids=QLineEdit()
        self.inlet_ids.setPlaceholderText('Inlet face IDs (blank: X-min)');self.outlet_ids.setPlaceholderText('Outlet face IDs (blank: X-max)')
        self.inlet_ids.setToolTip('Comma-separated CAD face IDs carrying inlet pressure traction; no velocity is prescribed. Picking new faces replaces any saved box filter.')
        self.outlet_ids.setToolTip('Comma-separated CAD face IDs carrying zero-gauge-pressure traction; other faces are no-slip walls.')
        cad_layout.addWidget(self.inlet_ids);cad_layout.addWidget(self.outlet_ids)
        row=QHBoxLayout();cad_layout.addLayout(row)
        for text,role in [('Pick inlet','support'),('Pick outlet','load')]:
            b=QPushButton(text);b.clicked.connect(lambda checked=False,r=role:self.pick_port(r));row.addWidget(b)
        save_ports=QPushButton('Use picked port faces');save_ports.clicked.connect(self.save_ports);cad_layout.addWidget(save_ports)
        left.addWidget(self.cad_controls);self.port_regions={'cfd_inlet_region':{},'cfd_outlet_region':{}};self.mesh_signature=None
        inputs = QWidget(); self.form = QFormLayout(inputs)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.fields = {}
        specs = [
            ('cfd_resolution', 'Panels / radial cells', 12, 256, 0),
            ('cfd_speed_m_s', 'Freestream speed (m/s)', .000001, 10000, 4),
            ('cfd_density_kg_m3', 'Density (kg/m³)', .000001, 1e6, 5),
            ('cfd_viscosity_Pa_s', 'Viscosity (Pa·s)', 1e-9, 1e6, 9),
            ('cfd_sound_speed_m_s', 'Speed of sound (m/s)', .001, 1e6, 3),
            ('cfd_radius_m', 'Radius (mm)', .00001, 1e7, 4),
            ('cfd_length_m', 'Pipe length (mm)', .00001, 1e8, 3),
            ('cfd_pressure_drop_Pa', 'Pressure drop (Pa)', 1e-9, 1e9, 7),
            ('cfd_chord_m', 'Plate chord (mm)', .00001, 1e7, 4),
            ('cfd_alpha_min_deg', 'Start α (degrees)', -10, 10, 2),
            ('cfd_alpha_max_deg', 'End α (degrees)', -10, 10, 2),
            ('cfd_alpha_step_deg', 'Step α (degrees)', .01, 20, 2),
            ('cfd_mesh_size_m','Flow mesh size (mm)',.00001,1e7,4),
            ('cfd_cad_scale','CAD scale to meters',.000001,1e6,6),
        ]
        for key, title, low, high, decimals in specs:
            field = QSpinBox() if decimals == 0 else QDoubleSpinBox()
            if decimals: field.setDecimals(decimals)
            field.setRange(low, high)
            field.setMinimumWidth(95)
            # Ignore the wheel even when focused, matching the main properties.
            field.wheelEvent = lambda event: event.ignore()
            field.setToolTip({
                'cfd_resolution': 'More panels/cells improve spatial resolution; 12–256. Pipe errors should decrease as this increases.',
                'cfd_speed_m_s': 'Uniform upstream velocity. External-flow Mach must be at most 0.3.',
                'cfd_density_kg_m3': 'Fluid mass per volume. Air example: 1.225 kg/m³. Used for forces and Reynolds number.',
                'cfd_viscosity_Pa_s': 'Dynamic viscosity. Used by the pipe solver; external models have no viscous physics.',
                'cfd_sound_speed_m_s': 'Used to check the incompressible-flow Mach limit; default 343 m/s.',
                'cfd_radius_m': 'Cylinder or pipe radius, displayed in millimeters and stored in meters.',
                'cfd_length_m': 'Length over which the pipe pressure drop acts. Flow is assumed fully developed.',
                'cfd_pressure_drop_Pa': 'Positive inlet-minus-outlet pressure difference. Reduce it if pipe Re reaches 2000.',
                'cfd_chord_m': 'Leading-to-trailing-edge length of the infinitely thin 2D plate, in millimeters.',
                'cfd_alpha_min_deg': 'First angle of attack. Small-angle attached-flow study only, within ±10°.',
                'cfd_alpha_max_deg': 'Last angle of attack. Positive alpha gives positive lift. Stall is not modeled.',
                'cfd_alpha_step_deg': 'Positive spacing between angles; at most 101 samples. The end angle is always included.',
                'cfd_mesh_size_m':'Target tetrahedral edge size in millimeters. First CAD stage allows up to 7000 nodes / 35000 elements.',
                'cfd_cad_scale':'Multiply CAD coordinates by this number to obtain meters. Use 0.001 for millimeter CAD, 1 for meter CAD.',
            }[key])
            self.fields[key] = field
            self.form.addRow(title, field)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(inputs)
        left.addWidget(scroll, 1)
        self.run_button = QPushButton('Run flow study')
        self.run_button.setToolTip('Save inputs in this CFD project and solve in the background. Reports contain plots, comparison and exportable data.')
        self.verify_button = QPushButton('Verify all three models')
        self.verify_button.setToolTip('Run cylinder, pipe and flat-plate comparisons at three spatial resolutions, with fixed acceptance thresholds.')
        left.addWidget(self.run_button); left.addWidget(self.verify_button)
        split.addWidget(panel)
        self.viewer = QWebEngineView()
        self.viewer.setHtml('<body style="background:#101923;color:#dce8f4;font:18px Segoe UI;padding:24px"><h2>Ready for a flow study</h2><p>Select a case and choose Run flow study.</p><p>The flat-plate case sweeps angle of attack and plots CL against α. Cylinder and pipe cases compare pressure or velocity against known solutions.</p></body>')
        split.addWidget(self.viewer); split.setSizes([340, 870]); layout.addWidget(split, 1)
        footer = QHBoxLayout()
        self.status = QLabel('Ready')
        self.progress = QProgressBar(); self.progress.setRange(0, 1); self.progress.setValue(0)
        self.stop_button = QPushButton('Stop'); self.stop_button.setEnabled(False)
        self.stop_button.setToolTip('Stop this CFD worker; partial output stays in its job folder.')
        self.export_button = QPushButton('Export CSV'); self.export_button.setEnabled(False)
        self.export_button.setToolTip('Save a copy of the current plotted numerical and reference data.')
        for w in (self.status, self.progress, self.stop_button, self.export_button): footer.addWidget(w)
        layout.addLayout(footer)
        self.new_button.clicked.connect(self.new_study)
        self.case.currentIndexChanged.connect(self.update_case)
        self.run_button.clicked.connect(lambda: self.run(False))
        self.verify_button.clicked.connect(lambda: self.run(True))
        self.stop_button.clicked.connect(self.stop)
        self.export_button.clicked.connect(self.export)
        self.history.currentIndexChanged.connect(self.open_saved)
        self.timer = QTimer(self); self.timer.timeout.connect(self.poll); self.timer.start(250)
        for field in self.fields.values(): field.valueChanged.connect(self.mark_changed)
        self.case.currentIndexChanged.connect(self.mark_changed)
        self.reload_history()
        self.new_study()

    def reload_history(self):
        self.history.blockSignals(True); self.history.clear()
        self.history.addItem('New unsaved CFD study', None)
        with self.workspace.connect() as connection:
            rows = connection.execute("SELECT DISTINCT p.id,p.name,p.created FROM projects p LEFT JOIN jobs j ON j.project_id=p.id WHERE j.kind IN ('cfd','cfd_validation') OR json_extract(p.parameters,'$.cfd_case')='cad' ORDER BY p.created DESC").fetchall()
        for row in rows: self.history.addItem(row['name'], row['id'])
        self.history.setCurrentIndex(max(0, self.history.findData(self.project_id)))
        self.history.blockSignals(False)

    def load_inputs(self, p):
        self.case.setCurrentIndex(self.case.findData(p['cfd_case']))
        for key, field in self.fields.items():
            field.setValue(p[key]*1000 if key in {'cfd_radius_m','cfd_length_m','cfd_chord_m','cfd_mesh_size_m'} else p[key])
        self.port_regions={k:p[k].copy() for k in ('cfd_inlet_region','cfd_outlet_region')}
        self.inlet_ids.setText(', '.join(map(str,p['cfd_inlet_region'].get('faces',[]))))
        self.outlet_ids.setText(', '.join(map(str,p['cfd_outlet_region'].get('faces',[]))))
        self.update_case()

    def new_study(self):
        if self.job_id: return
        self.project_id = None; self.result_folder = None
        self.history.setCurrentIndex(0)
        self.load_inputs(CFD_DEFAULTS)
        self.export_button.setEnabled(False); self.status.setText('New study')
        self.viewer.setHtml('<body style="background:#101923;color:#dce8f4;font:18px Segoe UI;padding:24px"><h2>New flow study</h2><p>Choose a case, enter its conditions, then Run flow study.</p><p>Verify all three models runs the cylinder, pipe and flat-plate theory comparisons at three resolutions.</p></body>')

    def mark_changed(self):
        if self.result_folder and not self.job_id:
            self.status.setText('Inputs changed — rerun to update result')
            self.export_button.setEnabled(False)

    def update_case(self):
        case = self.case.currentData()
        if not case: return
        self.scope.setText(CASE_LIMITS[case])
        self.cad_controls.setVisible(case=='cad')
        if case=='cad' and self.fields['cfd_pressure_drop_Pa'].value()==.1:
            self.fields['cfd_pressure_drop_Pa'].setValue(.00001)
        common = {'cfd_resolution', 'cfd_density_kg_m3', 'cfd_viscosity_Pa_s'}
        if case=='cad':common.discard('cfd_resolution')
        visible = common | ({'cfd_mesh_size_m','cfd_cad_scale','cfd_pressure_drop_Pa'} if case=='cad' else {'cfd_radius_m','cfd_length_m','cfd_pressure_drop_Pa'} if case == 'pipe' else
                  {'cfd_speed_m_s','cfd_sound_speed_m_s'} | ({'cfd_radius_m'} if case == 'cylinder' else
                  {'cfd_chord_m','cfd_alpha_min_deg','cfd_alpha_max_deg','cfd_alpha_step_deg'}))
        for key, field in self.fields.items(): self.form.setRowVisible(field, key in visible)

    def inputs(self):
        p = {'cfd_case': self.case.currentData()}
        for key, field in self.fields.items():
            p[key] = field.value()/1000 if key in {'cfd_radius_m','cfd_length_m','cfd_chord_m','cfd_mesh_size_m'} else field.value()
        for key,control in (('cfd_inlet_region',self.inlet_ids),('cfd_outlet_region',self.outlet_ids)):
            region=self.port_regions[key].copy();ids=[int(s.strip()) for s in control.text().split(',') if s.strip()]
            region.pop('faces',None)
            if ids:region['faces']=ids
            p[key]=region
        return p

    def import_fluid(self):
        if self.job_id:return
        file,_=QFileDialog.getOpenFileName(self,'Import closed CAD fluid volume','','CAD (*.step *.stp *.iges *.igs *.brep *.stl *.obj *.3mf)')
        if not file:return
        try:
            if not self.project_id:self.project_id=self.workspace.create_project('CFD / CAD fluid volume / '+datetime.now().strftime('%H:%M:%S'))['id']
            self.workspace.import_cad(self.project_id,file)
            self.case.setCurrentIndex(self.case.findData('cad'))
            self.inlet_ids.clear();self.outlet_ids.clear();self.port_regions={'cfd_inlet_region':{},'cfd_outlet_region':{}}
            self.cad_note.setText(Path(file).name);self.mesh_signature=None;self.result_folder=None
            self.workspace.set_parameters(self.project_id,self.inputs());self.export_button.setEnabled(False)
        except Exception as error:QMessageBox.warning(self,'Fluid-volume import',str(error))

    def inspect_mesh(self):
        try:
            if not self.project_id:raise ValueError('Import a CAD fluid volume first')
            p=self.inputs()
            self.workspace.set_parameters(self.project_id,p|{'mesh_size_m':p['cfd_mesh_size_m'],'cad_scale':p['cfd_cad_scale'],'element_order':1})
            self.job_id=self.workspace.start_job(self.project_id,'cfd_mesh')['id'];self.result_folder=None;self.set_running(True)
        except Exception as error:QMessageBox.warning(self,'Fluid mesh',str(error))

    def pick_port(self,role):
        try:
            signature=(self.project_id,self.inputs()['cfd_mesh_size_m'],self.inputs()['cfd_cad_scale'])
            if self.mesh_signature!=signature:raise ValueError('Inspect the mesh before picking ports, and after changing mesh settings')
            region=self.inputs()['cfd_inlet_region' if role=='support' else 'cfd_outlet_region']
            self.viewer.page().runJavaScript(f"typeof setFacePicking==='function' && setFacePicking('{role}',{region.get('faces',[])})")
        except Exception as error:QMessageBox.warning(self,'Pick flow port',str(error))

    def save_ports(self):
        def received(data):
            if not data or not data.get('mode'):return
            for role,field in (('support',self.inlet_ids),('load',self.outlet_ids)):
                if data.get('touched',{}).get(role):
                    field.setText(', '.join(map(str,data[role])))
                    self.port_regions['cfd_inlet_region' if role=='support' else 'cfd_outlet_region']={}
            self.viewer.page().runJavaScript("setFacePicking(null)");self.mark_changed()
        self.viewer.page().runJavaScript("typeof getFaceSelection==='function' ? getFaceSelection() : null",received)

    def run(self, validation=False):
        try:
            from opensim.cfd_parameters import validate_cfd_parameters
            p = self.inputs(); validate_cfd_parameters(p)
            if not validation and p['cfd_case']=='cad' and (not self.project_id or not self.workspace.get_project(self.project_id)['cad']):
                raise ValueError('Import a closed CAD fluid volume before running CAD flow')
            if validation or not self.project_id:
                name = 'Validation / all three' if validation else CASE_LABELS[p['cfd_case']]
                self.project_id = self.workspace.create_project('CFD / '+name+' / '+datetime.now().strftime('%Y-%m-%d %H:%M:%S'))['id']
            self.workspace.set_parameters(self.project_id, p)
            job = self.workspace.start_job(self.project_id, 'cfd_validation' if validation else 'cfd')
            self.job_id = job['id']; self.result_folder = None
            self.reload_history(); self.set_running(True)
            self.status.setText('Running…')
            self.viewer.setHtml('<body style="background:#101923;color:#dce8f4;font:18px Segoe UI;padding:24px"><h2>Solving…</h2><p>The flow study runs in the background. Its plot and saved inputs will appear here when complete.</p></body>')
        except Exception as error: QMessageBox.warning(self, 'CFD study', str(error))

    def set_running(self, running):
        for widget in (self.case, self.history, self.new_button, self.run_button, self.verify_button,self.cad_controls, *self.fields.values()): widget.setEnabled(not running)
        self.stop_button.setEnabled(running); self.export_button.setEnabled(not running and self.result_folder is not None)
        self.progress.setRange(0, 0 if running else 1)
        if not running: self.progress.setValue(1)

    def poll(self):
        if not self.job_id: return
        job = self.workspace.get_job(self.job_id)
        self.status.setText(STAGE_LABELS.get(job['progress_stage'], job['status']))
        if job['status'] in {'queued','running'}: return
        self.job_id = None
        if job['status'] == 'completed':
            if job['kind']=='cfd_mesh':
                self.mesh_signature=(self.project_id,self.inputs()['cfd_mesh_size_m'],self.inputs()['cfd_cad_scale'])
                self.viewer.setUrl(QUrl.fromLocalFile(str(self.workspace.job_directory(job['id'])/'preview.html')))
                self.cad_note.setText('Mesh ready. CAD face IDs: '+', '.join(str(f['id']) for f in job['result']['cad_faces']))
                self.status.setText('Pick ports or use X-min / X-max defaults');self.set_running(False);return
            folder = self.workspace.job_directory(job['id'])/('cfd_validation' if job['kind']=='cfd_validation' else 'cfd')
            self.show_result(folder)
            self.status.setText('Verification '+job['result']['result'] if job['kind']=='cfd_validation' else 'Completed')
        else:
            self.status.setText(job['error'] or job['status'])
            if job['status'] == 'failed': QMessageBox.warning(self, 'CFD study failed', job['error'])
        self.set_running(False)
        if job['status'] != 'completed': self.progress.setValue(0)

    def show_result(self, folder):
        self.mesh_signature=None
        self.result_folder = Path(folder)
        self.viewer.setUrl(QUrl.fromLocalFile(str(self.result_folder/'report.html')))
        self.export_button.setEnabled((self.result_folder/'data.csv').is_file())
        self.progress.setRange(0,1);self.progress.setValue(1)

    def open_saved(self):
        pid = self.history.currentData()
        if not pid or self.job_id: return
        self.project_id = pid
        project = self.workspace.get_project(pid); self.load_inputs(project['parameters'])
        self.cad_note.setText('Fluid volume imported' if project['cad'] else 'No fluid volume imported')
        self.cad_note.setToolTip(project['cad'] or 'Import the closed volume occupied by fluid')
        job = next((j for j in self.workspace.list_jobs(pid) if j['kind'] in {'cfd','cfd_validation'} and self.workspace.job_is_current(j,project)), None)
        self.result_folder = None; self.export_button.setEnabled(False)
        if job and job['status'] in {'queued','running'}:
            self.job_id = job['id']; self.set_running(True)
        elif job and job['status']=='completed':
            self.show_result(self.workspace.job_directory(job['id'])/job['kind'])
            self.status.setText('Saved result')
        else: self.status.setText('No completed result for these inputs')

    def stop(self):
        if self.job_id:
            try: self.workspace.cancel_job(self.job_id)
            except ValueError: pass

    def export(self):
        if not self.result_folder: return
        name, _ = QFileDialog.getSaveFileName(self, 'Save CFD data', 'cfd-data.csv', 'CSV (*.csv)')
        if name:
            import shutil
            source = self.result_folder/'data.csv'
            if Path(name).resolve() != source.resolve(): shutil.copyfile(source, name)
