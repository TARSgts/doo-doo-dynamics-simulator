import json
import time
import pytest


def test_drop_study_stays_in_main_window_and_preserves_other_studies(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QApplication,QFileDialog,QDialog
    from opensim.desktop import SimulatorWindow
    from opensim.workspace import Workspace
    app=QApplication.instance() or QApplication([]);w=Workspace(tmp_path/'workspace');pid=w.create_project('Drop study')['id'];w.show_project(pid)
    original=w.get_project(pid)['parameters'];window=SimulatorWindow(w);window.show()
    def js(code):
        result=[];window.view.page().runJavaScript(code,lambda value:result.append(value));deadline=time.monotonic()+10
        while not result and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
        assert result;return result[0]
    try:
        w.select_study(pid,'cfd');window.refresh()
        assert any(not button.isHidden() for button in window.cfd_buttons)
        window.show_impact()
        assert all(button.isHidden() for button in window.cfd_buttons)
        assert w.ui_state()['study']=='impact' and len(w.list_projects())==1
        assert not window.fields['impact_mass_kg'].isHidden() and window.fields['load_N'].isHidden()
        assert window.fields['impact_length_m'].value()==200.
        assert window.fields['impact_young_Pa'].value()==210.
        assert not window.region_button.isEnabled() and not window.camera.isEnabled()
        assert not any(d.isVisible() for d in window.findChildren(QDialog))
        window.fields['impact_duration_s'].setValue(5.)
        window.fields['impact_modes'].setValue(1)
        window.impact_run();deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            job=w.list_jobs(pid)[0];app.processEvents()
            if job['status'] not in {'queued','running'}:break
            time.sleep(.05)
        assert job['status']=='completed',job.get('error')
        window.refresh();deadline=time.monotonic()+15;state=None
        while time.monotonic()<deadline:
            app.processEvents();value=js("typeof impactPlaybackState==='undefined'?'':JSON.stringify(impactPlaybackState)")
            if value:state=json.loads(value);break
            time.sleep(.03)
        assert state and state['frames']>2
        value=js("time.value=Math.floor(Number(time.max)/2);time.oninput();JSON.stringify(impactPlaybackState)")
        scrubbed=json.loads(value);assert scrubbed['frame']>0 and scrubbed['time_s']>0
        js('play.click()');assert json.loads(js('JSON.stringify(impactPlaybackState)'))['playing']
        js('play.click()')
        saved=w.get_project(pid)['parameters'];assert saved['impact_duration_s']==.005
        for key in ('load_N','young_Pa','density_kg_m3','thermal_conductivity_W_mK','cfd_speed_m_s'):
            assert saved[key]==original[key]
        target=tmp_path/'export.csv';monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args:(str(target),''))
        window.export_impact_history();assert target.read_text().startswith('time_s,drop_weight_displacement_m')
        w.select_study(pid,'static');window.refresh();assert not window.fields['load_N'].isHidden() and window.fields['impact_mass_kg'].isHidden()
        assert window.camera.isEnabled()
    finally:
        window.close();window.view.setPage(None);window.deleteLater();app.processEvents()
