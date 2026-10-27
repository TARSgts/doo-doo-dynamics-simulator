import json
from pathlib import Path

import numpy as np

from opensim.geometry import Mesh


def write_vtk(path: Path, mesh: Mesh, displacement: np.ndarray):
    lines = ["# vtk DataFile Version 3.0", "Open simulation SI results", "ASCII",
             "DATASET UNSTRUCTURED_GRID", f"POINTS {len(mesh.points)} double"]
    lines.extend(" ".join(f"{value:.15g}" for value in point) for point in mesh.points)
    width = mesh.tetrahedra.shape[1]
    lines.append(f"CELLS {len(mesh.tetrahedra)} {len(mesh.tetrahedra) * (width + 1)}")
    lines.extend(f"{width} " + " ".join(str(int(node)) for node in element) for element in mesh.tetrahedra)
    lines.append(f"CELL_TYPES {len(mesh.tetrahedra)}")
    lines.extend("24" if width == 10 else "10" for _ in mesh.tetrahedra)
    lines.extend([f"POINT_DATA {len(mesh.points)}", "VECTORS displacement_m double"])
    lines.extend(" ".join(f"{value:.15g}" for value in vector) for vector in displacement)
    lines.extend(["SCALARS displacement_magnitude_m double 1", "LOOKUP_TABLE default"])
    lines.extend(f"{value:.15g}" for value in np.linalg.norm(displacement, axis=1))
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def write_viewer(path: Path, mesh: Mesh, displacement: np.ndarray, summary: dict):
    template = Path(__file__).with_name("viewer.html").read_text(encoding="utf-8")
    data = {"points": mesh.points.tolist(), "faces": mesh.boundary_faces(),
            "displacement": displacement.tolist(), "summary": summary}
    path.write_text(template.replace("__SIMULATION_DATA__", json.dumps(data, allow_nan=False)), encoding="utf-8")
