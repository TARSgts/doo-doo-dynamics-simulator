import time

import pytest

from opensim.workspace import CAPABILITIES, Workspace


def wait_job(workspace, job_id):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        job = workspace.get_job(job_id)
        if job["status"] not in {"queued", "running"}:
            return job
        time.sleep(0.05)
    pytest.fail("Worker did not finish within 45 seconds")


@pytest.mark.parametrize("parameters", [{"poisson": 0.5}, {"load_N": 0}, {"mesh_size_m": -1},
                                       {"young_Pa": float("nan")}, {"cad_scale": True}, {"physics": "thermal"},
                                       {"element_order": 3}, {"element_order": True}, {"load_axis": "bad"}, {"load_kind": "pressure"}])
def test_parameter_validation_and_project_isolation(tmp_path, parameters):
    workspace = Workspace(tmp_path)
    project = workspace.create_project("Test")
    with pytest.raises(ValueError):
        workspace.set_parameters(project["id"], parameters)
    with pytest.raises(ValueError, match="Unknown project"):
        workspace.get_project("../../outside")
    assert workspace.get_project(project["id"])["revision"] == 0


def test_legacy_project_parameters_receive_defaults(tmp_path):
    workspace = Workspace(tmp_path)
    project = workspace.create_project("Legacy")
    with workspace.connect() as connection:
        connection.execute("UPDATE projects SET parameters=? WHERE id=?", ('{"load_N":1000}', project["id"]))
    assert workspace.get_project(project["id"])["parameters"]["element_order"] == 1
    workspace.set_parameters(project["id"], {"load_axis": "z"})
    assert workspace.get_project(project["id"])["parameters"]["load_axis"] == "z"


def test_capabilities_distinguish_planned_features():
    planned = {feature["name"] for feature in CAPABILITIES if not feature["enabled"]}
    assert {"Contact", "GPU solve"}.issubset(planned)
    assert "Thermal analysis" not in planned
    assert next(feature for feature in CAPABILITIES if feature["name"] == "Modal analysis")["enabled"]


def test_failed_import_job_retains_failure_and_logs(tmp_path):
    workspace = Workspace(tmp_path / "workspace")
    project = workspace.create_project("Bad CAD")
    cad = tmp_path / "invalid.step"
    cad.write_text("This is not a CAD solid")
    workspace.import_cad(project["id"], str(cad))
    job = workspace.start_job(project["id"], "mesh")
    failed = wait_job(workspace, job["id"])
    assert failed["status"] == "failed"
    assert failed["progress_stage"] == "failed"
    assert failed["error"]
    assert (workspace.job_directory(job["id"]) / "worker.log").is_file()
    assert workspace.current_artifact(project["id"]) is None


@pytest.mark.integration
def test_real_worker_jobs_and_stale_result_handling(tmp_path):
    from opensim.solver import find_solver

    try:
        find_solver()
    except FileNotFoundError:
        pytest.skip("CalculiX is unavailable")
    workspace = Workspace(tmp_path)
    project = workspace.create_project("Plate")
    job = workspace.start_job(project["id"], "example")
    with pytest.raises(ValueError, match="active job"):
        workspace.set_parameters(project["id"], {"load_N": 2000})
    assert wait_job(workspace, job["id"])["status"] == "completed"
    assert workspace.current_artifact(project["id"], "mesh").is_file()
    solve_job = workspace.start_job(project["id"], "solve")
    assert wait_job(workspace, solve_job["id"])["status"] == "completed"
    assert workspace.get_job(solve_job["id"])["progress_stage"] == "completed"
    result = workspace.get_results(project["id"])
    assert result["summary"]["reaction_N"][0] == pytest.approx(-1000, rel=1e-5)
    original = workspace.current_artifact(project["id"])
    workspace.set_parameters(project["id"], {"load_N": 2000})
    assert workspace.current_artifact(project["id"]) is None
    with pytest.raises(ValueError, match="current project inputs"):
        workspace.get_results(project["id"])
    assert original.is_file()
    workspace.show_project(project["id"], "mesh")
    assert workspace.ui_state()["view"] == "mesh"
