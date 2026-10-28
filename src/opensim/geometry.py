from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import math
import json
import tempfile

import gmsh
import numpy as np

from opensim.mesh_import import MESH_SUFFIXES, clean_surface, read_triangles, write_binary_stl
from opensim.file_formats import CAD_SUFFIXES, SUPPORTED_SUFFIXES

FACE_PATCH_ANGLE_DEG = 40


class MeshElementLimitExceeded(ValueError):
    pass


@dataclass
class Mesh:
    points: np.ndarray
    tetrahedra: np.ndarray
    surface_groups: dict = field(default_factory=dict)
    repair_report: dict = field(default_factory=dict)

    @property
    def element_type(self) -> str:
        return "C3D10" if self.tetrahedra.shape[1] == 10 else "C3D4"

    def tip_node(self) -> int:
        target = (self.points.min(axis=0) + self.points.max(axis=0)) / 2
        target[0] = self.points[:, 0].max()
        distances = np.linalg.norm(self.points - target, axis=1)
        index = int(distances.argmin())
        if distances[index] > np.ptp(self.points[:, 0]) * 1e-7:
            raise ValueError("Tip point load requires a node at the X-max face center")
        return index

    def end_nodes(self, side: str) -> np.ndarray:
        position = self.points[:, 0]
        extent = float(np.ptp(position))
        if extent <= 0:
            raise ValueError("Solid must have a nonzero X extent")
        target = position.min() if side == "min" else position.max()
        return np.flatnonzero(np.abs(position - target) <= extent * 1e-7)

    def boundary_elements(self) -> list[list[int]]:
        faces = {}
        edges = {(0, 1): 4, (1, 2): 5, (0, 2): 6, (0, 3): 7, (1, 3): 8, (2, 3): 9}
        for tetrahedron in self.tetrahedra:
            for indices in ((0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3)):
                face = tuple(sorted(int(tetrahedron[index]) for index in indices))
                nodes = [int(tetrahedron[index]) for index in indices]
                if self.element_type == "C3D10":
                    nodes += [int(tetrahedron[edges[tuple(sorted(pair))]]) for pair in
                              ((indices[0], indices[1]), (indices[1], indices[2]), (indices[0], indices[2]))]
                count, _ = faces.get(face, (0, nodes))
                faces[face] = count + 1, nodes
        return [nodes for count, nodes in faces.values() if count == 1]

    def boundary_faces(self) -> list[list[int]]:
        triangles = []
        for face in self.boundary_elements():
            if len(face) == 3:
                triangles.append(face)
            else:
                triangles.extend([[face[index] for index in indices] for indices in
                                  ((0, 3, 5), (3, 1, 4), (5, 4, 2), (3, 4, 5))])
        return triangles

    def boundary_face_ids(self) -> list[int]:
        """CAD face tag for each rendered triangle, including quadratic subdivisions."""
        tags = {tuple(sorted(face[:3])): int(tag)
                for tag, faces in self.surface_groups.items() for face in faces}
        result = []
        for face in self.boundary_elements():
            result.extend([tags.get(tuple(sorted(face[:3])), 0)] * (4 if len(face) == 6 else 1))
        return result

    def tip_average(self, values: np.ndarray) -> np.ndarray:
        target = self.points[:, 0].max()
        tolerance = np.ptp(self.points[:, 0]) * 1e-7
        integrated = np.zeros(values.shape[1])
        area_sum = 0.0
        for face in self.boundary_elements():
            if np.any(np.abs(self.points[face, 0] - target) > tolerance):
                continue
            corners = self.points[face[:3]]
            area = np.linalg.norm(np.cross(corners[1] - corners[0], corners[2] - corners[0])) / 2
            integrated += area * values[face[3:] if len(face) == 6 else face].mean(axis=0)
            area_sum += area
        if area_sum <= 0:
            raise ValueError("No planar tip surface available for area averaging")
        return integrated / area_sum

    def surface_catalog(self):
        result = []
        for tag, faces in self.surface_groups.items():
            corners = self.points[np.asarray(faces, dtype=int)[:, :3]]
            areas = np.linalg.norm(np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]), axis=1) / 2
            area = float(areas.sum())
            if area > 0:
                result.append({"id": int(tag), "triangles": len(faces), "area_m2": area,
                               "centroid_m": (np.sum(corners.mean(axis=1) * areas[:, None], axis=0) / area).tolist()})
        return result


@contextmanager
def gmsh_session():
    gmsh.initialize([], readConfigFiles=False)
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        yield
    finally:
        gmsh.finalize()


def make_box(path: Path, dimensions=(1.0, 0.1, 0.1)):
    if any(not np.isfinite(value) or value <= 0 for value in dimensions):
        raise ValueError("Box dimensions must be positive and finite")
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with gmsh_session():
        gmsh.model.add("axial_bar")
        gmsh.model.occ.addBox(0, 0, 0, *dimensions)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path.resolve()))


def import_and_mesh(path: Path, size: float, scale: float, output: Path, order=1, tip_point=False) -> Mesh:
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError("Supported CAD formats: STEP, IGES, BREP, STL, OBJ, 3MF")
    if not path.is_file():
        raise FileNotFoundError(path)
    if not np.isfinite(size) or not np.isfinite(scale) or size <= 0 or scale <= 0:
        raise ValueError("Mesh size and CAD scale must be positive and finite")
    if order not in {1, 2}:
        raise ValueError("Element order must be 1 or 2")
    surface_mesh = path.suffix.lower() in MESH_SUFFIXES
    if surface_mesh and tip_point:
        raise ValueError("A tip-center point load needs exact CAD (STEP, IGES or BREP). For STL/OBJ/3MF parts, "
                         "use uniform surface traction on picked faces or the end-face load")
    if surface_mesh:
        repair_report = {"source_unchanged": True, "status": "preparing", "attempts": []}
        try:
            points, faces = clean_surface(read_triangles(path) * scale, path.name, repair=True, report=repair_report)
        except ValueError as error:
            repair_report.update(status="failed", error=str(error))
            _write_repair_report(output, repair_report)
            raise
    with gmsh_session(), tempfile.TemporaryDirectory() as scratch:
        gmsh.model.add("solid")
        if surface_mesh:
            try:
                _rebuild_solid_from_surface(points, faces, Path(scratch) / "surface.stl", size, repair_report)
                mesh = _mesh_volume(size, order, output)
                repair_report["status"] = "completed"
                mesh.repair_report = repair_report
                return mesh
            except Exception as error:
                repair_report.update(status="failed", error=str(error))
                raise
            finally:
                _write_repair_report(output, repair_report)
        gmsh.model.occ.importShapes(str(path.resolve()))
        gmsh.model.occ.synchronize()
        volumes = gmsh.model.getEntities(3)
        if not volumes and path.suffix.lower() in {".iges", ".igs"}:
            gmsh.model.occ.healShapes(tolerance=1e-8, sewFaces=True, makeSolids=True)
            gmsh.model.occ.synchronize()
            volumes = gmsh.model.getEntities(3)
        if len(volumes) != 1:
            raise ValueError("Stage 1 requires exactly one closed solid")
        gmsh.model.occ.dilate(volumes, 0, 0, 0, scale, scale, scale)
        gmsh.model.occ.synchronize()
        if tip_point:
            bounds = gmsh.model.getBoundingBox(3, volumes[0][1])
            target = [(bounds[index] + bounds[index + 3]) / 2 for index in range(3)]
            target[0] = bounds[3] - 1e-7
            end_faces = []
            for _, face in gmsh.model.getEntities(2):
                closest, _ = gmsh.model.getClosestPoint(2, face, target)
                if np.linalg.norm(np.asarray(closest) - target) < 1e-6 and gmsh.model.isInside(2, face, closest):
                    end_faces.append((face, closest))
            if len(end_faces) != 1:
                raise ValueError("Tip point requires a planar end face containing the section center")
            face, location = end_faces[0]
            point = gmsh.model.occ.addPoint(*location)
            gmsh.model.occ.synchronize()
            gmsh.model.mesh.embed(0, [point], 2, face)
        return _mesh_volume(size, order, output)


def _write_repair_report(output, report):
    path = Path(output).with_suffix(".repair.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")


def _rebuild_solid_from_surface(points, faces, stl_path: Path, size: float, report=None):
    """Split a closed triangle surface into smooth face patches and close them into one volume.

    Each patch becomes a pickable "face" (edges sharper than FACE_PATCH_ANGLE_DEG separate patches),
    and the patches are remeshed at the requested size so element quality does not depend on the
    triangles the exporter happened to write.
    """
    write_binary_stl(stl_path, points, faces)
    for attempt, angle in enumerate((FACE_PATCH_ANGLE_DEG, 25, 10)):
        if attempt:
            # Discard partially created geometry, then retry from the same cleaned
            # triangles. Smaller patches change partitioning, not model shape.
            gmsh.clear()
            gmsh.model.add("solid")
        gmsh.merge(str(stl_path))
        try:
            gmsh.model.mesh.classifySurfaces(math.radians(angle), True, True, math.pi if not attempt else math.pi / 2)
            gmsh.model.mesh.createGeometry()
            surfaces = [tag for _, tag in gmsh.model.getEntities(2)]
            loop = gmsh.model.geo.addSurfaceLoop(surfaces)
            gmsh.model.geo.addVolume([loop])
            gmsh.model.geo.synchronize()
            if len(gmsh.model.getEntities(3)) != 1:
                raise ValueError("The surface mesh did not form exactly one closed solid")
            if report is not None:
                report["attempts"].append({"patch_angle_degrees": angle, "status": "completed"})
                report["patch_retry_used"] = bool(attempt)
            return
        except Exception as error:
            if report is not None:
                report["attempts"].append({"patch_angle_degrees": angle, "status": "failed", "error": str(error)})
            last_error = error
    raise ValueError(f"Automatic surface repair could not create meshable face patches after 3 attempts ({last_error}). "
                     "Export STEP from the original CAD, or repair the mesh in your modeling tool and re-import it") from last_error


def _mesh_volume(size, order, output: Path) -> "Mesh":
    gmsh.option.setNumber("Mesh.MeshSizeMin", size)
    gmsh.option.setNumber("Mesh.MeshSizeMax", size)
    gmsh.option.setNumber("Mesh.ElementOrder", order)
    gmsh.option.setNumber("Mesh.SecondOrderLinear", 1)
    gmsh.option.setNumber("General.NumThreads", 1)
    gmsh.model.mesh.generate(3)
    tags, coordinates, _ = gmsh.model.mesh.getNodes()
    node_map = {int(tag): index for index, tag in enumerate(tags)}
    element_types, _, connectivity = gmsh.model.mesh.getElements(3)
    if list(element_types) != [4 if order == 1 else 11]:
        raise ValueError("Expected a homogeneous tetrahedral mesh")
    tetrahedra = np.array([
        [node_map[int(tag)] for tag in group]
        for group in connectivity[0].reshape(-1, 4 if order == 1 else 10)
    ], dtype=int)
    if order == 2:
        tetrahedra[:, [8, 9]] = tetrahedra[:, [9, 8]]
    points = np.asarray(coordinates).reshape(-1, 3)
    used = np.unique(tetrahedra)
    if len(used) != len(points):
        # Surface-mesh imports can leave nodes from the original triangles that no element uses;
        # unconnected nodes would make the stiffness matrix singular, so renumber to used nodes only.
        renumber = np.full(len(points), -1)
        renumber[used] = np.arange(len(used))
        points, tetrahedra = points[used], renumber[tetrahedra]
        node_map = {tag: int(renumber[index]) for tag, index in node_map.items() if renumber[index] >= 0}
    corners = points[tetrahedra[:, :4]]
    determinants = np.linalg.det(corners[:, 1:] - corners[:, :1])
    if len(tetrahedra) == 0 or np.any(determinants <= 0):
        raise ValueError("Mesh contains empty, inverted or degenerate tetrahedra")
    gmsh.write(str(output.resolve()))
    surface_groups = {}
    for _, tag in gmsh.model.getEntities(2):
        surface_types, _, surface_connectivity = gmsh.model.mesh.getElements(2, tag)
        faces = []
        for element_type, records in zip(surface_types, surface_connectivity):
            width = {2: 3, 9: 6}.get(int(element_type))
            if width is None:
                raise ValueError("Unsupported surface mesh element")
            faces.extend([[node_map[int(node)] for node in row] for row in records.reshape(-1, width)])
        surface_groups[str(tag)] = faces
    return Mesh(points, tetrahedra, surface_groups)
