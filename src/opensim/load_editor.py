"""Edit each surface load without sharing its direction, region or magnitude."""
import copy
import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox,QComboBox,QDialog,QDoubleSpinBox,QFormLayout,QHBoxLayout,
    QLabel,QLineEdit,QListWidget,QMessageBox,QPushButton,QVBoxLayout)
from opensim.load_cases import validate_load_cases
from opensim.load_settings import LOAD_SURFACES


class LoadEditor(QDialog):
    def __init__(self,parent):
        super().__init__(parent);self.owner=parent;self.pid=parent.require_project()
        self.cases=copy.deepcopy(parent.workspace.get_project(self.pid)['parameters']['load_cases'])
        self.index=None;self.loading=False;self.setWindowTitle('Independent forces and pressures');self.resize(680,650)
        layout=QVBoxLayout(self);note=QLabel('Each entry acts simultaneously and has its own selected faces, vector and magnitude. A nonempty list replaces the single legacy load. Clear the list to restore that load.');note.setWordWrap(True);layout.addWidget(note)
        self.list=QListWidget();layout.addWidget(self.list)
        row=QHBoxLayout();layout.addLayout(row)
        for text,fn in [('Add force',lambda:self.add('force')),('Add pressure',lambda:self.add('pressure')),('Remove',self.remove)]:
            b=QPushButton(text);b.clicked.connect(fn);row.addWidget(b)
        form=QFormLayout();layout.addLayout(form)
        self.name=QLineEdit();form.addRow('Load name',self.name)
        self.enabled=QCheckBox('Enabled');form.addRow('',self.enabled)
        self.kind=QLabel();form.addRow('Application',self.kind)
        self.values=[]
        for text in ('X force (N)','Y force (N)','Z force (N)','Pressure (Pa)'):
            f=QDoubleSpinBox();f.setRange(-1e12,1e12);f.setDecimals(5);f.wheelEvent=lambda e:e.ignore();f.setToolTip(text+' for this load only. Positive pressure acts inward on each local surface.');self.values.append(f);form.addRow(text,f)
        self.surface=QComboBox();self.surface.addItems(LOAD_SURFACES);form.addRow('Fallback face',self.surface)
        self.region=QLineEdit();self.region.setPlaceholderText('Face IDs, for example: 3, 7');form.addRow('Selected face IDs',self.region)
        self.region_note=QLabel();self.region_note.setWordWrap(True);form.addRow(self.region_note)
        self.box_region={}
        pick=QPushButton('Pick faces for this load');pick.clicked.connect(self.pick);layout.addWidget(pick)
        pick.setToolTip('Hide this window, pick model faces, then Save picked faces. The selection belongs to this entry.')
        self.message=QLabel('Force: total vector in N spread over its surface. Pressure: Pa times area, inward for positive values.');self.message.setWordWrap(True);layout.addWidget(self.message)
        row=QHBoxLayout();layout.addLayout(row)
        save=QPushButton('Apply loads');preview=QPushButton('Apply and preview');close=QPushButton('Close')
        for b in (save,preview,close):row.addWidget(b)
        save.clicked.connect(lambda:self.save(False));preview.clicked.connect(lambda:self.save(True));close.clicked.connect(self.close)
        self.list.currentRowChanged.connect(self.select);self.form=form;self.rebuild()

    def store(self):
        if self.index is None:return
        c=self.cases[self.index];c['name']=self.name.text();c['enabled']=self.enabled.isChecked()
        c['surface']=self.surface.currentText()
        faces=[int(s.strip()) for s in self.region.text().split(',') if s.strip()]
        c['region']=({'faces':faces} if faces else self.box_region.copy())
        if c['kind']=='force':c['components_N']=[f.value() for f in self.values[:3]]
        else:c['pressure_Pa']=self.values[3].value()

    def rebuild(self,selected=0):
        self.list.blockSignals(True);self.list.clear()
        for i,c in enumerate(self.cases):self.list.addItem(c.get('name') or f'Load {i+1}')
        self.list.blockSignals(False);self.index=None
        if self.cases:self.list.setCurrentRow(min(selected,len(self.cases)-1))

    def select(self,index):
        if index<0:return
        try:self.store()
        except ValueError: QMessageBox.warning(self,'Load faces','Use comma-separated positive face IDs');return
        self.index=index;c=self.cases[index];self.name.setText(c.get('name',''));self.enabled.setChecked(c.get('enabled',True));self.kind.setText('Surface force vector' if c['kind']=='force' else 'Surface-normal pressure')
        for f,v in zip(self.values,[*c.get('components_N',[0,0,0]),c.get('pressure_Pa',0)]):f.setValue(v)
        for i,f in enumerate(self.values):self.form.setRowVisible(f,(i<3)==(c['kind']=='force'))
        self.surface.setCurrentText(c.get('surface','x-max'));region=c.get('region',{})
        self.box_region={k:v for k,v in region.items() if k!='faces'};self.region.setText(', '.join(map(str,region.get('faces',[]))))
        self.region_note.setText('Box filter retained (SI meters): '+json.dumps(self.box_region) if self.box_region else 'An empty selection uses this entry’s fallback face.')

    def add(self,kind):
        try:self.store()
        except ValueError:return
        self.cases.append({'name':f'{"Force" if kind=="force" else "Pressure"} {len(self.cases)+1}','kind':kind,'enabled':True,'surface':'x-max','region':{},**({'components_N':[0.,0.,-10.]} if kind=='force' else {'pressure_Pa':1000.})});self.rebuild(len(self.cases)-1)

    def remove(self):
        if self.index is not None:self.cases.pop(self.index);self.index=None;self.rebuild()

    def pick(self):
        if self.index is None:return
        try:
            self.store();self.owner.load_pick_callback=self.picked
            self.owner.load_pick_initial_faces=self.cases[self.index].get('region',{}).get('faces',[])
            self.hide();self.owner.begin_face_picking('load')
        except Exception as error:self.owner.load_pick_callback=None;self.show();QMessageBox.warning(self,'Pick load faces',str(error))

    def picked(self,region=None):
        if region and self.index is not None:self.cases[self.index]['region']=region;index=self.index;self.index=None;self.select(index)
        self.show();self.raise_()

    def save(self,preview):
        try:
            self.store();validate_load_cases(self.cases)
            if self.owner.project_id!=self.pid:raise ValueError('The selected project changed. Reopen the load editor for that project.')
            self.owner.workspace.set_parameters(self.pid,{'load_cases':self.cases});self.owner.project_revision=None;self.owner.refresh()
            self.message.setText(f'{len(self.cases)} independent loads saved. '+('Preview uses the actual mesh and integrated load directions.' if preview else 'Solve applies all enabled entries together.'))
            if preview:self.owner.mesh();self.hide()
        except Exception as error:QMessageBox.warning(self,'Independent loads',str(error))
