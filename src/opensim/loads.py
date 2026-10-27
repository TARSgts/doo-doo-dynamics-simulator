from dataclasses import dataclass, field

import numpy as np

from opensim.load_settings import LOAD_AXES, LOAD_KINDS, LOAD_SURFACES, NORMAL_AXES


@dataclass
class AppliedLoad:
    forces: np.ndarray
    centroid: np.ndarray
    area: float
    faces: list
    face_directions: list = field(default_factory=list)


def boundary_owners(mesh):
    """Opposite volume node identifies the material side, even inside holes."""
    owners = {}
    for tetrahedron in mesh.tetrahedra:
        for opposite in range(4):
            key = tuple(sorted(int(tetrahedron[index]) for index in range(4) if index != opposite))
            owners[key] = int(tetrahedron[opposite]) if key not in owners else None
    return owners


def assemble_load(mesh, total_force, axis="x", kind="face", surface="x-max", region=None):
    if not np.isfinite(total_force) or total_force == 0:
        raise ValueError("Total force must be finite and nonzero")
    if axis not in LOAD_AXES or kind not in LOAD_KINDS or surface not in LOAD_SURFACES:
        raise ValueError("Choose X/Y/Z or normal-in/normal-out, face/point/traction, and a valid bounding-plane surface")
    normal = axis in NORMAL_AXES
    if normal and kind != "traction":
        raise ValueError("Perpendicular surface loading requires uniform surface traction")
    forces = np.zeros_like(mesh.points, dtype=float)
    direction = "xyz".index(axis) if not normal else None
    if kind != "traction":
        nodes = np.array([mesh.tip_node()]) if kind == "point" else mesh.end_nodes("max")
        if kind == "face" and (len(nodes) < 3 or np.linalg.matrix_rank(mesh.points[nodes] - mesh.points[nodes[0]]) < 2):
            raise ValueError("The end face needs at least three noncollinear nodes")
        forces[nodes, direction] = total_force / len(nodes)
        return AppliedLoad(forces, mesh.points[nodes].mean(axis=0), 0.0, [])
    coordinate_axis = "xyz".index(surface[0])
    target = mesh.points[:, coordinate_axis].min() if surface.endswith("min") else mesh.points[:, coordinate_axis].max()
    tolerance = float(np.ptp(mesh.points, axis=0).max()) * 1e-8
    area_sum, first_moment, faces, directions = 0.0, np.zeros(3), [], []
    owners = boundary_owners(mesh) if normal else None
    from opensim.regions import selected_faces
    candidates = selected_faces(mesh, region) if region else mesh.boundary_elements()
    for face in candidates:
        if not region and not np.all(np.abs(mesh.points[face, coordinate_axis] - target) <= tolerance):
            continue
        corners = mesh.points[face[:3]]
        area_vector = np.cross(corners[1] - corners[0], corners[2] - corners[0]) / 2
        area = np.linalg.norm(area_vector)
        if area <= 0:
            raise ValueError("Selected load surface contains a degenerate triangle")
        if len(face) == 6:
            midpoints = (corners + corners[[1, 2, 0]]) / 2
            if not np.allclose(mesh.points[face[3:]], midpoints, rtol=0, atol=tolerance):
                raise ValueError("Uniform traction currently requires straight-sided quadratic surface triangles")
        weighted_nodes = face[3:] if len(face) == 6 else face
        vector = np.zeros(3)
        if normal:
            opposite = owners.get(tuple(sorted(face[:3])))
            if opposite is None:
                raise ValueError("Normal loading requires a boundary face with one adjacent solid element")
            vector = area_vector / area
            if np.dot(vector, mesh.points[opposite] - corners[0]) > 0:
                vector = -vector
            if axis == "normal-in":
                vector = -vector
        else:
            vector[direction] = 1
        forces[weighted_nodes] += area / 3 * vector
        area_sum += area
        first_moment += area * corners.mean(axis=0)
        faces.append(face)
        directions.append(vector * np.sign(total_force))
    if area_sum <= 0:
        raise ValueError("No planar boundary surface found at the selected bounding plane")
    forces *= total_force / area_sum
    return AppliedLoad(forces, first_moment / area_sum, area_sum, faces, directions)
