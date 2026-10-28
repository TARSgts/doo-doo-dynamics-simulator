import json
import time

import numpy as np
import pytest

from opensim.cfd import cylinder_flow, cylinder_velocity, pipe_flow, flat_plate_flow, run_cfd
from opensim.cfd_parameters import CFD_DEFAULTS, validate_cfd_parameters
from opensim.cfd_validation import run_cfd_validation
from opensim.workspace import Workspace


def test_cylinder_exterior_field_refinement_and_surface_conservation():
    angle = np.linspace(.17, 2*np.pi+.17, 25)[:-1]
    r = 1.5
    points = r*np.column_stack((np.cos(angle), np.sin(angle)))
    exact = np.column_stack((1-np.cos(2*angle)/r**2, -np.sin(2*angle)/r**2))
    errors = []
    for n in (24, 48, 96):
        data, summary = cylinder_flow(n, speed=1, radius=1)
        assert summary['cp_max_error'] < 1e-8
        assert summary['normal_velocity_residual'] < 1e-10
        assert summary['relative_net_source'] < 1e-10
        assert abs(summary['CL']) < 1e-8
        assert abs(summary['CD_pressure']) < 1e-8
        errors.append(np.max(np.linalg.norm(cylinder_velocity(points, data, 1)-exact, axis=1)))
    assert errors[2] < errors[1] < errors[0]
    assert errors[2] < .01


def test_pipe_converges_to_poiseuille_and_scales_with_pressure_and_viscosity():
    errors = []
    for n in (12, 24, 48):
        data, s = pipe_flow(n)
        errors.append(s['flow_relative_error'])
        assert np.all(data['velocity_m_s'] > 0)
        assert np.all(np.diff(data['velocity_m_s']) < 0)
        assert s['linear_residual'] < 1e-9
        assert s['wall_shear_Pa'] == pytest.approx(.1*.005/(2*1))
    np.testing.assert_allclose(np.array(errors[:-1])/errors[1:], 4, rtol=1e-8)
    assert errors[-1] < .0005
    base = pipe_flow()[1]['flow_rate_m3_s']
    assert pipe_flow(pressure_drop=.2)[1]['flow_rate_m3_s'] == pytest.approx(2*base)
    assert pipe_flow(viscosity=2*1.81e-5)[1]['flow_rate_m3_s'] == pytest.approx(base/2)
    with pytest.raises(ValueError, match='Reynolds'):
        pipe_flow(pressure_drop=1e5)


def test_flat_plate_sweep_sign_symmetry_slope_and_dimensional_lift():
    data, s = flat_plate_flow(48, speed=15, chord=.2, density=1.1, alpha_min=-8, alpha_max=8, alpha_step=1)
    alpha = data['alpha_deg']
    np.testing.assert_allclose(data['CL'], 2*np.pi*np.sin(np.deg2rad(alpha)), atol=1e-9)
    np.testing.assert_allclose(data['CL'], -data['CL'][::-1], atol=1e-12)
    assert data['CL'][np.where(alpha==0)[0][0]] == 0
    assert s['lift_slope_per_rad'] == pytest.approx(2*np.pi, rel=.005)
    np.testing.assert_allclose(data['lift_per_span_N_m'], .5*1.1*15**2*.2*data['CL'])
    assert s['normal_velocity_residual'] < 1e-9
    odd, _ = flat_plate_flow(alpha_min=-3, alpha_max=4, alpha_step=2)
    assert odd['alpha_deg'][-1] == 4


@pytest.mark.parametrize('change', [
    {'cfd_case':'turbulent'}, {'cfd_resolution':3}, {'cfd_resolution':12.5}, {'cfd_resolution':True},
    {'cfd_viscosity_Pa_s':0}, {'cfd_density_kg_m3':float('nan')}, {'cfd_speed_m_s':200},
    {'cfd_alpha_min_deg':-11}, {'cfd_alpha_max_deg':11}, {'cfd_alpha_step_deg':0},
    {'cfd_alpha_step_deg':.0001}, {'cfd_alpha_min_deg':5, 'cfd_alpha_max_deg':-5},
])
def test_invalid_settings_rejected(change):
    with pytest.raises(ValueError): validate_cfd_parameters(CFD_DEFAULTS | change)


def test_all_three_verification_reports_and_exports(tmp_path):
    report = run_cfd_validation(tmp_path/'validation')
    assert report['result'] == 'PASS'
    assert all(report['checks'].values())
    assert len(report['rows']) == 9
    for case in ('cylinder', 'pipe', 'flat_plate'):
        folder = tmp_path/'validation'/case
        assert (folder/'report.html').is_file()
        assert (folder/'plot.png').stat().st_size > 1000
        data = np.load(folder/'flow.npz')
        assert all(np.isfinite(data[key]).all() for key in data.files)
        assert len((folder/'data.csv').read_text().splitlines()) > 2
        saved = json.loads((folder/'manifest.json').read_text())
        assert saved['summary']['case'] == case
    with pytest.raises(FileExistsError): run_cfd_validation(tmp_path/'validation')


def finish(workspace, job):
    deadline = time.monotonic()+45
    while time.monotonic()<deadline:
        result = workspace.get_job(job['id'])
        if result['status'] not in {'queued','running'}: break
        time.sleep(.05)
    assert result['status'] == 'completed', result['error']
    return result


def test_worker_cad_independence_stale_results_and_saved_inputs(tmp_path):
    workspace = Workspace(tmp_path)
    original = workspace.create_project('Existing CAD project')
    workspace.show_project(original['id'])
    sample = workspace.create_project('CFD flat plate')
    workspace.set_parameters(sample['id'], {'cfd_case':'flat_plate','cfd_alpha_step_deg':1})
    finish(workspace, workspace.start_job(sample['id'], 'cfd'))
    result = workspace.get_cfd_results(sample['id'])
    assert result['summary']['angle_count'] == 17
    assert len(result['artifacts']) == 5
    assert workspace.get_project(sample['id'])['cad'] is None
    assert workspace.get_project(original['id']) == original
    assert workspace.ui_state()['project_id'] == original['id']
    workspace.set_parameters(sample['id'], {'cfd_alpha_max_deg':6})
    with pytest.raises(ValueError, match='No completed CFD'): workspace.get_cfd_results(sample['id'])
    finish(workspace, workspace.start_job(sample['id'], 'cfd_validation'))
    assert workspace.get_cfd_results(sample['id'])['summary']['result'] == 'PASS'


def test_benchmark_results_do_not_depend_on_structural_or_thermal_inputs(tmp_path):
    summary = run_cfd(tmp_path/'pipe', {'cfd_case':'pipe', 'young_Pa':999., 'thermal_power_W':123.})
    assert summary['flow_rate_m3_s'] == pytest.approx(pipe_flow()[1]['flow_rate_m3_s'])
