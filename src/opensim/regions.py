import numpy as np
from opensim.region_settings import validate_region


def selected_faces(mesh, region):
    validate_region(region)
    if not region:
        return []
    ids = region.get("faces", [])
    if any(str(tag) not in mesh.surface_groups for tag in ids):
        raise ValueError("Selected CAD face IDs are absent from this mesh; reselect after changing CAD")
    candidates = [face for tag in dict.fromkeys(ids) for face in mesh.surface_groups[str(tag)]] if ids else mesh.boundary_elements()
    box = region.get("box_m")
    if box is not None:
        lower, upper = np.array(box[:3]), np.array(box[3:])
        candidates = [face for face in candidates if np.all(mesh.points[face[:3]].mean(axis=0) >= lower)
                      and np.all(mesh.points[face[:3]].mean(axis=0) <= upper)]
    if not candidates:
        raise ValueError("The selected region contains no surface triangles")
    return candidates


def support_nodes(mesh, region=None):
    if region:
        nodes = np.unique(np.asarray([node for face in selected_faces(mesh, region) for node in face], dtype=int))
    else:
        nodes = mesh.end_nodes("min")
    if len(nodes) < 3 or np.linalg.matrix_rank(mesh.points[nodes] - mesh.points[nodes[0]]) < 2:
        raise ValueError("Fixed support needs at least three noncollinear surface nodes; select a support region")
    return nodes
