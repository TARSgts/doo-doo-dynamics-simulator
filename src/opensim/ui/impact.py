"""Desktop controls for the bounded elastic plate drop-test study."""
import shutil
from PySide6.QtWidgets import QDoubleSpinBox,QSpinBox,QPushButton,QToolButton,QSizePolicy,QFileDialog,QScrollArea
from opensim.impact_parameters import IMPACT_DEFAULTS,IMPACT_LIMITS
from opensim.hover_help import FIELD_HELP

# SI units per displayed unit.
IMPACT_UNITS={k:1e-3 for k in ('impact_length_m','impact_width_m','impact_thickness_m','impact_drop_height_m','impact_patch_m','impact_duration_s')}|{'impact_step_s':1e-6,'impact_young_Pa':1e9,'impact_contact_N_m':1000.}
IMPACT_FIELDS=[
 ('impact_length_m','Plate length (mm)',50,1000,2,'Length of the parametric rectangular plate; imported CAD is not used.'),
 ('impact_width_m','Plate width (mm)',50,1000,2,'Width of the plate. All four edges have ideal simple supports.'),
 ('impact_thickness_m','Thickness (mm)',1,20,3,'Uniform thickness. Must be at most 5% of the shorter plate side.'),
 ('impact_young_Pa',"Plate E (GPa)",.001,300,3,'Linear elastic Young’s modulus for this drop-test plate only.'),
 ('impact_poisson','Plate Poisson ratio',-.9,.49,3,'Elastic Poisson ratio for the thin-plate model.'),
 ('impact_density_kg_m3','Plate density (kg/m³)',50,20000,2,'Target density; determines the plate’s modal masses.'),
 ('impact_mass_kg','Drop weight (kg)',.05,2,3,'Mass of the centered blunt drop weight, modeled by one translating degree of freedom.'),
 ('impact_drop_height_m','Drop height (mm)',.1,50,3,'Low-height drop. Converted to speed at first touch; free fall before contact is not animated.'),
 ('impact_patch_m','Square patch (mm)',5,200,2,'Width of the centered uniform load patch. Must fit within a third of the shorter plate side.'),
 ('impact_contact_N_m','Contact spring (N/mm)',10,10000,2,'Illustrative compliant-interface stiffness. This is not a calibrated material or failure property.'),
 ('impact_damping_ratio','Plate damping ratio',0,.1,4,'Modal viscous damping ratio, e.g. 0.01 means 1% of critical damping.'),
 ('impact_duration_s','Duration (ms)',5,100,2,'Time simulated after first touch, including rebound. Gravity remains active.'),
 ('impact_step_s','Maximum step (µs)',.1,20,3,'Maximum integration step. A modal/contact frequency accuracy bound may reduce it further.'),
 ('impact_modes','Modes per direction',1,5,0,'Number of odd symmetric modes per direction. Repeat with more modes to check modal convergence.'),
]
FIELD_HELP.update({key:help for key,_,_,_,_,help in IMPACT_FIELDS})


class ImpactStudyMixin:
    def build_impact_properties(self,form,layout):
        for key,title,lo,hi,decimals,_ in IMPACT_FIELDS:
            control=QDoubleSpinBox() if decimals else QSpinBox()
            if decimals:control.setDecimals(decimals)
            control.setRange(lo,hi);control.setValue(IMPACT_DEFAULTS[key]/IMPACT_UNITS.get(key,1))
            control.setKeyboardTracking(False);control.wheelEvent=lambda event:event.ignore()
            control.setMinimumWidth(90);control.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
            control.valueChanged.connect(self.mark_dirty);self.fields[key]=control;form.addRow(title,control)
        self.impact_export=QPushButton('Export drop-test history…')
        self.impact_export.setToolTip('Save the completed current study’s time, displacement, force and energy history as CSV.')
        self.impact_export.clicked.connect(lambda:self.safe(self.export_impact_history));layout.addWidget(self.impact_export)
        self.analysis_buttons.append(self.impact_export)

    def show_impact(self):
        self.save_before_project_change()
        if not self.project_id:
            project=self.workspace.create_project('Elastic plate drop test');pid=project['id']
        else:pid=self.require_project()
        self.workspace.select_study(pid,'impact');self.workspace.show_project(pid,'impact');self.project_revision=None;self.refresh()

    def impact_run(self):
        self.save_parameters();self.workspace.start_job(self.require_project(),'impact');self.workspace.show_project(self.project_id,'impact')

    def export_impact_history(self):
        if self.dirty:raise ValueError('Apply settings and rerun the drop test before exporting edited inputs')
        result=self.workspace.get_impact_results(self.require_project())
        path,_=QFileDialog.getSaveFileName(self,'Export drop-test history','drop-test-history.csv','CSV files (*.csv)')
        if path:shutil.copyfile(result['artifacts']['history.csv'],path)

    def impact_panel(self,study):
        active=study=='impact';self.impact_export.setVisible(active)
        self.camera.setEnabled(not active);self.result_component.setEnabled(not active)
        for button in self.findChildren(QPushButton)+self.findChildren(QToolButton):
            if button.text().lower() in {'fit view','edges'}:button.setEnabled(not active)
        if not active:return False
        for button in self.cfd_buttons:button.hide()
        for button in self.findChildren(QPushButton)+self.findChildren(QToolButton):
            if button.property('pickRole'):button.setEnabled(False)
        context=self.project_id,study
        if context!=self.panel_context:self.findChild(QScrollArea,'PropertiesScroll').verticalScrollBar().setValue(0)
        self.panel_context=context
        for key,control in (self.fields|self.selectors).items():self.properties_form.setRowVisible(control,bool(self.project_id) and key in IMPACT_DEFAULTS)
        self.details_heading.setText('DETAILS OF ELASTIC DROP TEST');self.study_note.setText(IMPACT_LIMITS);self.study_note.show();self.normal_load_note.hide()
        self.material_button.setEnabled(False);self.loads_button.setEnabled(False);self.region_button.setEnabled(False)
        self.region_note.setText('Four simply supported edges · centered square contact patch · gravity downward. This study has its own plate and material settings.')
        self.pick_note.setText('Run the study, then use the time slider in the main viewport. Check energy balance and repeat with more modes and smaller time steps.')
        for button in self.force_pick_buttons:button.hide()
        for button in self.analysis_buttons:
            if button.text().lower() in {'generate mesh','generate fluid mesh'}:button.setEnabled(False)
        self.run_study_button.setText('Run elastic drop test');self.run_study_button.setToolTip('Integrate the bounded elastic plate/contact model and show playback, plots and exports here.')
        self.impact_export.setEnabled(bool(self.project_id) and not self.dirty and self.workspace.latest_result_job(self.project_id,['impact']) is not None)
        return True

    def impact_placeholder(self):
        return '<html><body style="background:#101923;color:#dce5f3;font:16px Segoe UI;padding:28px"><h1>Elastic plate drop test</h1><p>Set plate dimensions, a low drop height and the blunt drop-weight mass, then choose <b>Run elastic drop test</b>.</p><p>'+IMPACT_LIMITS+'</p><p>Playback, force/displacement plots, energy checks and CSV export appear in this main window after completion.</p></body></html>'
