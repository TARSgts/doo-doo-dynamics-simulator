from dataclasses import dataclass

import numpy as np

from opensim.load_settings import LOAD_KINDS, LOAD_SURFACES


@dataclass
class AppliedLoad:
    forces: np.ndarray
    centroid: np.ndarray
    area: float
    faces: list


def assemble_load(mesh, total_force, axis="x", kind="face", surface="x-max"):
    if not np.isfinite(total_force) or total_force == 0:
        raise ValueError("Total force must be finite and nonzero")
    if axis not in "xyz" or len(axis) != 1 or kind not in LOAD_KINDS or surface not in LOAD_SURFACES:
        raise ValueError("Choose X/Y/Z, face/point/traction, and a valid bounding-plane surface")
    forces = np.zeros_like(mesh.points, dtype=float)
    direction = "xyz".index(axis)
    if kind != "traction":
        nodes = np.array([mesh.tip_node()]) if kind == "point" else mesh.end_nodes("max")
        if kind == "face" and (len(nodes) < 3 or np.linalg.matrix_rank(mesh.points[nodes] - mesh.points[nodes[0]]) < 2):
            raise ValueError("The end face needs at least three noncollinear nodes")
        forces[nodes, direction] = total_force / len(nodes)
        return AppliedLoad(forces, mesh.points[nodes].mean(axis=0), 0.0, [])
    coordinate_axis = "xyz".index(surface[0])
    target = mesh.points[:, coordinate_axis].min() if surface.endswith("min") else mesh.points[:, coordinate_axis].max()
    tolerance = float(np.ptp(mesh.points, axis=0).max()) * 1e-8
    area_sum, first_moment, faces = 0.0, np.zeros(3), []
    for face in mesh.boundary_elements():
        if not np.all(np.abs(mesh.points[face, coordinate_axis] - target) <= tolerance):
            continue
        corners = mesh.points[face[:3]]
        area = np.linalg.norm(np.cross(corners[1] - corners[0], corners[2] - corners[0])) / 2
        if area <= 0:
            raise ValueError("Selected load surface contains a degenerate triangle")
        if len(face) == 6:
            midpoints = (corners + corners[[1, 2, 0]]) / 2
            if not np.allclose(mesh.points[face[3:]], midpoints, rtol=0, atol=tolerance):
                raise ValueError("Uniform traction currently requires straight-sided quadratic surface triangles")
        weighted_nodes = face[3:] if len(face) == 6 else face
        forces[weighted_nodes, direction] += area / 3
        area_sum += area
        first_moment += area * corners.mean(axis=0)
        faces.append(face)
    if area_sum <= 0:
        raise ValueError("No planar boundary surface found at the selected bounding plane")
    forces *= total_force / area_sum
    return AppliedLoad(forces, first_moment / area_sum, area_sum, faces)
