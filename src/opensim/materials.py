"""Illustrative room-temperature isotropic presets, editable before application."""
MATERIALS = {
    'Steel (generic)': {'young_Pa':210e9,'poisson':.3,'density_kg_m3':7850.,'thermal_conductivity_W_mK':45.},
    'Aluminum (generic)': {'young_Pa':69e9,'poisson':.33,'density_kg_m3':2700.,'thermal_conductivity_W_mK':167.},
    'ABS (solid, isotropic approximation)': {'young_Pa':2.3e9,'poisson':.35,'density_kg_m3':1040.,'thermal_conductivity_W_mK':.18},
}


def material_name(parameters):
    return next((name for name,p in MATERIALS.items() if all(abs(parameters[k]-v)<=max(1e-10,abs(v)*1e-8) for k,v in p.items())), 'Custom')


def edit_material(parent):
    from PySide6.QtWidgets import QComboBox,QDialog,QDialogButtonBox,QDoubleSpinBox,QFormLayout,QLabel,QVBoxLayout
    parent.save_parameters()
    p=parent.workspace.get_project(parent.require_project())['parameters']
    dialog=QDialog(parent);dialog.setWindowTitle('Material properties');dialog.resize(480,420)
    layout=QVBoxLayout(dialog);form=QFormLayout();combo=QComboBox()
    combo.addItems(['Custom',*MATERIALS]);combo.setCurrentText(material_name(p))
    form.addRow('Material preset',combo);fields={}
    for key,title,factor,lo,hi,decimals in [('young_Pa',"Young’s modulus (GPa)",1e-9,.000001,1e6,6),
        ('poisson','Poisson ratio',1,-.99,.4999,4),('density_kg_m3','Density (kg/m³)',1,.000001,1e9,4),
        ('thermal_conductivity_W_mK','Conductivity (W/m·K)',1,.000001,1e9,6)]:
        field=QDoubleSpinBox();field.setDecimals(decimals);field.setRange(lo,hi);field.setValue(p[key]*factor)
        field.wheelEvent=lambda event:event.ignore();field.setToolTip(title+'; editable before applying.')
        fields[key]=(field,factor);form.addRow(title,field)
    layout.addLayout(form)
    note=QLabel('Presets are approximate room-temperature values, not certified alloy or filament data. One material applies to the whole solid. Printing direction, infill, plasticity and failure strength are not modeled. Changing density changes modal frequencies.');note.setWordWrap(True);layout.addWidget(note)
    def select(name):
        if name in MATERIALS:
            for key,(field,factor) in fields.items():field.setValue(MATERIALS[name][key]*factor)
    combo.currentTextChanged.connect(select)
    buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
    if dialog.exec()==QDialog.DialogCode.Accepted:
        values={k:field.value()/factor for k,(field,factor) in fields.items()}
        values['material_name']=material_name(values)
        parent.workspace.set_parameters(parent.project_id,values);parent.project_revision=None;parent.refresh()
