class_name WildlifeSystem
extends Node2D
## Spawns the animals from world_data/wildlife.json, coordinates herds, and relays animal
## sounds (birdsong, croaking) as world events that perception can pick up later.

signal animal_sound(animal: Animal, kind: String, position: Vector3)

var _groups: Dictionary = {}       # group id -> Array[Animal]


func populate(world_wildlife_json: String, species_json: String, art_root: String) -> void:
	var species = JSON.parse_string(FileAccess.get_file_as_string(species_json))["species"]
	var spawns = JSON.parse_string(FileAccess.get_file_as_string(world_wildlife_json))["animals"]
	for spec in spawns:
		var cfg: Dictionary = species[spec["species"]]
		var a := Animal.new()
		a.name = spec["id"]
		a.setup(spec, cfg, self)
		var view := AnimalView2D.new()
		view.name = "AnimalView"
		view.configure(cfg, art_root, spec["species"])
		a.add_child(view)
		a.sound.connect(func(animal, kind): animal_sound.emit(animal, kind, animal.sim_position))
		add_child(a)
		if a.group != "":
			if not _groups.has(a.group):
				_groups[a.group] = []
			_groups[a.group].append(a)
	print("Wildlife: %d animals" % spawns.size())


func alarm(source: Animal, threat: Node) -> void:
	for a in _groups.get(source.group, []):
		if a != source and a.sim_position.distance_to(source.sim_position) < 30.0:
			a.on_alarm(threat)


func leader_of(a: Animal) -> Animal:
	return _groups[a.group][0] if _groups.has(a.group) else a
