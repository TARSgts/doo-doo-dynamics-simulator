import os
import time
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication, QEvent
from opensim.cfd_desktop import CFDDialog
from opensim.workspace import Workspace


def test_cfd_desktop_units_model_fields_worker_and_saved_history(tmp_path,monkeypatch):
    app = QApplication.instance() or QApplication([])
    workspace = Workspace(tmp_path)
    original = workspace.create_project('Existing model')
    workspace.show_project(original['id'])
    dialog = CFDDialog(workspace)
    try:
        assert dialog.fields['cfd_radius_m'].value() == 5
        dialog.case.setCurrentIndex(dialog.case.findData('flat_plate'))
        assert not dialog.fields['cfd_alpha_step_deg'].isHidden()
        assert dialog.fields['cfd_pressure_drop_Pa'].isHidden()
        dialog.fields['cfd_chord_m'].setValue(200)
        dialog.fields['cfd_alpha_step_deg'].setValue(1)
        assert dialog.inputs()['cfd_chord_m'] == .2
        dialog.run()
        assert dialog.job_id
        assert not dialog.case.isEnabled()
        deadline = time.monotonic()+30
        while dialog.job_id and time.monotonic()<deadline:
            app.processEvents(); dialog.poll(); time.sleep(.02)
        assert dialog.job_id is None
        assert dialog.status.text() == 'Completed'
        assert (dialog.result_folder/'report.html').is_file()
        assert dialog.export_button.isEnabled()
        pid = dialog.project_id
        dialog.fields['cfd_alpha_max_deg'].setValue(6)
        assert 'Inputs changed' in dialog.status.text()
        assert not dialog.export_button.isEnabled()
        dialog.new_study()
        assert dialog.project_id is None and dialog.result_folder is None
        dialog.history.setCurrentIndex(dialog.history.findData(pid))
        assert dialog.project_id == pid
        assert dialog.inputs()['cfd_chord_m'] == .2
        assert dialog.fields['cfd_alpha_max_deg'].value() == 8
        from opensim.geometry import make_box
        from PySide6.QtWidgets import QFileDialog
        cad=tmp_path/'fluid.step';make_box(cad,(100,10,10))
        monkeypatch.setattr(QFileDialog,'getOpenFileName',lambda *args,**kwargs:(str(cad),'CAD'))
        dialog.import_fluid()
        assert dialog.case.currentData()=='cad'
        assert dialog.fields['cfd_resolution'].isHidden()
        dialog.inspect_mesh()
        deadline=time.monotonic()+30
        while dialog.job_id and time.monotonic()<deadline:
            app.processEvents();dialog.poll();time.sleep(.02)
        assert dialog.job_id is None
        assert dialog.mesh_signature is not None
        assert 'CAD face IDs' in dialog.cad_note.text()
        job=workspace.list_jobs(pid)[0]
        assert job['kind']=='cfd_mesh' and job['result']['analysis']=='cfdcad'
        assert workspace.ui_state()['project_id']==original['id']
        assert workspace.get_project(original['id'])==original
    finally:
        dialog.timer.stop(); dialog.close(); dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
