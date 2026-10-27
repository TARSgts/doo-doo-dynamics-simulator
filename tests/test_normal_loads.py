import gmsh
import numpy as np
import pytest

from opensim.geometry import Mesh, gmsh_session, import_and_mesh, make_box
from opensim.loads import assemble_load
from opensim.solver import deck_number, write_deck
from opensim.workspace import Workspace


@pytest.mark.parametrize("value", [-1.59612629826565e-11, -9.42849795070461e-5, 1.23456789012345e-100, -1.23456789012345e100, 210e9])
def test_solver_numbers_fit_the_actual_calculix_read_window(value):
    encoded = deck_number(value)
    assert len(encoded) <= 20
    assert float(encoded[:20]) == pytest.approx(value, rel=1e-11, abs=0)


@pytest.fixture(scope="module", params=[1, 2])
def normal_mesh(tmp_path_factory, request):
    directory = tmp_path_factory.mktemp(f"normal-{request.param}")
    cad = directory / "box.step"
    make_box(cad, (0.1, 0.02, 0.03))
    return import_and_mesh(cad, 0.012, 1, directory / "mesh.msh", order=request.param)


@pytest.mark.parametrize("surface", ["x-min", "x-max", "y-min", "y-max", "z-min", "z-max"])
@pytest.mark.parametrize("axis", ["normal-in", "normal-out"])
def test_normal_load_matches_axis_load_on_every_box_face(normal_mesh, surface, axis):
    coordinate = "xyz".index(surface[0])
    sign = (1 if surface.endswith("max") else -1) * (1 if axis == "normal-out" else -1)
    actual = assemble_load(normal_mesh, 123.4, axis, "traction", surface)
    expected = assemble_load(normal_mesh, sign * 123.4, surface[0], "traction", surface)
    np.testing.assert_allclose(actual.forces, expected.forces, atol=1e-11)
    np.testing.assert_allclose(actual.centroid, expected.centroid, atol=1e-12)
    np.testing.assert_allclose(np.cross(normal_mesh.points, actual.forces).sum(axis=0),
                               np.cross(actual.centroid, actual.forces.sum(axis=0)), atol=1e-11)
    reversed_load = assemble_load(normal_mesh, -123.4, axis, "traction", surface)
    np.testing.assert_allclose(reversed_load.forces, -actual.forces, atol=1e-11)
    assert actual.face_directions[0][coordinate] == sign


@pytest.mark.parametrize("order", [1, 2])
def test_closed_surface_pressure_has_zero_resultant_and_correct_virtual_work(order, tmp_path):
    corners = np.array([[0, 0, 0], [2, 0, 0], [0, 3, 0], [0, 0, 4]], dtype=float)
    edges = [(0, 1), (1, 2), (0, 2), (0, 3), (1, 3), (2, 3)]
    points = corners if order == 1 else np.vstack([corners, [(corners[a] + corners[b]) / 2 for a, b in edges]])
    mesh = Mesh(points, np.arange(len(points)).reshape(1, -1))
    mesh.surface_groups = {"1": mesh.boundary_elements()}
    # Deliberately reverse each surface record: orientation comes from the
    # adjacent volume, not CAD/triangle winding or the global model center.
    permutation = [0, 2, 1] if order == 1 else [0, 2, 1, 5, 4, 3]
    mesh.surface_groups["1"] = [[face[i] for i in permutation] for face in mesh.surface_groups["1"]]
    area = sum(np.linalg.norm(np.cross(points[f[1]] - points[f[0]], points[f[2]] - points[f[0]])) / 2 for f in mesh.boundary_elements())
    pressure = 37
    load = assemble_load(mesh, pressure * area, "normal-in", "traction", region={"faces": [1]})
    np.testing.assert_allclose(load.forces.sum(axis=0), 0, atol=1e-12)
    np.testing.assert_allclose(np.cross(points, load.forces).sum(axis=0), 0, atol=1e-12)
    volume = abs(np.linalg.det(corners[1:] - corners[0])) / 6
    assert np.sum(load.forces * points) == pytest.approx(-3 * pressure * volume, abs=1e-10)
    if order == 2:
        np.testing.assert_allclose(load.forces[:4], 0, atol=1e-12)
    # A sloped face must export every nonzero force component.
    sloped = next(f for f in mesh.boundary_elements() if 0 not in f[:3])
    mesh.surface_groups["2"] = [sloped]
    sloped_load = write_deck(mesh, tmp_path / "sloped.inp", 210e9, 0, 10, "normal-in", "traction", load_region={"faces": [2]})
    assert np.all(np.abs(sloped_load.forces.sum(axis=0)) > 0)
    rows = (tmp_path / "sloped.inp").read_text().split("*CLOAD\n", 1)[1].split("*NODE PRINT", 1)[0].splitlines()
    reconstructed = np.zeros_like(points)
    for row in rows:
        node, axis, value = row.split(",")
        reconstructed[int(node) - 1, int(axis) - 1] = float(value)
    np.testing.assert_allclose(reconstructed, sloped_load.forces, atol=1e-12)


def test_inner_cylinder_normals_point_into_material_for_inward_loading(tmp_path):
    cad = tmp_path / "tube.step"
    with gmsh_session():
        gmsh.model.add("tube")
        outer = gmsh.model.occ.addCylinder(0, 0, 0, 0, 0, 1, 2)
        inner = gmsh.model.occ.addCylinder(0, 0, -0.1, 0, 0, 1.2, 1)
        gmsh.model.occ.cut([(3, outer)], [(3, inner)])
        gmsh.model.occ.synchronize()
        gmsh.write(str(cad))
    mesh = import_and_mesh(cad, 0.4, 1, tmp_path / "tube.msh")
    ids = [int(tag) for tag, faces in mesh.surface_groups.items()
           if np.allclose(np.linalg.norm(mesh.points[np.asarray(faces)[:, :3], :2], axis=2), 1, atol=1e-8)]
    assert len(ids) == 1
    load = assemble_load(mesh, 100, "normal-in", "traction", region={"faces": ids})
    for face, direction in zip(load.faces, load.face_directions):
        radial = mesh.points[face[:3]].mean(axis=0)
        radial[2] = 0
        assert np.dot(radial, direction) > 0
        assert np.linalg.norm(direction) == pytest.approx(1)


def test_normal_inputs_require_surface_loading_and_preserve_signed_force(tmp_path, normal_mesh):
    workspace = Workspace(tmp_path)
    project = workspace.create_project("Normal load")
    with pytest.raises(ValueError, match="requires uniform"):
        workspace.set_parameters(project["id"], {"load_axis": "normal-in"})
    for direction in ("normal-in", "normal-out"):
        configured = workspace.set_parameters(project["id"], {"load_axis": direction, "load_kind": "traction", "load_N": -10})
        assert configured["parameters"]["load_N"] == -10
        with pytest.raises(ValueError, match="requires uniform"):
            assemble_load(normal_mesh, 1, direction, "point")
    loading = write_deck(normal_mesh, tmp_path / "model.inp", 210e9, 0.3, 10, "normal-in", "traction", "z-max")
    rows = (tmp_path / "model.inp").read_text().split("*CLOAD\n", 1)[1].split("*NODE PRINT", 1)[0].splitlines()
    reconstructed = np.zeros_like(normal_mesh.points)
    for row in rows:
        node, axis, value = row.split(",")
        reconstructed[int(node) - 1, int(axis) - 1] = float(value)
    np.testing.assert_allclose(reconstructed, loading.forces, atol=1e-12)


@pytest.mark.integration
@pytest.mark.parametrize("direction,sign", [("normal-in", -1), ("normal-out", 1)])
@pytest.mark.parametrize("spatial", [False, True])
def test_rotated_bar_normal_load_matches_axial_theory(tmp_path, direction, sign, spatial):
    from opensim.cli import solve
    from opensim.solver import find_solver
    try:
        find_solver()
    except FileNotFoundError:
        pytest.skip("CalculiX unavailable")
    angle = 0.63
    axis = np.array([1, 2, 3] if spatial else [0, 0, 1], dtype=float)
    axis /= np.linalg.norm(axis)
    x, y, z = axis
    skew = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
    rotation = np.cos(angle) * np.eye(3) + np.sin(angle) * skew + (1 - np.cos(angle)) * np.outer(axis, axis)
    cad = tmp_path / "rotated.step"
    with gmsh_session():
        gmsh.model.add("rotated_bar")
        bar = gmsh.model.occ.addBox(0, 0, 0, 1, 0.1, 0.1)
        gmsh.model.occ.rotate([(3, bar)], 0, 0, 0, *axis, angle)
        gmsh.model.occ.synchronize()
        gmsh.write(str(cad))
    mesh = import_and_mesh(cad, 0.08, 1, tmp_path / "rotated.msh", order=2)
    local = mesh.points @ rotation
    support = [int(tag) for tag, faces in mesh.surface_groups.items() if np.allclose(local[np.asarray(faces), 0], 0, atol=1e-8)]
    load = [int(tag) for tag, faces in mesh.surface_groups.items() if np.allclose(local[np.asarray(faces), 0], 1, atol=1e-8)]
    assert len(support) == len(load) == 1
    result = solve(cad, tmp_path / "solve", size=0.08, young=210e9, poisson=0, load=1000, order=2,
                   load_kind="traction", load_axis=direction, support_region={"faces": support}, load_region={"faces": load})
    expected = sign * 1000 / (210e9 * 0.01)
    np.testing.assert_allclose(result["loaded_surface_mean_displacement_m"], expected * rotation[:, 0], atol=1e-12)
    assert result["loaded_surface_mean_normal_displacement_m"] == pytest.approx(abs(expected), rel=1e-5)
    np.testing.assert_allclose(result["reaction_N"], -sign * 1000 * rotation[:, 0], atol=0.01)
    assert result["maximum_von_mises_Pa"] == pytest.approx(100000, rel=1e-4)
    assert result["normal_pressure_Pa"] == pytest.approx(-sign * 100000)
    assert result["relative_force_imbalance"] < 1e-5
    assert result["relative_moment_imbalance"] < 1e-5
