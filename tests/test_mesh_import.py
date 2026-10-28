from pathlib import Path
import struct
import zipfile
import json
import hashlib

import gmsh
import numpy as np
import pytest

from opensim.geometry import gmsh_session, import_and_mesh
from opensim.mesh_import import clean_surface, read_triangles


def box_triangles(size=(2.0, 1.0, 0.5)):
    """Outward-wound closed box surface, 12 triangles."""
    x, y, z = size
    corners = np.array([[0, 0, 0], [x, 0, 0], [x, y, 0], [0, y, 0], [0, 0, z], [x, 0, z], [x, y, z], [0, y, z]], dtype=float)
    faces = [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
             [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]]
    return corners[faces]


def write_stl(path, triangles, binary=True):
    if binary:
        with path.open("wb") as handle:
            handle.write(b"test".ljust(80, b" ") + struct.pack("<I", len(triangles)))
            for triangle in triangles:
                handle.write(struct.pack("<12fH", 0, 0, 0, *triangle.ravel(), 0))
    else:
        facets = "".join("facet normal 0 0 0\nouter loop\n" + "".join(f"vertex {a} {b} {c}\n" for a, b, c in triangle)
                         + "endloop\nendfacet\n" for triangle in triangles)
        path.write_text(f"solid test\n{facets}endsolid test\n")


def write_3mf(path, points, faces, transform=None, unit="millimeter"):
    vertices = "".join(f'<vertex x="{a}" y="{b}" z="{c}"/>' for a, b, c in points)
    triangles = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in faces)
    item = f'<item objectid="1"{f" transform={chr(34)}{transform}{chr(34)}" if transform else ""}/>'
    model = (f'<?xml version="1.0"?><model unit="{unit}" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
             f'<resources><object id="1" type="model"><mesh><vertices>{vertices}</vertices><triangles>{triangles}</triangles>'
             f'</mesh></object></resources><build>{item}</build></model>')
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("3D/3dmodel.model", model)


def tet_volume(mesh):
    corners = mesh.points[mesh.tetrahedra[:, :4]]
    return float(np.abs(np.linalg.det(corners[:, 1:] - corners[:, :1])).sum() / 6)


def test_automatic_surface_cleanup_preserves_shape_and_reports_changes():
    triangles = box_triangles()
    triangles[2] = triangles[2][[0, 2, 1]]
    damaged = np.concatenate([triangles, triangles[:1], np.zeros((1, 3, 3))])
    original = damaged.copy()
    report = {}
    points, faces = clean_surface(damaged, repair=True, report=report)
    np.testing.assert_array_equal(damaged, original)
    assert len(faces) == 12
    assert report['removed_duplicate_triangles'] == 1
    assert report['removed_degenerate_triangles'] == 1
    assert report['reoriented_triangles'] > 0
    assert report['enclosed_volume_m3'] == pytest.approx(1)
    # Repaired output passes the strict validator, including oriented edges.
    clean_surface(points[faces])
    np.testing.assert_allclose(points.min(axis=0), [0, 0, 0])
    np.testing.assert_allclose(points.max(axis=0), [2, 1, 0.5])


def test_automatic_cleanup_does_not_fill_holes_or_join_shells():
    with pytest.raises(ValueError, match='open edge'):
        clean_surface(box_triangles()[:-1], repair=True)
    with pytest.raises(ValueError, match='disconnected'):
        clean_surface(np.concatenate([box_triangles(), box_triangles() + [5, 0, 0]]), repair=True)
    with pytest.raises(ValueError, match='shared by more than two'):
        clean_surface(np.concatenate([box_triangles(), box_triangles() + [2, 0, 0]]), repair=True)


def test_damaged_stl_is_automatically_repaired_and_meshed_without_overwrite(tmp_path):
    triangles = box_triangles((100, 20, 20))
    triangles[3] = triangles[3][[0, 2, 1]]
    source = tmp_path / 'damaged.stl'
    write_stl(source, np.concatenate([triangles, triangles[:1]]))
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    mesh = import_and_mesh(source, 0.01, 0.001, tmp_path / 'mesh.msh', order=2)
    assert mesh.element_type == 'C3D10'
    assert tet_volume(mesh) == pytest.approx(0.1 * 0.02 * 0.02, rel=1e-6)
    report = json.loads((tmp_path / 'mesh.repair.json').read_text())
    assert report == mesh.repair_report
    assert report['removed_duplicate_triangles'] == 1
    assert report['reoriented_triangles'] > 0
    assert report['status'] == 'completed' and report['source_unchanged']
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_parametrization_failure_retries_clean_model_and_preserves_volume(tmp_path, monkeypatch):
    source = tmp_path / 'patches.stl'
    write_stl(source, box_triangles())
    create_geometry = gmsh.model.mesh.createGeometry
    attempts = []
    def fail_first(*args, **kwargs):
        attempts.append(True)
        if len(attempts) == 1:
            raise Exception('Wrong topology of boundary mesh for parametrization')
        return create_geometry(*args, **kwargs)
    monkeypatch.setattr(gmsh.model.mesh, 'createGeometry', fail_first)
    mesh = import_and_mesh(source, 0.3, 1, tmp_path / 'mesh.msh')
    assert tet_volume(mesh) == pytest.approx(1, rel=1e-6)
    report = mesh.repair_report
    assert report['patch_retry_used']
    assert [a['patch_angle_degrees'] for a in report['attempts']] == [40, 25]
    assert [a['status'] for a in report['attempts']] == ['failed', 'completed']
    assert len(mesh.surface_catalog()) >= 6


def test_unrepairable_patch_geometry_stops_after_bounded_retries_and_saves_report(tmp_path, monkeypatch):
    source = tmp_path / 'unrepairable.stl'
    write_stl(source, box_triangles())
    def fail(*args, **kwargs):
        raise Exception('Wrong topology of boundary mesh for parametrization')
    monkeypatch.setattr(gmsh.model.mesh, 'createGeometry', fail)
    with pytest.raises(ValueError, match='after 3 attempts'):
        import_and_mesh(source, 0.3, 1, tmp_path / 'mesh.msh')
    report = json.loads((tmp_path / 'mesh.repair.json').read_text())
    assert len(report['attempts']) == 3 and report['status'] == 'failed'
    assert not (tmp_path / 'mesh.msh').exists()


def test_open_surface_failure_records_actionable_report(tmp_path):
    source = tmp_path / 'hole.stl'
    write_stl(source, box_triangles()[:-1])
    with pytest.raises(ValueError, match='open edge'):
        import_and_mesh(source, 0.3, 1, tmp_path / 'mesh.msh')
    report = json.loads((tmp_path / 'mesh.repair.json').read_text())
    assert report['status'] == 'failed' and report['attempts'] == []


def test_readers_agree_for_binary_ascii_stl_obj_quads_and_3mf_transform(tmp_path):
    triangles = box_triangles()
    write_stl(tmp_path / "binary.stl", triangles)
    write_stl(tmp_path / "ascii.stl", triangles, binary=False)
    reference = np.sort(read_triangles(tmp_path / "binary.stl").reshape(-1, 3), axis=0)
    assert np.allclose(np.sort(read_triangles(tmp_path / "ascii.stl").reshape(-1, 3), axis=0), reference)
    # OBJ with quads, texture/normal indices and a negative (relative) index.
    corners = [[0, 0, 0], [2, 0, 0], [2, 1, 0], [0, 1, 0], [0, 0, 0.5], [2, 0, 0.5], [2, 1, 0.5], [0, 1, 0.5]]
    quads = [[1, 4, 3, 2], [5, 6, 7, 8], [1, 2, 6, 5], [2, 3, 7, 6], [3, 4, 8, 7], [4, 1, 5, -1]]
    (tmp_path / "box.obj").write_text("# box\n" + "".join(f"v {a} {b} {c}\n" for a, b, c in corners) + "vt 0 0\n"
                                      + "".join("f " + " ".join(f"{index}/1/1" for index in quad) + "\n" for quad in quads))
    obj = read_triangles(tmp_path / "box.obj")
    assert len(obj) == 12
    points, faces = clean_surface(obj)
    assert len(points) == 8 and len(faces) == 12
    write_3mf(tmp_path / "moved.3mf", np.array(corners), np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
              [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]]), transform="1 0 0 0 1 0 0 0 1 10 20 30")
    moved = read_triangles(tmp_path / "moved.3mf").reshape(-1, 3)
    assert np.allclose(moved.min(axis=0), [10, 20, 30]) and np.allclose(moved.max(axis=0), [12, 21, 30.5])


def test_open_flipped_nonmanifold_and_inside_out_surfaces(tmp_path):
    triangles = box_triangles()
    with pytest.raises(ValueError, match="open edge"):
        clean_surface(triangles[:-1])
    flipped = triangles.copy()
    flipped[0] = flipped[0][[0, 2, 1]]
    with pytest.raises(ValueError, match="flipped"):
        clean_surface(flipped)
    with pytest.raises(ValueError, match="duplicated"):
        clean_surface(np.concatenate([triangles, triangles[:1]]))
    second = box_triangles() + [2.0, 0, 0]  # touching box shares edges with the first one
    with pytest.raises(ValueError, match="not a single closed solid"):
        clean_surface(np.concatenate([triangles, second]))
    _, faces = clean_surface(triangles[:, [0, 2, 1]])  # inside-out is repaired, not rejected
    points, _ = clean_surface(triangles)
    corners = points[faces]
    assert np.einsum("ij,ij->i", corners[:, 0], np.cross(corners[:, 1], corners[:, 2])).sum() > 0
    (tmp_path / "junk.stl").write_bytes(b"\x00" * 50)
    with pytest.raises(ValueError, match="neither"):
        read_triangles(tmp_path / "junk.stl")
    with pytest.raises(ValueError, match="fewer than four"):
        read_triangles(write_stl(tmp_path / "tiny.stl", triangles[:2]) or tmp_path / "tiny.stl")


@pytest.mark.parametrize("unit, factor", [("meter", 1000), ("inch", 25.4), ("micron", 0.001), ("millimeter", 1)])
def test_3mf_units_include_build_translation(tmp_path, unit, factor):
    points, faces = clean_surface(box_triangles())
    path = tmp_path / "units.3mf"
    write_3mf(path, points, faces, transform="1 0 0 0 1 0 0 0 1 10 20 30", unit=unit)
    actual = read_triangles(path).reshape(-1, 3)
    np.testing.assert_allclose(actual.min(axis=0), np.array([10, 20, 30]) * factor)
    np.testing.assert_allclose(actual.max(axis=0), np.array([12, 21, 30.5]) * factor)


def test_3mf_primary_relationship_selects_built_model_not_first_archive_entry(tmp_path):
    points, faces = clean_surface(box_triangles())
    source = tmp_path / "source.3mf"
    write_3mf(source, points, faces)
    with zipfile.ZipFile(source) as archive:
        model = archive.read("3D/3dmodel.model")
    path = tmp_path / "related.3mf"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("3D/unbuilt.model", model.replace(b'unit="millimeter"', b'unit="meter"'))
        archive.writestr("3D/built.model", model)
        archive.writestr("_rels/.rels", '<Relationships><Relationship Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel" Target="/3D/built.model"/></Relationships>')
    assert read_triangles(path).max() == pytest.approx(2)


@pytest.mark.parametrize("index", ["0", "-5", "5"])
def test_obj_rejects_invalid_indices_instead_of_wrapping_to_another_vertex(tmp_path, index):
    path = tmp_path / "bad.obj"
    path.write_text(f"v 0 0 0\nv 1 0 0\nv 0 1 0\nv 0 0 1\nf 1 2 {index}\n")
    with pytest.raises(ValueError, match="not a valid OBJ"):
        read_triangles(path)


def test_disjoint_closed_shells_are_rejected_before_gmsh():
    with pytest.raises(ValueError, match="disconnected surface shells"):
        clean_surface(np.concatenate([box_triangles(), box_triangles() + [5, 0, 0]]))


@pytest.mark.parametrize("vertices", [
    [[0, 0, 0], [2, 0, 0], [1, 0.5, 0], [2, 2, 0], [0, 2, 0]],
    [[0, 0, 0], [2, 0, 0], [2, 2, 0.5], [0, 2, 0]],
])
def test_obj_requires_triangulation_of_unsupported_polygons(tmp_path, vertices):
    path = tmp_path / "polygon.obj"
    path.write_text("".join(f"v {x} {y} {z}\n" for x, y, z in vertices)
                    + "f " + " ".join(str(index + 1) for index in range(len(vertices))) + "\n")
    with pytest.raises(ValueError, match="export triangulated OBJ"):
        read_triangles(path)


def plate_files(directory: Path):
    """The perforated test plate in mm: exact STEP plus an STL exported from a fine surface mesh."""
    with gmsh_session():
        gmsh.model.add("plate")
        plate = gmsh.model.occ.addBox(0, 0, 0, 100, 40, 5)
        hole = gmsh.model.occ.addCylinder(50, 20, -1, 0, 0, 7, 6)
        gmsh.model.occ.cut([(3, plate)], [(3, hole)])
        gmsh.model.occ.synchronize()
        gmsh.write(str(directory / "plate.step"))
        gmsh.option.setNumber("Mesh.MeshSizeMax", 2)
        gmsh.model.mesh.generate(2)
        gmsh.write(str(directory / "plate.stl"))
    triangles = read_triangles(directory / "plate.stl").reshape(-1, 3)
    with (directory / "plate.obj").open("w") as handle:
        handle.writelines(f"v {a:.17g} {b:.17g} {c:.17g}\n" for a, b, c in triangles)
        handle.writelines(f"f {index + 1} {index + 2} {index + 3}\n" for index in range(0, len(triangles), 3))
    points, inverse = np.unique(triangles, axis=0, return_inverse=True)
    write_3mf(directory / "plate.3mf", points, inverse.reshape(-1, 3))


@pytest.mark.parametrize("order", [1, 2])
def test_stl_obj_and_3mf_rebuild_the_same_solid_as_step(tmp_path, order):
    plate_files(tmp_path)
    exact = (100 * 40 * 5 - np.pi * 6 ** 2 * 5) * 1e-9
    for name in ("plate.step", "plate.stl", "plate.obj", "plate.3mf"):
        mesh = import_and_mesh(tmp_path / name, 0.004, 0.001, tmp_path / f"{name}.msh", order=order)
        assert mesh.element_type == ("C3D10" if order == 2 else "C3D4")
        assert tet_volume(mesh) == pytest.approx(exact, rel=5e-3), name
        assert np.allclose(mesh.points.min(axis=0), 0, atol=1e-9)
        assert np.allclose(mesh.points.max(axis=0), [0.1, 0.04, 0.005], atol=1e-9)
        assert len(np.unique(mesh.tetrahedra)) == len(mesh.points)  # no orphan nodes
        catalog = mesh.surface_catalog()
        assert len(catalog) >= 7  # at least the six box sides and the hole wall are pickable
        assert sum(face["area_m2"] for face in catalog) == pytest.approx(
            2 * (100 * 40 + 100 * 5 + 40 * 5 - np.pi * 36) * 1e-6 + 2 * np.pi * 6 * 5 * 1e-6, rel=5e-3)


def test_tip_point_load_requires_exact_cad(tmp_path):
    write_stl(tmp_path / "box.stl", box_triangles())
    with pytest.raises(ValueError, match="exact CAD"):
        import_and_mesh(tmp_path / "box.stl", 0.2, 1, tmp_path / "box.msh", tip_point=True)


def test_workspace_accepts_mesh_files_and_rejects_others(tmp_path):
    from opensim.workspace import Workspace
    workspace = Workspace(tmp_path / "workspace")
    project = workspace.create_project("Mesh import")
    write_stl(tmp_path / "box.stl", box_triangles())
    assert workspace.import_cad(project["id"], str(tmp_path / "box.stl"))["cad"].endswith(".stl")
    (tmp_path / "part.ply").write_text("ply")
    with pytest.raises(ValueError, match="STL, OBJ or 3MF"):
        workspace.import_cad(project["id"], str(tmp_path / "part.ply"))


@pytest.mark.integration
def test_stl_cantilever_matches_step_solution(tmp_path):
    from opensim.cli import solve
    from opensim.geometry import make_box
    from opensim.solver import find_solver
    try:
        find_solver()
    except FileNotFoundError:
        pytest.skip("CalculiX unavailable")
    make_box(tmp_path / "beam.step", (0.3, 0.02, 0.02))
    triangles = box_triangles((300, 20, 20))
    write_stl(tmp_path / "beam.stl", triangles)
    damaged = triangles.copy()
    damaged[2] = damaged[2][[0, 2, 1]]
    write_stl(tmp_path / "damaged.stl", np.concatenate([damaged, damaged[:1]]))
    results = {}
    for name, scale in (("beam.step", 1.0), ("beam.stl", 0.001), ("damaged.stl", 0.001)):
        results[name] = solve(tmp_path / name, tmp_path / name.replace(".", "-"), size=0.004, scale=scale, young=210e9,
                              poisson=0.3, load=-50, order=2, load_axis="z", load_kind="traction", load_surface="x-max")
    step, stl = results["beam.step"], results["beam.stl"]
    assert stl["relative_force_imbalance"] < 1e-6
    step_tip = step["loaded_surface_mean_displacement_m"][2]
    stl_tip = stl["loaded_surface_mean_displacement_m"][2]
    assert stl_tip == pytest.approx(step_tip, rel=0.01)
    theory = -50 * 0.3 ** 3 / (3 * 210e9 * 0.02 ** 4 / 12)
    assert stl_tip == pytest.approx(theory, rel=0.05)
    repaired = results['damaged.stl']
    assert repaired['mesh_repair']['removed_duplicate_triangles'] == 1
    assert repaired['mesh_repair']['reoriented_triangles'] > 0
    assert repaired['relative_force_imbalance'] < 1e-6
    assert repaired['loaded_surface_mean_displacement_m'][2] == pytest.approx(stl_tip, rel=0.01)
