import numpy as np
import pytest

from opensim.geometry import Mesh, import_and_mesh, make_box
from opensim.loads import assemble_load
from opensim.distributed_validation import uniform_beam_deflection, run_distributed_validation
from opensim.workspace import Workspace


@pytest.fixture(scope="module", params=[1, 2])
def surface_mesh(tmp_path_factory, request):
    directory = tmp_path_factory.mktemp(f"traction-{request.param}")
    cad = directory / "box.step"
    make_box(cad, (0.1, 0.02, 0.03))
    return import_and_mesh(cad, 0.012, 1, directory / "mesh.msh", order=request.param)


@pytest.mark.parametrize("surface", ["x-min", "x-max", "y-min", "y-max", "z-min", "z-max"])
@pytest.mark.parametrize("axis", ["x", "y", "z"])
def test_all_surfaces_and_vector_directions_exact_resultants_and_virtual_work(surface_mesh, surface, axis):
    mesh = surface_mesh
    loading = assemble_load(mesh, -123.4, axis, "traction", surface)
    expected_force = np.zeros(3)
    expected_force["xyz".index(axis)] = -123.4
    dimensions = np.array([0.1, 0.02, 0.03])
    coordinate_axis = "xyz".index(surface[0])
    expected_area = np.prod(np.delete(dimensions, coordinate_axis))
    centroid = dimensions / 2
    centroid[coordinate_axis] = 0 if surface.endswith("min") else dimensions[coordinate_axis]
    assert loading.area == pytest.approx(expected_area, rel=1e-10)
    np.testing.assert_allclose(loading.centroid, centroid, atol=1e-12)
    np.testing.assert_allclose(loading.forces.sum(axis=0), expected_force, atol=1e-10)
    np.testing.assert_allclose(np.cross(mesh.points, loading.forces).sum(axis=0), np.cross(centroid, expected_force), atol=1e-10)
    reversed_load = assemble_load(mesh, 246.8, axis, "traction", surface)
    np.testing.assert_allclose(reversed_load.forces, -2 * loading.forces, atol=1e-10)
    if mesh.element_type == "C3D10":
        corner_nodes = np.unique(mesh.tetrahedra[:, :4])
        np.testing.assert_allclose(loading.forces[corner_nodes], 0, atol=1e-12)
        for test_axis in range(3):
            squared_average = centroid[test_axis] ** 2 if test_axis == coordinate_axis else dimensions[test_axis] ** 2 / 3
            work = np.sum(loading.forces[:, "xyz".index(axis)] * mesh.points[:, test_axis] ** 2)
            assert work == pytest.approx(-123.4 * squared_average, abs=1e-10)


def test_surface_selection_does_not_load_an_extreme_point_or_curved_quadratic_face():
    corners = np.array([[0, 0, 0], [0, 2, 0], [0, 0, 3], [4, 0, 0]], dtype=float)
    edges = [(0, 1), (1, 2), (0, 2), (0, 3), (1, 3), (2, 3)]
    points = np.vstack([corners, [(corners[first] + corners[second]) / 2 for first, second in edges]])
    mesh = Mesh(points, np.arange(10).reshape(1, 10))
    with pytest.raises(ValueError, match="No planar"):
        assemble_load(mesh, 1, "x", "traction", "x-max")
    points[4, 1] += 0.1
    with pytest.raises(ValueError, match="straight-sided"):
        assemble_load(mesh, 1, "x", "traction", "x-min")


def test_distributed_inputs_are_validated_and_saved_without_changing_unit_meaning(tmp_path):
    workspace = Workspace(tmp_path)
    project = workspace.create_project("Surface load")
    configured = workspace.set_parameters(project["id"], {"load_kind": "traction", "load_surface": "z-max", "load_axis": "z", "load_N": -10})
    assert configured["parameters"]["load_N"] == -10
    assert Workspace(tmp_path).get_project(project["id"])["parameters"]["load_surface"] == "z-max"
    with pytest.raises(ValueError):
        workspace.set_parameters(project["id"], {"load_surface": "all"})
    assert uniform_beam_deflection(1) == pytest.approx(-0.0004464285714285714)
    assert uniform_beam_deflection(0) == 0


@pytest.mark.integration
def test_real_uniform_traction_axial_and_distributed_beam_mesh_studies(tmp_path):
    pytest.importorskip("matplotlib")
    from opensim.solver import find_solver
    try:
        find_solver()
    except FileNotFoundError:
        pytest.skip("CalculiX unavailable")
    report = run_distributed_validation(tmp_path / "validation")
    assert report["result"] == "PASS"
    assert all(report["criteria"].values())
    fine = report["beam_cases"][-1]
    assert fine["reaction_z_N"] == pytest.approx(10, rel=1e-5)
    assert fine["reaction_moment_y_Nm"] == pytest.approx(-5, rel=1e-5)
    assert fine["applied_at_support_z_N"] < 0
    assert fine["reported_support_force_z_N"] - fine["applied_at_support_z_N"] == pytest.approx(fine["reaction_z_N"])
    assert fine["traction_Pa"] == pytest.approx(-500)
    fields = np.load(tmp_path / "validation" / "fine" / "fields.npz")
    np.testing.assert_allclose(fields["applied_forces_N"].sum(axis=0), [0, 0, -10], atol=1e-10)
    assert (tmp_path / "validation" / "validation.png").is_file()
