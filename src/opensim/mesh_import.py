"""Read triangle-surface files (STL, OBJ, 3MF) into a clean, closed surface.

These formats store only triangles, not exact CAD faces. The importer merges
duplicate vertices, optionally removes duplicate triangles and fixes orientation,
rejects open or non-manifold surfaces with a clear message,
and writes a clean binary STL that Gmsh can rebuild into a meshable solid.
"""
from pathlib import Path
import posixpath
import re
import struct
import xml.etree.ElementTree as ElementTree
import zipfile

import numpy as np
from opensim.file_formats import MESH_SUFFIXES

THREEMF_TO_MM = {"micron": 0.001, "millimeter": 1, "centimeter": 10, "inch": 25.4, "foot": 304.8, "meter": 1000}
REPAIR_HINT = "Repair it first, for example with your slicer's repair tool, Meshmixer or Fusion's mesh repair, then export again."


def read_triangles(path: Path) -> np.ndarray:
    """Return triangle coordinates in file units for STL/OBJ, normalized mm for 3MF."""
    suffix = path.suffix.lower()
    if suffix == ".stl":
        triangles = _read_stl(path)
    elif suffix == ".obj":
        triangles = _read_obj(path)
    elif suffix == ".3mf":
        triangles = _read_3mf(path)
    else:
        raise ValueError("Supported mesh formats: STL, OBJ, 3MF")
    triangles = np.asarray(triangles, dtype=float).reshape(-1, 3, 3)
    if len(triangles) < 4:
        raise ValueError(f"{path.name} contains fewer than four triangles, so it cannot enclose a solid")
    if not np.isfinite(triangles).all():
        raise ValueError(f"{path.name} contains non-numeric or infinite coordinates")
    return triangles


def _read_stl(path: Path):
    data = path.read_bytes()
    if len(data) >= 84:
        count = struct.unpack_from("<I", data, 80)[0]
        if 84 + 50 * count == len(data):
            records = np.frombuffer(data, dtype=np.dtype([("normal", "<f4", 3), ("corners", "<f4", (3, 3)), ("attribute", "<u2")]),
                                    count=count, offset=84)
            return records["corners"].astype(float)
    text = data.decode("ascii", errors="replace")
    if not text.lstrip().lower().startswith("solid"):
        raise ValueError(f"{path.name} is neither a valid binary STL nor an ASCII STL")
    values = re.findall(r"^\s*vertex\s+(\S+)\s+(\S+)\s+(\S+)", text, flags=re.MULTILINE | re.IGNORECASE)
    if len(values) % 3:
        raise ValueError(f"{path.name} has an incomplete ASCII STL facet")
    try:
        return np.array(values, dtype=float).reshape(-1, 3, 3)
    except ValueError as error:
        raise ValueError(f"{path.name} has a malformed ASCII STL vertex") from error


def _read_obj(path: Path):
    vertices, triangles = [], []
    for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        fields = line.partition("#")[0].split()
        if not fields:
            continue
        try:
            if fields[0] == "v":
                vertices.append([float(value) for value in fields[1:4]])
            elif fields[0] == "f":
                corners = []
                for field in fields[1:]:
                    index = int(field.split("/")[0])
                    resolved = index - 1 if index > 0 else len(vertices) + index
                    if index == 0 or not 0 <= resolved < len(vertices):
                        raise ValueError("vertex index is out of range")
                    corners.append(resolved)
                if len(corners) < 3:
                    raise ValueError
                if len(corners) > 3:
                    polygon = np.asarray([vertices[index] for index in corners], dtype=float)
                    extent = float(np.ptp(polygon, axis=0).max())
                    normal = np.cross(polygon, np.roll(polygon, -1, axis=0)).sum(axis=0)
                    length = np.linalg.norm(normal)
                    if length <= extent ** 2 * 1e-12:
                        raise ValueError("degenerate polygon; export triangulated OBJ")
                    normal /= length
                    edges = np.roll(polygon, -1, axis=0) - polygon
                    turns = np.cross(edges, np.roll(edges, -1, axis=0)) @ normal
                    if np.max(np.abs((polygon - polygon[0]) @ normal)) > extent * 1e-8 or np.any(turns < -extent ** 2 * 1e-12):
                        raise ValueError("concave or nonplanar polygon; export triangulated OBJ")
                # Fan triangulation is valid for the verified planar, convex polygon.
                for second in range(1, len(corners) - 1):
                    triangles.append([vertices[corners[0]], vertices[corners[second]], vertices[corners[second + 1]]])
        except (ValueError, IndexError) as error:
            raise ValueError(f"{path.name} line {number} is not a valid OBJ vertex or face: {error}") from error
    return triangles


def _read_3mf(path: Path):
    try:
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if name.lower().endswith(".model")]
            if not names:
                raise ValueError(f"{path.name} contains no 3D model part")
            primary = "3D/3dmodel.model" if "3D/3dmodel.model" in names else names[0]
            if "_rels/.rels" in archive.namelist():
                relationships = ElementTree.fromstring(archive.read("_rels/.rels"))
                targets = [item for item in relationships if item.get("Type", "").endswith("/3dmodel")]
                if len(targets) != 1 or targets[0].get("TargetMode") == "External":
                    raise ValueError(f"{path.name} needs one internal primary 3MF model")
                primary = posixpath.normpath(targets[0].get("Target", "").lstrip("/"))
                if primary.startswith("../") or primary not in names:
                    raise ValueError(f"{path.name} references a missing primary 3MF model")
            elif len(names) > 1:
                raise ValueError(f"{path.name} has multiple model parts without a primary-model relationship")
            root = ElementTree.fromstring(archive.read(primary))
    except zipfile.BadZipFile as error:
        raise ValueError(f"{path.name} is not a valid 3MF archive") from error
    namespace = root.tag[1:].split("}")[0] if root.tag.startswith("{") else ""
    unit = root.get("unit", "millimeter")
    if unit not in THREEMF_TO_MM:
        raise ValueError(f"{path.name} has an unsupported 3MF unit: {unit}")
    tag = (lambda name: f"{{{namespace}}}{name}") if namespace else (lambda name: name)
    objects = {}
    for item in root.iter(tag("object")):
        mesh = item.find(tag("mesh"))
        if item.find(tag("components")) is not None:
            raise ValueError(f"{path.name} uses 3MF components (grouped parts); export a single plain part instead")
        if mesh is None:
            continue
        vertices = np.array([[float(vertex.get(axis)) for axis in "xyz"] for vertex in mesh.iter(tag("vertex"))])
        faces = np.array([[int(triangle.get(key)) for key in ("v1", "v2", "v3")] for triangle in mesh.iter(tag("triangle"))])
        if len(vertices) and len(faces):
            if faces.min() < 0 or faces.max() >= len(vertices):
                raise ValueError(f"{path.name} has a triangle vertex index out of range")
            objects[item.get("id")] = vertices[faces]
    builds = list(root.iter(tag("item"))) or [None]
    triangles = []
    for build in builds:
        selected = objects.get(build.get("objectid")) if build is not None else next(iter(objects.values()), None)
        if selected is None:
            raise ValueError(f"{path.name} references a missing mesh object")
        transform = build.get("transform") if build is not None else None
        if transform:
            matrix = np.array([float(value) for value in transform.split()]).reshape(4, 3)
            selected = selected @ matrix[:3] + matrix[3]
        triangles.extend(selected)
    if not triangles:
        raise ValueError(f"{path.name} contains no triangle mesh")
    return np.asarray(triangles) * THREEMF_TO_MM[unit]


def clean_surface(triangles: np.ndarray, name="mesh", *, repair=False, report=None):
    """Verify a closed surface, optionally removing duplicate facets and repairing winding.

    No hole filling, surface smoothing or joining of separate shells is performed.
    The caller's triangle coordinates are never mutated. Report lengths use the
    caller's coordinate units (meters in the import pipeline).
    """
    size = float(np.ptp(triangles.reshape(-1, 3), axis=0).max())
    if size <= 0:
        raise ValueError(f"{name} has zero size")
    tolerance = size * 1e-9
    keys = np.round(triangles.reshape(-1, 3) / tolerance).astype(np.int64)
    unique, inverse = np.unique(keys, axis=0, return_inverse=True)
    points = np.zeros((len(unique), 3))
    np.add.at(points, inverse.ravel(), triangles.reshape(-1, 3))
    points /= np.bincount(inverse.ravel())[:, None]
    faces = inverse.reshape(-1, 3)
    faces = faces[(faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])]
    corners = points[faces]
    area = np.linalg.norm(np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]), axis=1) / 2
    faces = faces[area > size * size * 1e-14]
    if report is not None:
        report.update(input_triangles=len(triangles), removed_degenerate_triangles=len(triangles) - len(faces),
                      weld_tolerance_m=tolerance)
    _, unique_faces = np.unique(np.sort(faces, axis=1), axis=0, return_index=True)
    duplicates = len(faces) - len(unique_faces)
    if duplicates and not repair:
        raise ValueError(f"{name} has {duplicates} duplicated triangle(s). {REPAIR_HINT}")
    if duplicates:
        faces = faces[np.sort(unique_faces)]
    if report is not None:
        report["removed_duplicate_triangles"] = duplicates
    directed = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    undirected, edge_ids, counts = np.unique(np.sort(directed, axis=1), axis=0, return_inverse=True, return_counts=True)
    open_edges, shared = int(np.sum(counts == 1)), int(np.sum(counts > 2))
    if open_edges or shared:
        problems = ([f"{open_edges} open edge(s) (holes in the surface)"] if open_edges else []) + \
                   ([f"{shared} edge(s) shared by more than two triangles"] if shared else [])
        raise ValueError(f"{name} is not a single closed solid: it has " + " and ".join(problems) + f". {REPAIR_HINT}")
    _, directed_counts = np.unique(directed, axis=0, return_counts=True)
    if np.any(directed_counts > 1):
        if not repair:
            raise ValueError(f"{name} has inconsistently oriented (flipped) triangles. {REPAIR_HINT}")
        pairs = np.argsort(edge_ids).reshape(-1, 2)
        neighbors = [[] for _ in faces]
        for first, second in pairs:
            a, b = int(first % len(faces)), int(second % len(faces))
            flip = bool(directed[first, 0] == directed[second, 0])
            neighbors[a].append((b, flip))
            neighbors[b].append((a, flip))
        orientation = np.full(len(faces), -1, dtype=np.int8)
        for seed in range(len(faces)):
            if orientation[seed] != -1:
                continue
            orientation[seed] = 0
            pending = [seed]
            while pending:
                first = pending.pop()
                for second, flip in neighbors[first]:
                    expected = int(orientation[first]) ^ flip
                    if orientation[second] == -1:
                        orientation[second] = expected
                        pending.append(second)
                    elif orientation[second] != expected:
                        raise ValueError(f"{name} has a non-orientable surface; automatic repair cannot determine a solid")
        flipped = orientation == 1
        faces[flipped] = faces[flipped][:, [0, 2, 1]]
        if report is not None:
            report["reoriented_triangles"] = int(flipped.sum())
    parent = list(range(len(points)))
    def root(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node
    for first, second in undirected:
        parent[root(int(first))] = root(int(second))
    if len({root(int(node)) for node in np.unique(faces)}) != 1:
        raise ValueError(f"{name} has multiple disconnected surface shells. Export one connected closed shell; assemblies and enclosed cavity shells are not supported")
    corners = points[faces]
    volume = float(np.sum(np.einsum("ij,ij->i", corners[:, 0], np.cross(corners[:, 1], corners[:, 2]))) / 6)
    if abs(volume) <= size ** 3 * 1e-12:
        raise ValueError(f"{name} encloses no volume")
    if volume < 0:
        faces = faces[:, [0, 2, 1]]
    if report is not None:
        report.update(output_triangles=len(faces), reversed_inside_out_shell=volume < 0,
                      enclosed_volume_m3=abs(volume))
    return points, faces


def surface_intersection_pairs(points, faces, max_pairs=2_000_000, max_hits=20):
    """Find noncoplanar segment/facet intersections for failed-import diagnostics.

    Bounded sweep-and-prune search; an empty result is not a validity certificate.
    Coplanar overlaps and edge-sharing adjacent facets are outside this check.
    Returned indices refer to the cleaned triangle array, starting at zero.
    """
    triangles = points[faces]
    lower, upper = triangles.min(axis=1), triangles.max(axis=1)
    axis = int(np.ptp(points, axis=0).argmax())
    ordered = np.argsort(lower[:, axis], kind="stable")
    ends = np.searchsorted(lower[ordered, axis], upper[:, axis], side="right")
    tested, hits = 0, []
    for rank, first in enumerate(ordered):
        candidates = ordered[rank + 1:ends[first]]
        tested += len(candidates)
        if tested > max_pairs:
            break
        candidates = candidates[np.all(upper[candidates] >= lower[first], axis=1)
                                & np.all(lower[candidates] <= upper[first], axis=1)]
        shared = (faces[candidates, :, None] == faces[first, None, :]).sum(axis=(1, 2))
        candidates = candidates[shared < 2]
        if not len(candidates):
            continue
        found = np.zeros(len(candidates), dtype=bool)
        for a, b in ((0, 1), (1, 2), (2, 0)):
            for reverse in (False, True):
                targets = triangles[candidates] if not reverse else np.broadcast_to(triangles[first], (len(candidates), 3, 3))
                start = triangles[first, a] if not reverse else triangles[candidates, a]
                direction = triangles[first, b] - triangles[first, a] if not reverse else triangles[candidates, b] - triangles[candidates, a]
                edge1, edge2 = targets[:, 1] - targets[:, 0], targets[:, 2] - targets[:, 0]
                cross = np.cross(direction, edge2)
                det = np.einsum("ij,ij->i", edge1, cross)
                tolerance = 64 * np.finfo(float).eps * np.linalg.norm(edge1, axis=1) * np.linalg.norm(edge2, axis=1) * np.linalg.norm(direction, axis=-1)
                valid = np.abs(det) > tolerance
                inv = np.divide(1., det, out=np.zeros_like(det), where=valid)
                offset = start - targets[:, 0]
                u = np.einsum("ij,ij->i", offset, cross) * inv
                q = np.cross(offset, edge1)
                v = np.sum(direction * q, axis=1) * inv
                distance = np.einsum("ij,ij->i", edge2, q) * inv
                found |= valid & (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9) & (distance > 1e-8) & (distance < 1 - 1e-8)
        for second in candidates[found]:
            hits.append([int(first), int(second)])
            if len(hits) >= max_hits:
                return hits
    return hits


def write_binary_stl(path: Path, points: np.ndarray, faces: np.ndarray):
    corners = points[faces]
    normals = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    records = np.zeros(len(faces), dtype=np.dtype([("normal", "<f4", 3), ("corners", "<f4", (3, 3)), ("attribute", "<u2")]))
    records["normal"], records["corners"] = normals, corners
    with path.open("wb") as handle:
        handle.write(b"Doo Doo Dynamics cleaned surface".ljust(80, b" "))
        handle.write(struct.pack("<I", len(faces)))
        handle.write(records.tobytes())
