import numpy as np
import pytest

from opensim.hole_validation import (consistent_edge_loads, kirsch_hoop, mesh_quarter_plate,
                                     polar_boundary_stress, read_frd_stress, run_hole_validation)


def frd_document(rows):
    names = ["SXX", "SYY", "SZZ", "SXY", "SYZ", "SZX"]
    header = " -4  STRESS 6 1\n" + "".join(f" -5 {name} 1 4 1 1\n" for name in names)
    return header + "".join(f" -1{node:10d}" + "".join(f"{value:12.5E}" for value in values) + "\n"
                            for node, values in rows) + " -3\n"


def test_kirsch_stress_reference_and_tensor_transformation():
    angles = np.array([0, np.pi / 4, np.pi / 2])
    np.testing.assert_allclose(kirsch_hoop(angles), [-1, 1, 3])
    np.testing.assert_allclose(kirsch_hoop(angles, 2e6), [-2e6, 2e6, 6e6])
    tensor = np.tile([5, 7, 0, 2, 0, 0], (3, 1))
    hoop, radial = polar_boundary_stress(angles, tensor)
    np.testing.assert_allclose(hoop, [7, 4, 5])
    np.testing.assert_allclose(radial, [5, 8, 7])


def test_frd_reads_adjacent_signed_fixed_width_fields(tmp_path):
    path = tmp_path / "stress.frd"
    values = [1e6, -2e6, -3e6, 4e5, -5e5, 6e5]
    path.write_text(frd_document([(1, values), (2, values)]))
    np.testing.assert_allclose(read_frd_stress(path, 2), [values, values])


@pytest.mark.parametrize("problem", ["missing", "duplicate", "nonfinite", "unterminated", "components"])
def test_frd_rejects_invalid_stress_results(tmp_path, problem):
    values = [1, 2, 3, 4, 5, 6]
    rows = [(1, values), (2, values)]
    if problem == "missing":
        rows.pop()
    elif problem == "duplicate":
        rows.append((1, values))
    elif problem == "nonfinite":
        rows[0] = (1, [float("nan"), 2, 3, 4, 5, 6])
    document = frd_document(rows)
    if problem == "unterminated":
        document = document.replace(" -3\n", "")
    if problem == "components":
        document = document.replace("SXX", "BAD")
    path = tmp_path / "bad.frd"
    path.write_text(document)
    with pytest.raises(ValueError):
        read_frd_stress(path, 2)


def test_curved_hole_mesh_and_consistent_traction_resultant(tmp_path):
    mesh = mesh_quarter_plate(tmp_path / "mesh.msh", half_width=0.2, radial=4, angular=4)
    assert mesh.quadrilaterals.shape == (32, 8)
    hole = np.abs(np.linalg.norm(mesh.points[:, :2], axis=1) - 0.005) < 1e-9
    assert hole.sum() == 17
    forces = consistent_edge_loads(mesh, 0.2, 0.0001, 1e6)
    np.testing.assert_allclose(forces.sum(axis=0), [20, 0, 0], atol=1e-10)
    np.testing.assert_allclose(np.cross(mesh.points, forces).sum(axis=0), [0, 0, -2], atol=1e-10)
    with pytest.raises(ValueError, match="positive and finite"):
        consistent_edge_loads(mesh, 0.2, 0, 1e6)


@pytest.mark.integration
def test_real_hole_stress_concentration_mesh_and_domain_checks(tmp_path):
    pytest.importorskip("matplotlib")
    from opensim.solver import find_solver
    try:
        find_solver()
    except FileNotFoundError:
        pytest.skip("CalculiX unavailable")
    report = run_hole_validation(tmp_path / "hole-validation")
    assert report["result"] == "PASS"
    assert all(report["criteria"].values())
    fine = report["cases"][2]
    assert fine["Kt_gross"] == pytest.approx(3, rel=0.01)
    assert fine["peak_hoop_stress_Pa"] == pytest.approx(3e6, rel=0.01)
    assert fine["peak_angle_deg"] == pytest.approx(90)
    assert fine["reaction_N"][0] == pytest.approx(-20, rel=1e-5)
    assert fine["Kt_net"] == pytest.approx(fine["Kt_gross"] * 0.975)
    assert fine["elements"] > report["cases"][0]["elements"]
    assert (tmp_path / "hole-validation" / "validation.png").is_file()
    with pytest.raises(FileExistsError):
        run_hole_validation(tmp_path / "hole-validation")
