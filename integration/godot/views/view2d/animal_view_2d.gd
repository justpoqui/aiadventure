class_name AnimalView2D
extends Node2D
## Cosmetic: draws an Animal from its sprite sheet. The sprite faces north in the sheet and is
## rotated to the animal's heading; the soft shadow is NOT rotated (the sun stays north-west).

const SHADOW_OFFSET_M := Vector2(0.12, 0.16)    # toward the south-east, per metre of body size
static var _shadow_tex: Texture2D

var _animal: Animal
var _body := Sprite2D.new()
var _shadow := Sprite2D.new()
var _frames: Array = []
var _size_m := 1.0
var _anim_t := 0.0
var _alpha := 1.0


func configure(cfg: Dictionary, art_root: String, species: String) -> void:
	_frames = cfg["frames"]
	_size_m = float(cfg["size_m"]) * float(cfg["display_scale"])
	_body.texture = load(art_root.path_join(cfg["sheet"]))
	_body.hframes = _frames.size()
	_body.scale = Vector2.ONE * float(cfg["scale"]) * (SimUnits.PIXELS_PER_METRE / 32.0)
	_shadow.texture = _shadow_texture()
	var sh := _size_m * SimUnits.PIXELS_PER_METRE / 64.0
	_shadow.scale = Vector2(sh * 0.6, sh)
	_shadow.modulate = Color(0, 0, 0, 0.35)
	if species != "fish":
		add_child(_shadow)
	add_child(_body)


func _ready() -> void:
	_animal = get_parent() as Animal
	_animal.moved.connect(func(p): position = SimUnits.to_screen(p))
	position = SimUnits.to_screen(_animal.sim_position)


func _process(delta: float) -> void:
	var a := _animal
	# Frame: cycle movement frames while moving, otherwise the state's still frame.
	var name := a.frame_name
	if a.is_moving():
		var moving: Array = Animal.MOVE_FRAMES[a.species]
		_anim_t += delta * (6.0 if a.state == "flee" else 3.5)
		name = moving[int(_anim_t) % moving.size()]
	var idx := _frames.find(name)
	_body.frame = max(idx, 0)
	_body.rotation = a.heading
	_shadow.rotation = a.heading
	_shadow.position = SHADOW_OFFSET_M * _size_m * SimUnits.PIXELS_PER_METRE * (2.5 if a.elevated else 1.0)
	_shadow.visible = not a.hidden
	# Draw order: fish under the surface, birds above the canopy when up, others with agents.
	z_index = 1 if a.species == "fish" else (7 if a.elevated else 4)
	var target_alpha := 0.0 if a.hidden else (0.55 if a.species == "fish" else 1.0)
	_alpha = move_toward(_alpha, target_alpha, delta * 2.0)
	_body.modulate.a = _alpha


static func _shadow_texture() -> Texture2D:
	if _shadow_tex == null:
		var img := Image.create(64, 64, false, Image.FORMAT_RGBA8)
		for y in 64:
			for x in 64:
				var d := Vector2(x - 31.5, y - 31.5).length() / 32.0
				img.set_pixel(x, y, Color(1, 1, 1, clampf(1.0 - d, 0.0, 1.0) ** 1.6))
		_shadow_tex = ImageTexture.create_from_image(img)
	return _shadow_tex
