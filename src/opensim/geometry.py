from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import gmsh
import numpy as np


@dataclass
class Mesh:
    points: np.ndarray
    tetrahedra: np.ndarray
    surface_groups: dict = field(default_factory=dict)

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
    if path.suffix.lower() not in {".step", ".stp", ".iges", ".igs", ".brep"}:
        raise ValueError("Supported CAD formats: STEP, IGES, BREP")
    if not path.is_file():
        raise FileNotFoundError(path)
    if not np.isfinite(size) or not np.isfinite(scale) or size <= 0 or scale <= 0:
        raise ValueError("Mesh size and CAD scale must be positive and finite")
    if order not in {1, 2}:
        raise ValueError("Element order must be 1 or 2")
    with gmsh_session():
        gmsh.model.add("solid")
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
