import json
from pathlib import Path
import sys
import threading
import time

import pytest

from opensim import solver
from opensim.workspace import CANCEL_MESSAGE, Workspace


@pytest.fixture(autouse=True)
def reset_solver_cancellation():
    solver._cancelled.clear()
    yield
    solver._cancelled.clear()


def insert_job(workspace, project_id, job_id, status="running", kind="solve", payload=None):
    now = time.time()
    with workspace.connect() as connection:
        connection.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)",
                           (job_id, project_id, kind, status, 0, json.dumps(payload or {}), None, None, now, now))


def wait_for(condition, timeout=20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.1)
    return False


def test_cancel_marks_job_stopped_unlocks_inputs_and_ignores_late_worker_reports(tmp_path):
    workspace = Workspace(tmp_path)
    project = workspace.create_project("Cancel test")
    insert_job(workspace, project["id"], "slow")
    with pytest.raises(ValueError, match="active job"):
        workspace.set_parameters(project["id"], {"load_N": 5})
    assert workspace.active_job(project["id"])["id"] == "slow"
    cancelled = workspace.cancel_job("slow")
    assert cancelled["status"] == "cancelled"
    assert cancelled["progress_stage"] == "cancelled"
    assert cancelled["error"] == CANCEL_MESSAGE
    assert workspace.active_job(project["id"]) is None
    workspace.set_parameters(project["id"], {"load_N": 5})
    workspace.finish_job("slow", result={"nodes": 1})
    workspace.finish_job("slow", error="late failure")
    assert workspace.get_job("slow")["status"] == "cancelled"
    assert workspace.get_job("slow")["result"] is None
    workspace.set_job_progress("slow", "solving")
    assert workspace.get_job("slow")["progress_stage"] == "cancelled"
    with pytest.raises(ValueError):
        workspace.set_job_progress("slow", "cancelled")
    with pytest.raises(ValueError, match="already finished"):
        workspace.cancel_job("slow")
    with pytest.raises(ValueError, match="Unknown job"):
        workspace.cancel_job("missing")
    with pytest.raises(ValueError):
        workspace.get_results(project["id"])


def test_orphaned_running_job_can_be_cleared(tmp_path):
    """A worker that died with the computer still leaves a 'running' row; stopping it frees the project."""
    workspace = Workspace(tmp_path)
    project = workspace.create_project("Orphan")
    insert_job(workspace, project["id"], "orphan", kind="mesh")
    workspace.cancel_job("orphan")
    insert_job(workspace, project["id"], "next", status="queued")
    assert workspace.active_job(project["id"])["id"] == "next"


def test_worker_does_not_revive_a_job_stopped_before_it_started(tmp_path):
    from opensim.worker import execute
    workspace = Workspace(tmp_path)
    project = workspace.create_project("Stopped early")
    insert_job(workspace, project["id"], "early", status="queued", payload={"cad": None, "parameters": {}})
    workspace.cancel_job("early")
    execute(workspace, "early")
    assert workspace.get_job("early")["status"] == "cancelled"


def test_cancelled_example_cannot_replace_newly_imported_model(tmp_path, monkeypatch):
    from opensim import worker
    from opensim.workspace import DEFAULT_PARAMETERS
    workspace = Workspace(tmp_path / "workspace")
    project = workspace.create_project("Cancel during geometry creation")
    replacement = tmp_path / "replacement.step"
    replacement.write_text("new user geometry")
    insert_job(workspace, project["id"], "example-race", status="queued", kind="example",
               payload={"cad": None, "parameters": DEFAULT_PARAMETERS, "example": "axial_bar"})
    def cancelled_geometry(path, dimensions):
        path.write_text("old generated geometry")
        workspace.cancel_job("example-race")
        workspace.import_cad(project["id"], replacement)
    monkeypatch.setattr("opensim.execution.examples.make_box", cancelled_geometry)
    monkeypatch.setattr(worker, "watch_for_cancel", lambda workspace, job_id, stop: stop.wait())
    workspace.job_directory("example-race").mkdir(parents=True, exist_ok=True)
    worker.execute(workspace, "example-race")
    saved = workspace.get_project(project["id"])
    assert Path(saved["cad"]).read_text() == "new user geometry"
    assert workspace.get_job("example-race")["status"] == "cancelled"


def fake_solver(directory: Path):
    """run_solver calls `<exe> -i model`; Python treats that as 'run model, then read stdin', which is closed."""
    (directory / "model").write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
    return Path(sys.executable)


def test_watchdog_ends_running_solver_and_exits_worker(tmp_path):
    from opensim.worker import watch_for_cancel
    workspace = Workspace(tmp_path)
    project = workspace.create_project("Watchdog")
    insert_job(workspace, project["id"], "watched")
    executable = fake_solver(tmp_path)
    outcome = {}

    def run():
        started = time.time()
        try:
            solver.run_solver(executable, tmp_path, timeout=60)
        except Exception as error:
            outcome["error"] = error
        outcome["seconds"] = time.time() - started

    solve_thread = threading.Thread(target=run)
    solve_thread.start()
    assert wait_for(lambda: solver._active_processes)
    process = next(iter(solver._active_processes))
    exits = []
    stop = threading.Event()
    watcher = threading.Thread(target=watch_for_cancel, args=(workspace, "watched", stop, exits.append))
    watcher.start()
    time.sleep(0.5)
    assert not exits and process.poll() is None
    workspace.cancel_job("watched")
    watcher.join(5)
    solve_thread.join(10)
    assert exits == [3]
    assert isinstance(outcome["error"], solver.SolverCancelled)
    assert outcome["seconds"] < 10
    assert process.poll() is not None
    assert not solver._active_processes
    with pytest.raises(solver.SolverCancelled):
        solver.run_solver(executable, tmp_path)


def test_watchdog_leaves_healthy_jobs_alone(tmp_path):
    from opensim.worker import watch_for_cancel
    workspace = Workspace(tmp_path)
    project = workspace.create_project("Healthy")
    insert_job(workspace, project["id"], "healthy")
    exits, stop = [], threading.Event()
    watcher = threading.Thread(target=watch_for_cancel, args=(workspace, "healthy", stop, exits.append))
    watcher.start()
    time.sleep(0.8)
    workspace.finish_job("healthy", result={"nodes": 1})
    time.sleep(0.5)
    stop.set()
    watcher.join(2)
    assert not watcher.is_alive() and not exits


def test_stopping_a_real_long_mesh_ends_the_worker_and_frees_the_project(tmp_path):
    from opensim.geometry import make_box
    workspace = Workspace(tmp_path / "workspace")
    project = workspace.create_project("Long mesh")
    cad = tmp_path / "block.step"
    make_box(cad, (1.0, 1.0, 1.0))
    workspace.import_cad(project["id"], str(cad))
    workspace.set_parameters(project["id"], {"mesh_size_m": 0.006, "element_order": 2})
    job = workspace.start_job(project["id"], "mesh")
    assert wait_for(lambda: workspace.get_job(job["id"])["progress_stage"] == "meshing")
    time.sleep(1)
    assert workspace.get_job(job["id"])["status"] == "running"
    stopped_at = time.time()
    workspace.cancel_job(job["id"])
    log = workspace.job_directory(job["id"]) / "worker.log"
    assert wait_for(lambda: "Stop requested" in log.read_text(encoding="utf-8", errors="replace"), 10)
    assert time.time() - stopped_at < 10
    time.sleep(1)
    assert workspace.get_job(job["id"])["status"] == "cancelled"
    workspace.set_parameters(project["id"], {"mesh_size_m": 0.5, "element_order": 1})
    quick = workspace.start_job(project["id"], "mesh")
    assert wait_for(lambda: workspace.get_job(quick["id"])["status"] == "completed", 60)


@pytest.mark.integration
def test_stopping_a_real_calculix_solve_ends_the_solver(tmp_path):
    from opensim.geometry import make_box
    try:
        solver.find_solver()
    except FileNotFoundError:
        pytest.skip("CalculiX unavailable")
    workspace = Workspace(tmp_path / "workspace")
    project = workspace.create_project("Long solve")
    cad = tmp_path / "bar.step"
    make_box(cad, (0.2, 0.05, 0.05))
    workspace.import_cad(project["id"], str(cad))
    workspace.set_parameters(project["id"], {"mesh_size_m": 0.0035, "element_order": 2})
    job = workspace.start_job(project["id"], "solve")
    assert wait_for(lambda: workspace.get_job(job["id"])["progress_stage"] == "solving", 120)
    time.sleep(1)
    if workspace.get_job(job["id"])["status"] != "running":
        pytest.skip("Solve finished before it could be stopped on this machine")
    workspace.cancel_job(job["id"])
    log = workspace.job_directory(job["id"]) / "worker.log"
    assert wait_for(lambda: "ended 1 solver process" in log.read_text(encoding="utf-8", errors="replace"), 10)
    assert workspace.get_job(job["id"])["status"] == "cancelled"
