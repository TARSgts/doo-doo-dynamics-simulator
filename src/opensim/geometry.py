from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import gmsh
import numpy as np


@dataclass
class Mesh:
    points: np.ndarray
    tetrahedra: np.ndarray

    def end_nodes(self, side: str) -> np.ndarray:
        position = self.points[:, 0]
        extent = float(np.ptp(position))
        if extent <= 0:
            raise ValueError("Solid must have a nonzero X extent")
        target = position.min() if side == "min" else position.max()
        return np.flatnonzero(np.abs(position - target) <= extent * 1e-7)

    def boundary_faces(self) -> list[list[int]]:
        faces = {}
        for tetrahedron in self.tetrahedra:
            for indices in ((0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3)):
                face = tuple(sorted(int(tetrahedron[index]) for index in indices))
                faces[face] = faces.get(face, 0) + 1
        return [list(face) for face, count in faces.items() if count == 1]


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


def import_and_mesh(path: Path, size: float, scale: float, output: Path) -> Mesh:
    if path.suffix.lower() not in {".step", ".stp", ".iges", ".igs", ".brep"}:
        raise ValueError("Supported CAD formats: STEP, IGES, BREP")
    if not path.is_file():
        raise FileNotFoundError(path)
    if not np.isfinite(size) or not np.isfinite(scale) or size <= 0 or scale <= 0:
        raise ValueError("Mesh size and CAD scale must be positive and finite")
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
        gmsh.option.setNumber("Mesh.MeshSizeMin", size)
        gmsh.option.setNumber("Mesh.MeshSizeMax", size)
        gmsh.option.setNumber("Mesh.ElementOrder", 1)
        gmsh.option.setNumber("General.NumThreads", 1)
        gmsh.model.mesh.generate(3)
        tags, coordinates, _ = gmsh.model.mesh.getNodes()
        node_map = {int(tag): index for index, tag in enumerate(tags)}
        element_types, _, connectivity = gmsh.model.mesh.getElements(3)
        if list(element_types) != [4]:
            raise ValueError("Only linear four-node tetrahedra are supported")
        tetrahedra = np.array([
            [node_map[int(tag)] for tag in group]
            for group in connectivity[0].reshape(-1, 4)
        ], dtype=int)
        points = np.asarray(coordinates).reshape(-1, 3)
        corners = points[tetrahedra]
        determinants = np.linalg.det(corners[:, 1:] - corners[:, :1])
        if len(tetrahedra) == 0 or np.any(determinants <= 0):
            raise ValueError("Mesh contains empty, inverted or degenerate tetrahedra")
        gmsh.write(str(output.resolve()))
        return Mesh(points, tetrahedra)
