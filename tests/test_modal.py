import json
import time

import numpy as np
import pytest

from opensim.modal import parse_modal_dat, validate_modal_parameters, write_modal_deck
from opensim.modal_validation import beam_frequencies, beam_shape, shape_mac, run_modal_validation
from opensim.workspace import Workspace


def modal_document():
    lines = ["MODE NO EIGENVALUE FREQUENCY", "1 3.947841760E+01 6.283185307E+00 1.000000000E+00 0.000000000E+00",
             "2 1.579136704E+02 1.256637061E+01 2.000000000E+00 0.000000000E+00", "P A R T I C I P A T I O N F A C T O R S"]
    for mode in (1, 2):
        lines.extend([f"E I G E N V A L U E N U M B E R {mode}", "displacements (vx,vy,vz)", "1 0 0 0", f"2 0 {mode} -1"])
    return "\n".join(lines)


def test_modal_parser_keeps_separate_modes_and_frequency_units(tmp_path):
    path = tmp_path / "model.dat"
    path.write_text(modal_document())
    frequency, eigenvalues, shapes = parse_modal_dat(path, 2, 2)
    np.testing.assert_allclose(frequency, [1, 2])
    np.testing.assert_allclose(eigenvalues, (2 * np.pi * frequency) ** 2)
    assert shapes.shape == (2, 2, 3)
    np.testing.assert_allclose(shapes[:, 1], [[0, 1, -1], [0, 2, -1]])


@pytest.mark.parametrize("problem", ["missing_node", "duplicate_node", "missing_mode", "unstable", "nan", "wrong_units"])
def test_modal_parser_rejects_bad_or_incomplete_eigenpairs(tmp_path, problem):
    document = modal_document()
    if problem == "missing_node":
        document = document.replace("2 0 2 -1", "")
    elif problem == "duplicate_node":
        document += "\n2 0 2 -1"
    elif problem == "missing_mode":
        document = document.split("E I G E N V A L U E N U M B E R 2")[0]
    elif problem == "unstable":
        document = document.replace("3.947841760E+01", "-3.947841760E+01")
    elif problem == "nan":
        document = document.replace("2 0 2 -1", "2 0 nan -1")
    else:
        document = document.replace("1.000000000E+00", "6.283185307E+00")
    path = tmp_path / "bad.dat"
    path.write_text(document)
    with pytest.raises(ValueError):
        parse_modal_dat(path, 2, 2)


@pytest.mark.parametrize("density,count", [(0, 6), (-1, 6), (float("nan"), 6), (True, 6), (7850, 0),
                                         (7850, 31), (7850, 6.0), (7850, True)])
def test_invalid_mass_and_mode_count(density, count):
    with pytest.raises(ValueError):
        validate_modal_parameters(density, count)


def test_modal_reference_scaling_shape_and_sign_invariance():
    frequencies = beam_frequencies()
    assert frequencies[0] == pytest.approx(16.71033194, rel=1e-7)
    np.testing.assert_allclose(beam_frequencies(density=31400), frequencies / 2)
    np.testing.assert_allclose(beam_frequencies(length=2), frequencies / 4)
    coordinate = np.linspace(0, 1, 101)
    reference = beam_shape(coordinate, 0)
    assert reference[0] == 0
    assert shape_mac(coordinate, -3 * reference, reference) == pytest.approx(1)
    with pytest.raises(ValueError):
        shape_mac(coordinate, np.zeros_like(coordinate), reference)


def test_modal_deck_does_not_require_a_static_loaded_end_face(tmp_path):
    from opensim.geometry import Mesh
    mesh = Mesh(np.array([[0, 0, 0], [0, 1, 0], [0, 0, 1], [1, 0, 0]], dtype=float), np.array([[0, 1, 2, 3]]))
    path = tmp_path / "model.inp"
    write_modal_deck(mesh, path, 210e9, 0.3, 7850, 1)
    assert "*FREQUENCY" in path.read_text()
    assert "*CLOAD" not in path.read_text()
    with pytest.raises(ValueError, match="Young's"):
        write_modal_deck(mesh, path, -1, 0.3, 7850, 1)


@pytest.mark.integration
def test_real_modal_validation_frequencies_shapes_and_density_scaling(tmp_path):
    pytest.importorskip("matplotlib")
    from opensim.solver import find_solver
    try:
        find_solver()
    except FileNotFoundError:
        pytest.skip("CalculiX unavailable")
    report = run_modal_validation(tmp_path / "validation")
    assert report["result"] == "PASS"
    assert all(report["criteria"].values())
    directory = tmp_path / "validation" / "fine"
    fields = np.load(directory / "modes.npz")
    np.testing.assert_allclose(np.max(np.linalg.norm(fields["normalized_modes"], axis=2), axis=1), 1)
    deck = (directory / "model.inp").read_text()
    assert "*DENSITY" in deck and "*FREQUENCY" in deck
    assert "*CLOAD" not in deck and "*STATIC" not in deck
    assert "mode_shape_normalized" in (directory / "mode-1.vtk").read_text()
    assert json.loads((directory / "manifest.json").read_text())["analysis"] == "modal"
    assert (directory / "mode-6.html").is_file()


@pytest.mark.integration
def test_modal_worker_selection_stale_results_and_preserved_static_inputs(tmp_path):
    from opensim.geometry import make_box
    from opensim.solver import find_solver
    try:
        find_solver()
    except FileNotFoundError:
        pytest.skip("CalculiX unavailable")
    workspace = Workspace(tmp_path / "workspace")
    project = workspace.create_project("Modal worker")
    cad = tmp_path / "beam.step"
    make_box(cad, (0.1, 0.02, 0.02))
    workspace.import_cad(project["id"], str(cad))
    workspace.set_parameters(project["id"], {"mesh_size_m": 0.01, "element_order": 2, "mode_count": 3})
    job = workspace.start_job(project["id"], "modal")
    with pytest.raises(ValueError, match="active job"):
        workspace.set_parameters(project["id"], {"density_kg_m3": 1000})
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline and workspace.get_job(job["id"])["status"] in {"queued", "running"}:
        time.sleep(0.05)
    assert workspace.get_job(job["id"])["status"] == "completed"
    results = workspace.get_modal_results(project["id"])
    assert len(results["modes"]) == 3
    assert workspace.show_project(project["id"], "modal", 2)["modal_mode"] == 2
    original = workspace.current_artifact(project["id"], "modal", 2)
    assert original.is_file() and original.name == "mode-2.html"
    assert workspace.current_artifact(project["id"], "geometry").is_file()
    assert workspace.current_artifact(project["id"], "mesh").is_file()
    with pytest.raises(ValueError, match="outside"):
        workspace.show_project(project["id"], "modal", 4)
    assert workspace.get_project(project["id"])["parameters"]["load_N"] == 1000
    with pytest.raises(ValueError, match="completed solve"):
        workspace.get_results(project["id"])
    workspace.set_parameters(project["id"], {"density_kg_m3": 2700})
    assert workspace.current_artifact(project["id"], "modal") is None
    with pytest.raises(ValueError, match="current project inputs"):
        workspace.get_modal_results(project["id"])
    assert original.is_file()
