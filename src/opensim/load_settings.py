LOAD_KINDS = ("face", "point", "traction")
LOAD_AXES = ("x", "y", "z", "normal-in", "normal-out")
NORMAL_AXES = ("normal-in", "normal-out")
LOAD_SURFACES = tuple(f"{axis}-{side}" for axis in "xyz" for side in ("min", "max"))
