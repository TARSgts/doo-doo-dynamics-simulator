from pathlib import Path
import numpy as np


def read_stress(path: Path, node_count: int):
    values, components = {}, []
    active, completed = False, False
    for line in path.read_text(encoding="ascii", errors="strict").splitlines():
        if line.startswith(" -4"):
            active = line.split()[1] == "STRESS"
            continue
        if not active:
            continue
        if line.startswith(" -5"):
            components.append(line.split()[1])
        elif line.startswith(" -1"):
            node = int(line[3:13])
            if node in values:
                raise ValueError("Duplicate nodal stress result")
            values[node] = [float(line[start:start + 12].replace("D", "E")) for start in range(13, len(line.rstrip()), 12)]
        elif line.startswith(" -3"):
            completed = True
            break
    if not completed or components[:6] != ["SXX", "SYY", "SZZ", "SXY", "SYZ", "SZX"] or set(values) != set(range(1, node_count + 1)):
        raise ValueError("Incomplete or unsupported FRD stress block")
    stress = np.array([values[node][:6] for node in range(1, node_count + 1)])
    if stress.shape != (node_count, 6) or not np.isfinite(stress).all():
        raise ValueError("Invalid nodal stress values")
    return stress


def von_mises(stress):
    normal = ((stress[:, 0] - stress[:, 1]) ** 2 + (stress[:, 1] - stress[:, 2]) ** 2 + (stress[:, 2] - stress[:, 0]) ** 2) / 2
    return np.sqrt(normal + 3 * np.sum(stress[:, 3:] ** 2, axis=1))
