LOAD_KINDS = ("face", "point", "traction")
LOAD_SURFACES = tuple(f"{axis}-{side}" for axis in "xyz" for side in ("min", "max"))
