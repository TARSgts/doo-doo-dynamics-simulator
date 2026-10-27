import numpy as np
import pytest

from opensim.geometry import import_and_mesh, make_box
from opensim.results import write_vtk
from opensim.solver import write_deck
from opensim.validation import euler_bernoulli, run_cantilever_validation


def test_independent_beam_formula_end_conditions_and_scaling():
    assert euler_bernoulli(0) == 0
    assert euler_bernoulli(1) == pytest.approx(-10 / (3 * 210e9 * (0.02 * 0.02 ** 3 / 12)))
    assert euler_bernoulli(1, force=-20) == pytest.approx(2 * euler_bernoulli(1))
    assert euler_bernoulli(2, length=2) == pytest.approx(8 * euler_bernoulli(1))


def test_quadratic_mapping_surface_quadrature_and_point_force(tmp_path):
    cad = tmp_path / "beam.step"
    make_box(cad, (0.1, 0.02, 0.02))
    mesh = import_and_mesh(cad, 0.01, 1, tmp_path / "mesh.msh", order=2, tip_point=True)
    assert mesh.element_type == "C3D10"
    edges = [(0, 1), (1, 2), (0, 2), (0, 3), (1, 3), (2, 3)]
    for mid, (start, end) in enumerate(edges, start=4):
        np.testing.assert_allclose(mesh.points[mesh.tetrahedra[:, mid]],
                                   (mesh.points[mesh.tetrahedra[:, start]] + mesh.points[mesh.tetrahedra[:, end]]) / 2,
                                   atol=1e-10)
    np.testing.assert_allclose(mesh.points[mesh.tip_node()], [0.1, 0.01, 0.01], atol=1e-10)
    polynomial = np.column_stack([np.zeros(len(mesh.points)), np.zeros(len(mesh.points)), mesh.points[:, 2] ** 2])
    assert mesh.tip_average(polynomial)[2] == pytest.approx(0.02 ** 2 / 3, rel=1e-9)
    deck = tmp_path / "model.inp"
    write_deck(mesh, deck, 210e9, 0.3, -10, "z", "point")
    load_block = deck.read_text().split("*CLOAD\n")[1].split("*NODE PRINT")[0].strip().splitlines()
    assert load_block == [f"{mesh.tip_node() + 1}, 3, -10"]
    vtk = tmp_path / "results.vtk"
    write_vtk(vtk, mesh, np.zeros_like(mesh.points))
    assert f"CELLS {len(mesh.tetrahedra)} {11 * len(mesh.tetrahedra)}" in vtk.read_text()
    assert "\n24\n" in vtk.read_text()


@pytest.mark.integration
def test_real_cantilever_refinement_against_euler_bernoulli(tmp_path):
    pytest.importorskip("matplotlib")
    from opensim.solver import find_solver
    try:
        find_solver()
    except FileNotFoundError:
        pytest.skip("CalculiX unavailable")
    report = run_cantilever_validation(tmp_path / "validation")
    assert report["result"] == "PASS"
    assert all(report["criteria"].values())
    assert report["cases"][0]["tip_error_fraction"] > 0.25
    assert report["cases"][-1]["tip_error_fraction"] < report["cases"][1]["tip_error_fraction"]
    assert report["cases"][-1]["reaction_z_N"] == pytest.approx(10, rel=1e-5)
    assert report["cases"][-1]["reaction_moment_y_Nm"] == pytest.approx(-10, rel=1e-5)
    assert (tmp_path / "validation" / "validation.png").is_file()
