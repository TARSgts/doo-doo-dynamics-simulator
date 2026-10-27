import json
import time

import pytest

from opensim.job_progress import elapsed_label
from opensim.workspace import Workspace


@pytest.mark.parametrize("seconds,expected", [(-1, "00:00"), (0, "00:00"), (65.9, "01:05"), (3661, "1:01:01")])
def test_elapsed_format(seconds, expected):
    assert elapsed_label(seconds) == expected


def test_legacy_jobs_and_terminal_progress_are_preserved(tmp_path):
    workspace = Workspace(tmp_path)
    project = workspace.create_project("Progress test")
    now = time.time()
    with workspace.connect() as connection:
        connection.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)", ("legacy", project["id"], "solve", "running", 0, json.dumps({}), None, None, now, now))
    assert workspace.get_job("legacy")["progress_stage"] == "starting"
    workspace.set_job_progress("legacy", "solving")
    assert Workspace(tmp_path).get_job("legacy")["progress_stage"] == "solving"
    workspace.finish_job("legacy", result={"done": True})
    completed = workspace.get_job("legacy")
    workspace.set_job_progress("legacy", "reading")
    assert workspace.get_job("legacy")["progress_stage"] == "completed"
    assert workspace.get_job("legacy")["updated"] == completed["updated"]
    with pytest.raises(ValueError):
        workspace.set_job_progress("legacy", "50%")
    with pytest.raises(ValueError):
        workspace.set_job_progress("legacy", "completed")


@pytest.mark.integration
def test_real_static_and_modal_callbacks_report_actual_stages(tmp_path):
    from opensim.geometry import make_box
    from opensim.cli import solve
    from opensim.modal import solve_modal
    from opensim.solver import find_solver
    try:
        find_solver()
    except FileNotFoundError:
        pytest.skip("CalculiX unavailable")
    cad = tmp_path / "beam.step"
    make_box(cad, (0.1, 0.02, 0.02))
    expected = ["meshing", "preparing", "solving", "reading", "exporting"]
    stages = []
    solve(cad, tmp_path / "static", size=0.01, order=2, progress=stages.append)
    assert stages == expected
    stages.clear()
    solve_modal(cad, tmp_path / "modal", size=0.01, mode_count=2, progress=stages.append)
    assert stages == expected
