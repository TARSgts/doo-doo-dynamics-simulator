import os
from pathlib import Path
import shutil
import subprocess

import numpy as np

from opensim.geometry import Mesh


def find_solver(explicit: str | None = None) -> Path:
    selected = explicit or os.environ.get("CCX_EXECUTABLE") or shutil.which("ccx")
    if selected:
        resolved = Path(selected).expanduser().resolve()
        if resolved.is_file():
            return resolved
        raise FileNotFoundError(f"CalculiX executable does not exist: {resolved}")
    project = Path(__file__).resolve().parents[2]
    static = project / ".tools" / "calculix" / "calculix_2.23_4win" / "ccx_static.exe"
    if static.is_file():
        return static.resolve()
    candidates = sorted((project / ".tools" / "calculix").rglob("ccx*.exe"))
    if len(candidates) == 1:
        return candidates[0].resolve()
    raise FileNotFoundError("Set CCX_EXECUTABLE to a trusted CalculiX ccx executable")


def write_deck(mesh: Mesh, path: Path, young: float, poisson: float, load: float):
    if not np.isfinite(young) or young <= 0:
        raise ValueError("Young's modulus must be positive and finite")
    if not np.isfinite(poisson) or not -1 < poisson < 0.5:
        raise ValueError("Poisson ratio must be between -1 and 0.5, exclusive")
    if not np.isfinite(load) or load == 0:
        raise ValueError("Axial load must be nonzero and finite")
    fixed = mesh.end_nodes("min")
    loaded = mesh.end_nodes("max")
    for nodes in (fixed, loaded):
        if len(nodes) < 3 or np.linalg.matrix_rank(mesh.points[nodes] - mesh.points[nodes[0]]) < 2:
            raise ValueError("Each X end must contain a planar face with at least three noncollinear nodes")
    lines = ["*HEADING", "Independent open-simulation axial load", "*NODE, NSET=NALL"]
    lines.extend(f"{index + 1}, " + ", ".join(f"{value:.15g}" for value in point)
                 for index, point in enumerate(mesh.points))
    lines.append("*ELEMENT, TYPE=C3D4, ELSET=SOLID")
    lines.extend(f"{index + 1}, " + ", ".join(str(int(node) + 1) for node in element)
                 for index, element in enumerate(mesh.tetrahedra))
    lines.append("*NSET, NSET=FIX")
    lines.extend(str(int(node) + 1) for node in fixed)
    lines.extend(["*MATERIAL, NAME=ELASTIC", "*ELASTIC", f"{young:.15g}, {poisson:.15g}",
                  "*SOLID SECTION, ELSET=SOLID, MATERIAL=ELASTIC", "*BOUNDARY", "FIX, 1, 3, 0",
                  "*STEP", "*STATIC, SOLVER=SPOOLES", "*CLOAD"])
    lines.extend(f"{int(node) + 1}, 1, {load / len(loaded):.15g}" for node in loaded)
    lines.extend(["*NODE PRINT, NSET=NALL", "U", "*NODE PRINT, NSET=FIX", "RF",
                  "*NODE FILE", "U", "*EL FILE", "S", "*END STEP"])
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def run_solver(executable: Path, directory: Path, timeout: float = 120):
    environment = os.environ.copy()
    environment["OMP_NUM_THREADS"] = "1"
    environment["NUMBER_OF_CPUS"] = "1"
    try:
        completed = subprocess.run([str(executable), "-i", "model"], cwd=directory,
                                   capture_output=True, text=True, errors="replace",
                                   timeout=timeout, env=environment, shell=False,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    except subprocess.TimeoutExpired as error:
        (directory / "solver.log").write_text(str(error), encoding="utf-8")
        raise RuntimeError(f"CalculiX exceeded {timeout} seconds") from error
    log = completed.stdout + completed.stderr
    (directory / "solver.log").write_text(log, encoding="utf-8")
    if completed.returncode != 0 or "*ERROR" in log.upper() or "JOB FINISHED" not in log.upper():
        raise RuntimeError(f"CalculiX did not finish successfully; inspect {directory / 'solver.log'}")


def parse_dat(path: Path, node_count: int) -> tuple[np.ndarray, dict[int, list[float]]]:
    displacement = {}
    reactions = {}
    destination = None
    for line in path.read_text(encoding="ascii", errors="replace").splitlines():
        lower = line.lower()
        if "displacements" in lower:
            destination = displacement
            continue
        if "forces" in lower:
            destination = reactions
            continue
        fields = line.split()
        if destination is not None and len(fields) == 4 and fields[0].isdigit():
            try:
                values = [float(value.replace("D", "E")) for value in fields[1:]]
            except ValueError:
                continue
            node = int(fields[0])
            if node in destination:
                raise ValueError("Multiple result blocks are unsupported in Stage 1")
            destination[node] = values
    if set(displacement) != set(range(1, node_count + 1)):
        raise ValueError("CalculiX displacement results are incomplete")
    vectors = np.array([displacement[node] for node in range(1, node_count + 1)])
    if not np.isfinite(vectors).all() or not reactions or not np.isfinite(list(reactions.values())).all():
        raise ValueError("Missing or nonfinite CalculiX results")
    return vectors, reactions
