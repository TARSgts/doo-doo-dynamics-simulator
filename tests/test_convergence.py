import json
import time

import pytest

from opensim.convergence import analyse, response_value, run_convergence, validate_convergence_parameters, write_report
from opensim.workspace import Workspace


def levels_from(values, start_elements=1000, ratio=2.0):
    return [{"level": index + 1, "mesh_size_m": 0.01 / ratio ** index, "nodes": 10, "viewer": f"mesh-{index + 1}/results.html",
             "tetrahedra": int(start_elements * ratio ** (3 * index)),
             "values": {"displacement": value, "response": value, "stress": value}} for index, value in enumerate(values)]


def test_richardson_recovers_exact_value_for_second_order_error():
    # f(h) = 1 + 0.5 h² sampled at h = 1, 1/2, 1/4 (element count ×8 per halving).
    values = [1 + 0.5 * h ** 2 for h in (1, 0.5, 0.25)]
    entry = analyse(levels_from(values), tolerance=0.1)["displacement"]  # last change is 9.1%
    assert entry["observed_order"] == pytest.approx(2, rel=1e-9)
    assert entry["extrapolated"] == pytest.approx(1, rel=1e-12)
    assert entry["gci_fine"] == pytest.approx(1.25 * abs(values[2] - values[1]) / values[2] / 3, rel=1e-9)
    assert entry["verdict"] == "converged"


@pytest.mark.parametrize("values,verdict", [
    ([1.0, 1.2, 1.3, 1.35], "converging"),
    ([1.0, 1.05, 1.15, 1.4], "diverging"),        # changes grow: e.g. stress at a singular corner
    ([1.0, 1.001, 1.0012], "converged"),
    ([1.0, 1.5], "not enough meshes"),
    ([1.0], "not enough meshes"),
])
def test_verdicts(values, verdict):
    entry = analyse(levels_from(values), tolerance=0.02)["displacement"]
    assert entry["verdict"] == verdict
    if verdict == "diverging":
        assert entry["extrapolated"] is None


def test_oscillating_values_get_no_extrapolation():
    entry = analyse(levels_from([1.0, 1.1, 1.05]), tolerance=0.01)["stress"]
    assert entry["extrapolated"] is None and entry["observed_order"] is None


def test_unequal_mesh_ratios_use_generalized_richardson():
    # Effective sizes 1, 1/2, 1/3: a geometric-mean ratio gives a wrong order/limit.
    levels = levels_from([1.5, 1.125, 1 + 0.5 / 9])
    for level, count in zip(levels, [1000, 8000, 27000]):
        level["tetrahedra"] = count
    entry = analyse(levels, 0.1)["displacement"]
    assert entry["observed_order"] == pytest.approx(2)
    assert entry["extrapolated"] == pytest.approx(1)


def test_same_element_counts_do_not_claim_convergence():
    levels = levels_from([1, 1, 1])
    levels[-1]["tetrahedra"] = levels[-2]["tetrahedra"]
    entry = analyse(levels, 0.02)["displacement"]
    assert entry["verdict"] == "not enough refinement"
    assert entry["extrapolated"] is None
    assert analyse(levels[:2], 0.02)["displacement"]["verdict"] == "not enough meshes"


def test_actual_element_limit_stops_before_starting_solver(tmp_path, monkeypatch):
    import numpy as np
    from opensim import cli
    from opensim.geometry import Mesh, MeshElementLimitExceeded
    cad = tmp_path / "fake.step"
    cad.write_text("test fixture")
    mesh = Mesh(np.zeros((4, 3)), np.tile(np.arange(4), (1001, 1)))
    monkeypatch.setattr(cli, "find_solver", lambda explicit: cad)
    monkeypatch.setattr(cli, "import_and_mesh", lambda *args, **kwargs: mesh)
    def should_not_run(*args, **kwargs):
        pytest.fail("Oversized mesh must not reach the solver")
    monkeypatch.setattr(cli, "run_solver", should_not_run)
    monkeypatch.setattr(cli, "write_deck", should_not_run)
    with pytest.raises(MeshElementLimitExceeded, match="Actual mesh has 1,001"):
        cli.solve(cad, tmp_path / "run", max_elements=1000)


def test_response_follows_force_direction_and_normal_loads():
    traction = {"load_axis": "z", "load_N": -10, "load_kind": "traction", "loaded_surface_mean_displacement_m": [0, 0, -2e-4]}
    assert response_value(traction) == pytest.approx(2e-4)
    assert response_value({"load_axis": "y", "load_N": 5, "load_kind": "point", "tip_mean_displacement_m": [0, 3e-5, 0]}) == pytest.approx(3e-5)
    assert response_value({"load_axis": "normal-out", "loaded_surface_mean_normal_displacement_m": 1e-6}) == 1e-6


@pytest.mark.parametrize("arguments", [(2, 1.4, 2, "displacement"), (7, 1.4, 2, "displacement"), (4, 1.1, 2, "displacement"),
                                       (4, 1.4, 0, "displacement"), (4, 1.4, 2, "temperature"), (4.5, 1.4, 2, "stress")])
def test_parameter_validation(arguments):
    with pytest.raises(ValueError):
        validate_convergence_parameters(*arguments)


def test_workspace_stores_convergence_settings_and_rejects_bad_ones(tmp_path):
    workspace = Workspace(tmp_path)
    project = workspace.create_project("Convergence settings")
    updated = workspace.set_parameters(project["id"], {"convergence_levels": 5.0, "convergence_ratio": 1.5,
                                                       "convergence_tolerance_percent": 1, "convergence_target": "stress"})
    assert updated["parameters"]["convergence_levels"] == 5 and isinstance(updated["parameters"]["convergence_levels"], int)
    with pytest.raises(ValueError):
        workspace.set_parameters(project["id"], {"convergence_target": "vibes"})
    with pytest.raises(ValueError, match="No completed convergence"):
        workspace.get_convergence_results(project["id"])
    with pytest.raises(ValueError, match="Import CAD"):
        workspace.start_job(project["id"], "convergence")


def test_report_renders_every_verdict_and_escapes_text(tmp_path):
    levels = levels_from([1e-4, 1.2e-4, 1.3e-4, 1.36e-4])  # still changing 4.4%: not converged
    result = {"target": "displacement", "tolerance_percent": 2, "refinement_ratio": 2, "requested_levels": 4,
              "element_type": "C3D4", "levels": levels, "quantities": analyse(levels, 0.02), "stop_reason": "<b>done</b>"}
    write_report(tmp_path / "report.html", result)
    text = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "&lt;b&gt;done&lt;/b&gt;" in text and "<b>done</b>" not in text
    assert text.count("<svg") == 3 and "mesh-4/results.html" in text and "Quadratic C3D10" in text and "Converging" in text


@pytest.mark.integration
def test_real_beam_study_converges_to_beam_theory_and_stops_early(tmp_path):
    from opensim.geometry import make_box
    from opensim.solver import find_solver
    try:
        find_solver()
    except FileNotFoundError:
        pytest.skip("CalculiX unavailable")
    make_box(tmp_path / "beam.step", (0.3, 0.02, 0.02))
    stages = []
    result = run_convergence(tmp_path / "beam.step", tmp_path / "study", size=0.01, young=210e9, poisson=0.3, load=-50, order=2,
                             load_axis="z", load_kind="traction", load_surface="x-max", levels=5, ratio=1.4,
                             tolerance_percent=1, target="response", progress=stages.append)
    assert len(result["levels"]) == 3 and "within the 1% target" in result["stop_reason"]  # stopped early
    assert result["verdict"] == "converged"
    counts = [level["tetrahedra"] for level in result["levels"]]
    assert counts == sorted(counts) and counts[-1] > 3 * counts[0]
    euler_bernoulli = 50 * 0.3 ** 3 / (3 * 210e9 * 0.02 ** 4 / 12)
    assert result["levels"][-1]["values"]["response"] == pytest.approx(euler_bernoulli, rel=0.01)
    assert stages[0] == "convergence-1-5-meshing" and "convergence-3-5-solving" in stages
    saved = json.loads((tmp_path / "study" / "convergence.json").read_text())
    assert saved["verdict"] == "converged"
    for name in ("report.html", "convergence.csv", "mesh-1/results.html", "mesh-3/results.html"):
        assert (tmp_path / "study" / name).is_file()


@pytest.mark.integration
def test_element_limit_stops_study_before_an_oversized_mesh(tmp_path):
    from opensim.geometry import make_box
    from opensim.solver import find_solver
    try:
        find_solver()
    except FileNotFoundError:
        pytest.skip("CalculiX unavailable")
    make_box(tmp_path / "beam.step", (0.3, 0.02, 0.02))
    result = run_convergence(tmp_path / "beam.step", tmp_path / "study", size=0.01, levels=6, ratio=2.0, max_elements=20000,
                             order=1, load=100)
    assert len(result["levels"]) == 2 and "element limit" in result["stop_reason"]


@pytest.mark.integration
def test_convergence_job_runs_through_workspace_worker(tmp_path):
    from opensim.geometry import make_box
    from opensim.solver import find_solver
    try:
        find_solver()
    except FileNotFoundError:
        pytest.skip("CalculiX unavailable")
    workspace = Workspace(tmp_path / "workspace")
    project = workspace.create_project("Study job")
    make_box(tmp_path / "bar.step", (0.1, 0.02, 0.02))
    workspace.import_cad(project["id"], str(tmp_path / "bar.step"))
    workspace.set_parameters(project["id"], {"mesh_size_m": 0.01, "convergence_levels": 3, "element_order": 2})
    job = workspace.start_job(project["id"], "convergence")
    deadline = time.time() + 300
    while workspace.get_job(job["id"])["status"] in {"queued", "running"} and time.time() < deadline:
        time.sleep(0.3)
    finished = workspace.get_job(job["id"])
    assert finished["status"] == "completed", finished["error"]
    results = workspace.get_convergence_results(project["id"])
    assert len(results["meshes"]) == 3
    assert all(__import__("pathlib").Path(path).is_file() for path in results["artifacts"].values())
