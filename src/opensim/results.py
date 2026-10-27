import json
from pathlib import Path
import uuid

import numpy as np

from opensim.geometry import Mesh


def write_vtk(path: Path, mesh: Mesh, displacement: np.ndarray, quantity="displacement_m", stress=None):
    lines = ["# vtk DataFile Version 3.0", "Open simulation SI results", "ASCII",
             "DATASET UNSTRUCTURED_GRID", f"POINTS {len(mesh.points)} double"]
    lines.extend(" ".join(f"{value:.15g}" for value in point) for point in mesh.points)
    width = mesh.tetrahedra.shape[1]
    lines.append(f"CELLS {len(mesh.tetrahedra)} {len(mesh.tetrahedra) * (width + 1)}")
    lines.extend(f"{width} " + " ".join(str(int(node)) for node in element) for element in mesh.tetrahedra)
    lines.append(f"CELL_TYPES {len(mesh.tetrahedra)}")
    lines.extend("24" if width == 10 else "10" for _ in mesh.tetrahedra)
    lines.extend([f"POINT_DATA {len(mesh.points)}", f"VECTORS {quantity} double"])
    lines.extend(" ".join(f"{value:.15g}" for value in vector) for vector in displacement)
    magnitude = "displacement_magnitude_m" if quantity == "displacement_m" else quantity + "_magnitude"
    lines.extend([f"SCALARS {magnitude} double 1", "LOOKUP_TABLE default"])
    lines.extend(f"{value:.15g}" for value in np.linalg.norm(displacement, axis=1))
    if stress is not None:
        lines.extend(["SCALARS von_mises_Pa double 1", "LOOKUP_TABLE default"])
        lines.extend(f"{value:.15g}" for value in stress)
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def write_viewer(path: Path, mesh: Mesh, displacement: np.ndarray, summary: dict, stress=None):
    data = {"points": mesh.points.tolist(), "faces": mesh.boundary_faces(),
            "displacement": displacement.tolist(), "summary": summary}
    if stress is not None:
        data["von_mises_Pa"] = stress.tolist()
    write_viewer_data(path, data)


def write_viewer_data(path: Path, data: dict):
    template = Path(__file__).with_name("viewer.html").read_text(encoding="utf-8")
    script = Path(__file__).with_name("viewport.js").read_text(encoding="utf-8")
    document = template.replace("__VIEWPORT_CODE__", script).replace("__SIMULATION_DATA__", json.dumps(data, allow_nan=False))
    path.write_text(document, encoding="utf-8")


def refresh_viewer(source: Path, destination: Path):
    document = source.read_text(encoding="utf-8")
    marker = "const simulation = "
    start = document.find(marker)
    if start < 0:
        raise ValueError("Saved viewer does not contain simulation data")
    data, _ = json.JSONDecoder().raw_decode(document[start + len(marker):])
    if not {"points", "faces", "displacement", "summary"}.issubset(data):
        raise ValueError("Saved viewer data is incomplete")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        write_viewer_data(temporary, data)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
