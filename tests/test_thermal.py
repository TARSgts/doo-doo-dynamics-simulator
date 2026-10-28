import json
import time
from pathlib import Path
import numpy as np
import pytest

from opensim.geometry import make_box, import_and_mesh
from opensim.thermal import solve_thermal, write_thermal_deck, parse_thermal_dat, parse_heat_flux
from opensim.thermal_parameters import THERMAL_DEFAULTS, validate_thermal_parameters
from opensim.workspace import Workspace
from opensim.plots import load_plot_source, make_plot_data, available_plots, write_plot_csv


@pytest.fixture(autouse=True)
def require_solver_for_integration(request):
    if request.node.get_closest_marker('integration'):
        from opensim.solver import find_solver
        try:
            find_solver()
        except FileNotFoundError:
            pytest.skip('CalculiX unavailable')


@pytest.mark.parametrize('key,value', [('thermal_conductivity_W_mK',0),('thermal_conductivity_W_mK',float('nan')),
    ('thermal_fixed_temperature_K',-1),('thermal_source_temperature_K',float('inf')),
    ('thermal_power_W',True),('thermal_boundary_mode','convection'),('thermal_fixed_region',{'faces':[-1]})])
def test_invalid_thermal_inputs_are_rejected(key,value):
    with pytest.raises(ValueError): validate_thermal_parameters({key:value})


@pytest.mark.integration
def test_thermal_cli_solves_and_reports_invalid_inputs_without_traceback(tmp_path):
    import subprocess
    import sys
    cad=tmp_path/'bar.step';make_box(cad,(.1,.02,.02))
    command=[sys.executable,'-m','opensim.cli','thermal',str(cad),'--mesh-size','.01','--conductivity','10',
             '--boundary-mode','power','--power','.4']
    valid=subprocess.run(command+['--out',str(tmp_path/'valid')],capture_output=True,text=True,timeout=30)
    assert valid.returncode==0,valid.stderr
    result=json.loads(valid.stdout)
    assert result['maximum_temperature_K']==pytest.approx(303.15,abs=1e-4)
    invalid=subprocess.run(command+['--out',str(tmp_path/'invalid'),'--conductivity','-1'],capture_output=True,text=True,timeout=30)
    assert invalid.returncode==1 and 'conductivity must be positive' in invalid.stderr
    assert 'Traceback' not in invalid.stderr


@pytest.mark.parametrize('order',[1,2])
@pytest.mark.parametrize('mode',['temperature','power'])
@pytest.mark.integration
def test_real_thermal_bar_matches_fourier_solution_and_conserves_heat(tmp_path,order,mode):
    cad=tmp_path/'bar.step'
    make_box(cad,(.1,.02,.02))
    p={'thermal_conductivity_W_mK':10.,'thermal_boundary_mode':mode,'thermal_power_W':.4}
    out=tmp_path/'solve'
    result=solve_thermal(cad,out,size=.01,order=order,parameters=p)
    fields=np.load(out/'thermal.npz')
    x=fields['points'][:,0]
    delta=80. if mode=='temperature' else .4*.1/(10*.02*.02)
    expected=293.15+delta*x/.1
    np.testing.assert_allclose(fields['temperature_K'],expected,atol=8e-5,rtol=0)
    np.testing.assert_allclose(fields['heat_flux_W_m2'][:,0],-10*delta/.1,rtol=2e-5,atol=1e-5)
    np.testing.assert_allclose(fields['heat_flux_W_m2'][:,1:],0,atol=1e-5)
    assert result['maximum_temperature_K']==pytest.approx(293.15+delta,abs=8e-5)
    expected_heat=10*.02*.02*delta/.1
    assert result['fixed_boundary_heat_W']==pytest.approx(-expected_heat,rel=2e-6)
    assert result['relative_energy_imbalance']<1e-6
    assert (out/'results.vtk').read_text().find('SCALARS temperature_K')>0
    assert (out/'temperatures.csv').read_text().startswith('node_id,x_m')
    assert json.loads((out/'manifest.json').read_text())['units']['temperature']=='K'
    assert 'temperature_K' in (out/'results.html').read_text()


@pytest.mark.integration
def test_selected_thermal_faces_and_cad_scale_match_default_bar(tmp_path):
    cad=tmp_path/'bar-mm.step'
    make_box(cad,(100,20,20))
    mesh=import_and_mesh(cad,.01,.001,tmp_path/'check.msh',order=2)
    catalog=mesh.surface_catalog()
    fixed=next(f['id'] for f in catalog if abs(f['centroid_m'][0])<1e-9)
    source=next(f['id'] for f in catalog if abs(f['centroid_m'][0]-.1)<1e-9)
    p={'thermal_fixed_region':{'faces':[fixed]},'thermal_source_region':{'faces':[source]},'thermal_conductivity_W_mK':10}
    result=solve_thermal(cad,tmp_path/'selected',size=.01,scale=.001,order=2,parameters=p)
    assert result['fixed_boundary_heat_W']==pytest.approx(-3.2,rel=2e-6)
    with pytest.raises(ValueError,match='share nodes'):
        write_thermal_deck(mesh,tmp_path/'bad.inp',p|{'thermal_source_region':p['thermal_fixed_region']})


@pytest.mark.integration
def test_no_heat_and_extracted_heat_cases(tmp_path):
    cad=tmp_path/'bar.step';make_box(cad,(.1,.02,.02))
    for index,power in enumerate((0.,-.04)):
        out=tmp_path/f'power-{index}'
        result=solve_thermal(cad,out,size=.015,parameters={'thermal_boundary_mode':'power','thermal_power_W':power,'thermal_conductivity_W_mK':10})
        expected=293.15+power*.1/(10*.02*.02)
        assert result['minimum_temperature_K']==pytest.approx(min(293.15,expected),abs=1e-4)
        assert abs(result['energy_balance_W'])<1e-7


def test_parsers_reject_missing_nonfinite_or_duplicate_results(tmp_path):
    dat=tmp_path/'bad.dat';dat.write_text(' temperatures for set NALL\n1 NaN\n heat generation for set NALL\n1 0\n')
    with pytest.raises(ValueError,match='Nonfinite'):parse_thermal_dat(dat,1)
    dat.write_text(' temperatures for set NALL\n1 1\n1 1\n')
    with pytest.raises(ValueError,match='duplicate'):parse_thermal_dat(dat,1)
    dat.write_text(' temperatures for set NALL\n1 1\n')
    with pytest.raises(ValueError,match='Incomplete'):parse_thermal_dat(dat,2)
    with pytest.raises(ValueError,match='Incomplete'):parse_heat_flux(dat,2)


@pytest.mark.integration
def test_workspace_worker_thermal_results_plots_and_stale_revision(tmp_path):
    workspace=Workspace(tmp_path/'workspace')
    project=workspace.create_project('Thermal verification bar')
    cad=tmp_path/'bar.step';make_box(cad,(.1,.02,.02))
    workspace.import_cad(project['id'],str(cad))
    workspace.set_parameters(project['id'],{'mesh_size_m':.01,'element_order':2,'thermal_conductivity_W_mK':10})
    structural_before=workspace.get_project(project['id'])['parameters']['support_region']
    job=workspace.start_job(project['id'],'thermal')
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        finished=workspace.get_job(job['id'])
        if finished['status'] not in {'queued','running'}:break
        time.sleep(.05)
    assert finished['status']=='completed',finished['error']
    result=workspace.get_thermal_results(project['id'])
    assert Path(result['artifacts']['results.html']).is_file()
    workspace.show_project(project['id'],'thermal')
    assert workspace.ui_state()['study']=='thermal'
    assert workspace.current_artifact(project['id'],'thermal')==Path(result['artifacts']['results.html'])
    source=load_plot_source(workspace,project['id'])
    for key in available_plots(source):
        data=make_plot_data(source,key)
        write_plot_csv(tmp_path/(key+'.csv'),source,data)
    temperature=make_plot_data(source,'temperature-position')
    assert min(temperature.y)==pytest.approx(20,abs=1e-4)
    assert max(temperature.y)==pytest.approx(100,abs=1e-4)
    flux=make_plot_data(source,'heat-flux-position',component='x')
    np.testing.assert_allclose(flux.y,-8000,rtol=2e-5)
    assert workspace.get_project(project['id'])['parameters']['support_region']==structural_before
    workspace.set_parameters(project['id'],{'thermal_conductivity_W_mK':5})
    with pytest.raises(ValueError,match='current project'):workspace.get_thermal_results(project['id'])


def test_desktop_thermal_properties_units_and_picking_do_not_change_structural_regions(tmp_path,monkeypatch):
    pytest.importorskip('PySide6')
    import os
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    from opensim.desktop import SimulatorWindow
    app=QApplication.instance() or QApplication([])
    workspace=Workspace(tmp_path/'workspace')
    project=workspace.create_project('Independent thermal setup')
    workspace.set_parameters(project['id'],{'load_N':123,'support_region':{'faces':[9]}})
    workspace.select_study(project['id'],'thermal')
    window=SimulatorWindow(workspace)
    try:
        assert 'THERMAL' in window.details_heading.text()
        assert window.fields['load_N'].isHidden() and window.fields['young_Pa'].isHidden()
        assert not window.fields['thermal_conductivity_W_mK'].isHidden()
        assert window.fields['thermal_fixed_temperature_K'].value()==20
        assert window.run_study_button.text()=='Run thermal study'
        window.selectors['thermal_boundary_mode'].setCurrentIndex(window.selectors['thermal_boundary_mode'].findData('power'))
        assert not window.fields['thermal_power_W'].isHidden()
        assert window.fields['thermal_source_temperature_K'].isHidden()
        window.fields['thermal_fixed_temperature_K'].setValue(25)
        window.save_parameters()
        assert workspace.get_project(project['id'])['parameters']['thermal_fixed_temperature_K']==298.15
        view=('local-view','geometry')
        window.loaded_view=view
        session={'project_id':project['id'],'revision':workspace.get_project(project['id'])['revision'],'view':view,'study':'thermal'}
        window.face_pick_session=session
        window.commit_picked_faces(session,{'mode':'load','available':[1,2],'support':[1],'load':[2],
                                          'touched':{'support':True,'load':True}})
        p=workspace.get_project(project['id'])['parameters']
        assert p['thermal_fixed_region']=={'faces':[1]} and p['thermal_source_region']=={'faces':[2]}
        assert p['support_region']=={'faces':[9]} and p['load_region']=={}
        assert p['load_N']==123 and p['load_kind']=='face'
        calls=[]
        monkeypatch.setattr(window,'thermal',lambda:calls.append('thermal'))
        window.run_selected_study()
        assert calls==['thermal'] and workspace.list_jobs(project['id'])==[]
    finally:
        window.close();window.view.setPage(None);window.deleteLater();app.processEvents()
