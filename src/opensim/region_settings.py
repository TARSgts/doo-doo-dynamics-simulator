import math


def validate_region(region):
    if region is None or region == {}:
        return
    if not isinstance(region, dict) or set(region) - {"faces", "box_m"}:
        raise ValueError("A region supports CAD face IDs and an optional box_m in meters")
    faces = region.get("faces", [])
    if not isinstance(faces, list) or any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in faces):
        raise ValueError("CAD face IDs must be positive integers")
    box = region.get("box_m")
    if box is not None:
        if (not isinstance(box, list) or len(box) != 6 or any(isinstance(value, bool) or not isinstance(value, (float, int))
                or not math.isfinite(value) for value in box) or any(box[index] >= box[index + 3] for index in range(3))):
            raise ValueError("box_m must contain finite xmin,ymin,zmin,xmax,ymax,zmax with positive spans")
    if not faces and box is None:
        raise ValueError("Select CAD face IDs or a coordinate box")
