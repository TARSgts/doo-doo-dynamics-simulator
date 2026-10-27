import json

import numpy as np
import pytest

from opensim.geometry import import_and_mesh, make_box
from opensim.results import write_viewer


@pytest.mark.parametrize("order", [1, 2])
def test_rendered_triangles_keep_exact_cad_face_identity(tmp_path, order):
    cad = tmp_path / "box.step"
    make_box(cad, (1, 0.2, 0.1))
    mesh = import_and_mesh(cad, 0.1, 1, tmp_path / "mesh.msh", order=order)
    faces, ids = mesh.boundary_faces(), mesh.boundary_face_ids()
    assert len(faces) == len(ids)
    assert set(ids) == {int(tag) for tag in mesh.surface_groups}
    assert 0 not in ids
    # Every displayed triangle must lie on its actual CAD plane, including
    # all four subdivisions of each six-node quadratic boundary element.
    for triangle, tag in zip(faces, ids):
        group = np.asarray(mesh.surface_groups[str(tag)])
        points = mesh.points[group.reshape(-1)]
        axis = np.ptp(points, axis=0).argmin()
        np.testing.assert_allclose(mesh.points[triangle, axis], points[0, axis], atol=1e-10)
    viewer = tmp_path / "preview.html"
    write_viewer(viewer, mesh, np.zeros_like(mesh.points), {"view": "mesh"})
    data, _ = json.JSONDecoder().raw_decode(viewer.read_text().split("const simulation = ", 1)[1])
    assert data["face_ids"] == ids
    assert data["faces"] == faces
