"""CFD is a first-class study in the shared model tree and viewport."""
from PySide6.QtWidgets import QDoubleSpinBox,QSpinBox,QComboBox,QPushButton,QToolButton,QSizePolicy
from opensim.cfd_parameters import CFD_DEFAULTS
from opensim.hover_help import FIELD_HELP

CFD_HELP={
 'cfd_mesh_size_m':'Target cell size near your model, in mm. Smaller cells increase cost. Always check mesh refinement before trusting forces.',
 'cfd_speed_m_s':'Inlet or freestream speed in m/s. SU2 solves velocity-driven incompressible flow.',
 'cfd_density_kg_m3':'Fluid density. Approximate room-temperature air: 1.225 kg/m³; water: 998 kg/m³.',
 'cfd_viscosity_Pa_s':'Dynamic viscosity in Pa·s. Approximate air: 0.0000181; water: 0.001.',
 'cfd_pressure_drop_Pa':'Inlet-minus-outlet pressure in Pa for the older creeping-flow solver only.',
 'cfd_padding':'Distance from the solid to enclosure boundaries, in multiples of its largest dimension. More space reduces confinement.',
 'cfd_iterations':'Maximum solver iterations. A run must meet the convergence and mass-balance checks to become a valid result.',
 'cfd_residual_target':'Log10 of the normalized residual target; −6 means 0.000001. Smaller values are stricter.',
 'cfd_backend':'SU2 solves incompressible Navier–Stokes, with optional Spalart–Allmaras turbulence. Creeping flow is the previous pressure-driven Re≤1 model.',
 'cfd_domain_mode':'For a solid object, create surrounding air/water automatically. For a duct passage, use the imported volume as fluid.',
 'cfd_flow_axis':'Flow proceeds in the positive global X, Y or Z direction. This also chooses the automatic inlet/outlet enclosure faces.',
 'cfd_turbulence':'Laminar has no turbulence closure. Spalart–Allmaras models fully turbulent flow; wall resolution and mesh refinement still matter.',
}
FIELD_HELP.update(CFD_HELP)


class CFDStudyMixin:
    def build_cfd_properties(self,form,layout):
        self.cfd_keys=set(CFD_HELP)
        for key,title,lo,hi,decimals in [
            ('cfd_mesh_size_m','Near-model mesh (mm)',.00001,1e7,4),
            ('cfd_speed_m_s','Flow speed (m/s)',.000001,100,6),
            ('cfd_density_kg_m3','Fluid density (kg/m³)',.000001,1e6,5),
            ('cfd_viscosity_Pa_s','Dynamic viscosity (Pa·s)',1e-9,1e6,9),
            ('cfd_pressure_drop_Pa','Pressure drop (Pa)',1e-9,1e9,8),
            ('cfd_padding','Enclosure padding (× size)',1,10,1),
            ('cfd_iterations','Maximum iterations',100,20000,0),
            ('cfd_residual_target','Residual target (log10)',-12,-3,1)]:
            control=QSpinBox() if not decimals else QDoubleSpinBox()
            if decimals:control.setDecimals(decimals)
            control.setRange(lo,hi);control.setValue(CFD_DEFAULTS[key]*(1000 if key=='cfd_mesh_size_m' else 1))
            control.wheelEvent=lambda event:event.ignore();control.setKeyboardTracking(False)
            control.setMinimumWidth(100);control.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
            control.valueChanged.connect(self.mark_dirty);self.fields[key]=control;form.addRow(title,control)
        for key,title,options in [
            ('cfd_backend','Flow solver',[('Navier–Stokes · SU2','su2'),('Creeping flow · Re≤1','stokes')]),
            ('cfd_domain_mode','Your imported model',[('Solid object · create surrounding fluid','external'),('Existing fluid volume / passage','fluid')]),
            ('cfd_flow_axis','Flow direction',[(f'+{a.upper()}',a) for a in 'xyz']),
            ('cfd_turbulence','Flow model',[('Laminar','none'),('Turbulent · Spalart–Allmaras','sa')])]:
            control=QComboBox();control.setMinimumWidth(100);control.setMinimumContentsLength(10)
            control.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            control.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
            for text,value in options:control.addItem(text,value)
            control.currentIndexChanged.connect(self.mark_dirty);self.selectors[key]=control;form.addRow(title,control)
        self.cfd_mesh_button=QPushButton('Build fluid mesh / preview setup')
        self.cfd_mesh_button.setToolTip('Use the current model. For external flow, subtract it from a new fluid enclosure; the original CAD is preserved.')
        self.cfd_mesh_button.clicked.connect(lambda:self.safe(self.mesh))
        self.cfd_report_button=QPushButton('Flow convergence / export report')
        self.cfd_report_button.setToolTip('Show the CFD convergence history and export paths in the main viewport.')
        self.cfd_report_button.clicked.connect(lambda:self.safe(lambda:self.change_view('cfd_report')))
        self.cfd_buttons=[self.cfd_mesh_button,self.cfd_report_button]
        for button in self.cfd_buttons:
            button.setMinimumWidth(100);button.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
            self.analysis_buttons.append(button);layout.addWidget(button)

    def cfd_select(self,project_id=None):
        self.save_before_project_change()
        pid=project_id or self.require_project();p=self.workspace.get_project(pid)['parameters']
        benchmark=not self.workspace.get_project(pid)['cad'] and any(j['kind'] in {'cfd','cfd_validation'} for j in self.workspace.list_jobs(pid))
        if not p['cfd_setup'] and not benchmark:
            existing=p['cfd_case']=='cad'
            self.workspace.set_parameters(pid,{'cfd_case':'cad','cfd_setup':1,
                'cfd_backend':p['cfd_backend'] if existing else 'su2',
                'cfd_domain_mode':p['cfd_domain_mode'] if existing else 'external',
                'cfd_mesh_size_m':p['cfd_mesh_size_m'] if existing else p['mesh_size_m'],
                'cfd_cad_scale':p['cfd_cad_scale'] if existing else p['cad_scale'],
                'cad_scale':p['cfd_cad_scale'] if existing else p['cad_scale']})
        self.workspace.select_study(pid,'cfd');self.project_revision=None;self.refresh()

    def cfd_run(self):
        self.save_parameters();self.workspace.start_job(self.require_project(),'cfd');self.workspace.show_project(self.project_id,'cfd_slice')

    def cfd_panel(self,study):
        flow=study=='cfd'
        for button in self.cfd_buttons:button.setVisible(flow)
        if not flow:return False
        backend=self.selectors['cfd_backend'].currentData()
        visible={'cad_scale','cfd_backend','cfd_domain_mode','cfd_mesh_size_m','cfd_density_kg_m3','cfd_viscosity_Pa_s'}
        visible|= {'cfd_speed_m_s','cfd_flow_axis','cfd_turbulence','cfd_iterations','cfd_residual_target','cfd_padding'} if backend=='su2' else {'cfd_pressure_drop_Pa'}
        if self.selectors['cfd_domain_mode'].currentData()!='external':visible.discard('cfd_padding')
        for key,control in (self.fields|self.selectors).items():self.properties_form.setRowVisible(control,bool(self.project_id) and key in visible)
        self.details_heading.setText('DETAILS OF FLUID DYNAMICS')
        self.study_note.setText('Use your imported model. Choose Solid object to create surrounding fluid, or Existing fluid volume for a passage. Check CAD scale, fluid properties and flow speed; build the mesh, then solve. External enclosure ports are selected automatically. Refine the mesh before trusting force predictions.' if backend=='su2' else 'Pressure-driven creeping flow on an imported fluid volume. This older solver requires Re≤1; use SU2 for ordinary velocity-driven flow.')
        self.study_note.setVisible(True);self.normal_load_note.hide();self.material_button.setEnabled(False)
        self.loads_button.setEnabled(False);self.run_study_button.setText('Run CFD study');self.run_study_button.setToolTip('Save this project’s flow setup and solve CFD in the background. Results stay in this main viewport.')
        self.region_button.setText('Inlet / outlet regions…');self.region_button.setToolTip('Select independent inlet/outlet faces. Empty selections use the automatic bounding-plane ports. Other internal-flow boundaries are no-slip walls.')
        for button in self.force_pick_buttons:
            button.setVisible(True);button.setText('Pick flow outlet');button.setToolTip('Pick outlet faces on the fluid mesh, then Save picked faces.')
        for button in self.findChildren(QPushButton)+self.findChildren(QToolButton):
            if button.property('pickRole')=='support':button.setText('Pick flow inlet');button.setToolTip('Pick inlet faces on the fluid mesh, then Save picked faces.')
        if self.project_id:
            p=self.workspace.get_project(self.project_id)['parameters']
            self.region_note.setText('Inlet: '+str(p['cfd_inlet_region'] or 'Automatic minimum face')+'\nOutlet: '+str(p['cfd_outlet_region'] or 'Automatic maximum face'))
        self.pick_note.setText('Build the fluid mesh before picking ports. For an automatic enclosure, blank inlet/outlet selections are normally sufficient.')
        return True
