class_name SimUnits
## The ONLY place where metres and pixels meet.
## Sim space: x = east, z = south, y = up (elevation). Screen: x right, y down.

const PIXELS_PER_METRE := 32.0   # 64 px tiles = 2 m


static func to_screen(p: Vector3) -> Vector2:
	return Vector2(p.x, p.z) * PIXELS_PER_METRE


static func to_sim(v: Vector2, elevation: float = 0.0) -> Vector3:
	return Vector3(v.x / PIXELS_PER_METRE, elevation, v.y / PIXELS_PER_METRE)
