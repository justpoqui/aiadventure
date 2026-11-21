# Step 08 — World database and live persistence

**Goal:** the world lives in `world.sqlite` inside a **save slot**. Closing the
game and reopening it continues from exactly where you left off: same tick,
same positions.

**Model reminder:** the live slot *is* the save, because it is written
continuously. Checkpoints (step 11) are snapshots on top of it.

## 8.1 The world migration

Create `godot/sim/persistence/migrations/0001_init.sql` by copying the
`world.sqlite` schema from `docs/architecture/06-data-architecture.md §2`, with
the same change as in step 05: **delete the `CREATE TABLE schema_migrations`
line.**

**Rule for every world migration file:** each statement must end with `;` at
the end of a line, and no line *inside* a statement may end with `;`. Godot's
runner splits the file on that pattern (see `_split_statements` below).
Comments are fine.

## 8.2 WorldDB: the only code that touches world.sqlite

`godot/sim/persistence/world_db.gd`
```gdscript
class_name WorldDB
extends RefCounted
## The ONLY code allowed to touch world.sqlite.

const MIGRATIONS_DIR := "res://sim/persistence/migrations"

var _db: SQLite


func open(abs_path: String) -> void:
	_db = SQLite.new()
	_db.path = abs_path
	_db.foreign_keys = true
	_db.verbosity_level = SQLite.QUIET
	if not _db.open_db():
		push_error("WorldDB: cannot open %s: %s" % [abs_path, _db.error_message])
		return
	_db.query("PRAGMA journal_mode=WAL;")


func close() -> void:
	if _db != null:
		_db.close_db()
		_db = null


func migrate() -> int:
	_exec("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);")
	var applied := {}
	for row in _select("SELECT version FROM schema_migrations;"):
		applied[int(row["version"])] = true
	var files := Array(DirAccess.get_files_at(MIGRATIONS_DIR))
	files.sort()
	for f in files:
		if not f.ends_with(".sql"):
			continue
		var version := int(f.get_slice("_", 0))
		if applied.has(version):
			continue
		var sql := FileAccess.get_file_as_string(MIGRATIONS_DIR.path_join(f))
		_exec("BEGIN;")
		var ok := true
		for stmt in _split_statements(sql):
			if not _db.query(stmt):
				push_error("Migration %s failed: %s\n%s" % [f, _db.error_message, stmt.left(300)])
				ok = false
				break
		if ok:
			_db.query_with_bindings("INSERT INTO schema_migrations VALUES (?, ?);",
					[version, Time.get_datetime_string_from_system(true)])
			_exec("COMMIT;")
		else:
			_exec("ROLLBACK;")
			assert(false, "world migration %s failed" % f)
			break
	return schema_version()


func schema_version() -> int:
	var rows := _select("SELECT COALESCE(MAX(version), 0) AS v FROM schema_migrations;")
	return int(rows[0]["v"])


func get_meta_value(key: String, default_value: String = "") -> String:
	_db.query_with_bindings("SELECT value FROM world_meta WHERE key = ?;", [key])
	return default_value if _db.query_result.is_empty() else str(_db.query_result[0]["value"])


func set_meta_value(key: String, value: String) -> void:
	_db.query_with_bindings("INSERT INTO world_meta (key, value) VALUES (?, ?) "
			+ "ON CONFLICT(key) DO UPDATE SET value = excluded.value;", [key, value])


func load_entities() -> Array:
	return _select("SELECT entity_id, public_handle, type_id, x, y, z, state_json, created_tick FROM entities "
			+ "WHERE destroyed_tick IS NULL;")


func upsert_entity(e: SimEntity) -> void:
	var p := e.sim_position
	_db.query_with_bindings(
			"INSERT INTO entities (entity_id, public_handle, type_id, x, y, z, state_json, created_tick) "
			+ "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
			+ "ON CONFLICT(entity_id) DO UPDATE SET x = excluded.x, y = excluded.y, z = excluded.z, "
			+ "state_json = excluded.state_json;",
			[e.entity_id, e.public_handle, e.type_id, p.x, p.y, p.z, JSON.stringify(e.get_state()), e.created_tick])


func begin() -> void:
	_exec("BEGIN;")


func commit() -> void:
	_exec("COMMIT;")


## Consistent copy of the live database (safe while it is open).
func vacuum_into(abs_path: String) -> bool:
	return _db.query_with_bindings("VACUUM INTO ?;", [abs_path])


func _exec(sql: String) -> void:
	if not _db.query(sql):
		push_error("WorldDB: %s\n%s" % [_db.error_message, sql.left(300)])


func _select(sql: String) -> Array:
	_exec(sql)
	return _db.query_result.duplicate()


## Splits a migration file into statements. Rule for migration files:
## end every statement with ";" at the end of a line, and never put ";" at a line end inside a statement.
static func _split_statements(sql: String) -> PackedStringArray:
	var lines := PackedStringArray()
	for line in sql.replace("\r\n", "\n").split("\n"):
		if not line.strip_edges().begins_with("--"):
			lines.append(line)
	var out := PackedStringArray()
	for chunk in "\n".join(lines).split(";\n"):
		var stmt := chunk.strip_edges()
		if stmt != "":
			out.append(stmt if stmt.ends_with(";") else stmt + ";")
	return out
```

## 8.3 The real SaveManager

Replace the stub `autoload/save_manager.gd` with this. The checkpoint code is
explained in step 11. Until then, checkpoints fail safely, because the
MindBridge stub reports "not connected".

`godot/autoload/save_manager.gd`
```gdscript
extends Node
## Owns world.sqlite for the active save slot and runs coordinated checkpoints with the mind.
## The live slot IS the save (always persisted). A checkpoint is a consistent snapshot.

signal checkpoint_finished(label: String, ok: bool)

const FLUSH_EVERY_TICKS := 60          # write live state once per game hour
const START_TICK := 360                # a new world begins at 06:00 on day 1: "I survived the night."
const MIND_SAVE_TIMEOUT_MS := 30000

var slot: String = "default"
var slot_dir: String = ""              # user:// path
var world_seed: int = 0
var db: WorldDB

var _saved_rows: Dictionary = {}       # entity_id -> row, read once at startup
var _save_reply = null
var _busy := false


func _ready() -> void:
	var args := CmdArgs.all()
	slot = args.get("slot", "default")
	slot_dir = "user://saves/%s" % slot
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(slot_dir))
	_remove_partial_snapshots()
	if args.has("restore"):
		_restore_snapshot(args["restore"])
	db = WorldDB.new()
	db.open(ProjectSettings.globalize_path(slot_dir.path_join("world.sqlite")))
	db.migrate()
	world_seed = int(db.get_meta_value("world_seed", "0"))
	if world_seed == 0:
		randomize()
		world_seed = randi() | 1
		db.set_meta_value("world_seed", str(world_seed))
	SimClock.tick = int(db.get_meta_value("current_tick", str(START_TICK)))
	for row in db.load_entities():
		_saved_rows[row["entity_id"]] = row
	print("SaveManager: slot '%s' at tick %d (%s)" % [slot, SimClock.tick, ProjectSettings.globalize_path(slot_dir)])
	SimClock.ticked.connect(_on_tick)
	MindBridge.message.connect(_on_message)


## Called by every SimEntity in _ready. Returns false if the entity is new.
func restore_entity(e: SimEntity) -> bool:
	var row = _saved_rows.get(e.entity_id)
	if row == null:
		return false
	e.public_handle = row["public_handle"]
	e.created_tick = int(row["created_tick"])
	e.sim_position = Vector3(row["x"], row["y"], row["z"])
	var state = JSON.parse_string(str(row["state_json"]))
	e.apply_state(state if state is Dictionary else {})
	return true


## Writes the live state (tick + all entities) in one transaction.
func flush() -> void:
	db.begin()
	db.set_meta_value("current_tick", str(SimClock.tick))
	for e in WorldRegistry.all():
		db.upsert_entity(e)
	db.commit()


func close() -> void:
	if db != null:
		db.close()


func checkpoint(label: String) -> bool:
	if _busy:
		return false
	_busy = true
	var was_paused := SimClock.paused
	SimClock.paused = true
	flush()
	# Build into "<label>.partial" and only swap it in once complete,
	# so a failed checkpoint can never damage an older good snapshot.
	var final_dir := ProjectSettings.globalize_path(slot_dir.path_join("snapshots").path_join(label))
	var work := final_dir + ".partial"
	var ok := _prepare_empty_dir(work)
	var mind_sha := ""
	if ok:
		mind_sha = await _ask_mind_to_save(work)
		ok = mind_sha != ""
	if ok:
		ok = db.vacuum_into(work.path_join("world.sqlite"))
	if ok:
		ok = _write_manifest(work, label, mind_sha)   # a snapshot without a manifest is ignored
	if ok:
		ok = _swap_in(work, final_dir)
	SimClock.paused = was_paused
	_busy = false
	if ok:
		print("SaveManager: checkpoint '%s' saved at tick %d" % [label, SimClock.tick])
	else:
		push_error("SaveManager: checkpoint '%s' FAILED" % label)
	checkpoint_finished.emit(label, ok)
	return ok


func _on_tick(t: int) -> void:
	if t % SimClock.MINUTES_PER_DAY == 0:
		checkpoint("day_%04d" % SimClock.day())
	elif t % FLUSH_EVERY_TICKS == 0:
		flush()


func _on_message(env: Dictionary) -> void:
	if env.get("type") == "save_ready":
		_save_reply = env


## Returns the sha256 of the mind snapshot, or "" on failure.
func _ask_mind_to_save(snap: String) -> String:
	if not MindBridge.is_ready():
		push_error("SaveManager: mind service not connected")
		return ""
	_save_reply = null
	MindBridge.send("save_request", {"snapshot_dir": snap})
	var deadline := Time.get_ticks_msec() + MIND_SAVE_TIMEOUT_MS
	while _save_reply == null and Time.get_ticks_msec() < deadline:
		await get_tree().process_frame
	if _save_reply == null:
		push_error("SaveManager: mind did not answer save_request in time")
		return ""
	var claimed: String = _save_reply["payload"]["files"].get("mind.sqlite", "")
	var actual := FileAccess.get_sha256(snap.path_join("mind.sqlite"))
	if claimed == "" or claimed != actual:
		push_error("SaveManager: mind snapshot checksum mismatch")
		return ""
	return actual


func _write_manifest(snap: String, label: String, mind_sha: String) -> bool:
	var agents := []
	for e in WorldRegistry.all():
		if e is AgentBody:
			agents.append(e.agent_id)
	var manifest := {
		"format_version": 1,
		"slot": slot,
		"label": label,
		"updated_utc": Time.get_datetime_string_from_system(true),
		"tick": SimClock.tick,
		"day": SimClock.day(),
		"world_schema": db.schema_version(),
		"mind_schema": MindBridge.mind_schema,
		"protocol": MindBridge.PROTOCOL_VERSION,
		"world_seed": world_seed,
		"agents": agents,
		"checksums": {
			"world.sqlite": FileAccess.get_sha256(snap.path_join("world.sqlite")),
			"mind.sqlite": mind_sha,
		},
	}
	var tmp := snap.path_join("manifest.json.tmp")
	var f := FileAccess.open(tmp, FileAccess.WRITE)
	if f == null:
		return false
	f.store_string(JSON.stringify(manifest, "  "))
	f.close()
	return DirAccess.rename_absolute(tmp, snap.path_join("manifest.json")) == OK


## Leftovers from a crash or failed checkpoint. Never valid, always safe to delete.
func _remove_partial_snapshots() -> void:
	var snaps := ProjectSettings.globalize_path(slot_dir.path_join("snapshots"))
	if not DirAccess.dir_exists_absolute(snaps):
		return
	for d in DirAccess.get_directories_at(snaps):
		if d.ends_with(".partial"):
			_remove_dir(snaps.path_join(d))


func _swap_in(work: String, final_dir: String) -> bool:
	if DirAccess.dir_exists_absolute(final_dir):
		_remove_dir(final_dir)
	return DirAccess.rename_absolute(work, final_dir) == OK


func _remove_dir(abs_dir: String) -> void:
	for f in DirAccess.get_files_at(abs_dir):
		DirAccess.remove_absolute(abs_dir.path_join(f))
	DirAccess.remove_absolute(abs_dir)


func _prepare_empty_dir(abs_dir: String) -> bool:
	if DirAccess.dir_exists_absolute(abs_dir):
		_remove_dir(abs_dir)
	return DirAccess.make_dir_recursive_absolute(abs_dir) == OK


## Copies a snapshot over the live slot. Runs BEFORE any database is opened.
## Godot copies mind.sqlite as a file but never opens it.
func _restore_snapshot(label: String) -> void:
	var snap := ProjectSettings.globalize_path(slot_dir.path_join("snapshots").path_join(label))
	var manifest_path := snap.path_join("manifest.json")
	if not FileAccess.file_exists(manifest_path):
		push_error("Restore: '%s' has no manifest (incomplete snapshot). Not restoring." % label)
		return
	var manifest = JSON.parse_string(FileAccess.get_file_as_string(manifest_path))
	for file_name in ["world.sqlite", "mind.sqlite"]:
		if FileAccess.get_sha256(snap.path_join(file_name)) != manifest["checksums"][file_name]:
			push_error("Restore: checksum mismatch for %s. Not restoring." % file_name)
			return
	var live := ProjectSettings.globalize_path(slot_dir)
	for file_name in ["world.sqlite", "mind.sqlite"]:
		for suffix in ["", "-wal", "-shm"]:   # stale WAL files would corrupt the restored copy
			if FileAccess.file_exists(live.path_join(file_name + suffix)):
				DirAccess.remove_absolute(live.path_join(file_name + suffix))
		DirAccess.copy_absolute(snap.path_join(file_name), live.path_join(file_name))
	print("Restore: slot '%s' restored from '%s' (tick %d)" % [slot, label, int(manifest["tick"])])
```

How it fits together:
1. `SaveManager._ready` (an autoload, so it runs before any scene) opens the
   slot, migrates it, and loads the tick and all entity rows into memory.
2. Each `SimEntity._ready` calls `restore_entity()`. If a row exists, its
   position and handle come from the database. If not, the entity is new and
   takes its editor placement.
3. `flush()` writes everything in **one transaction**: once per game hour, at
   every checkpoint, and on quit.
4. On quit, `main.gd` **pauses the clock first**, then flushes. Otherwise ticks
   keep passing while it shuts down and the saved tick is stale. (That was a
   real bug found while testing this guide.)

## 8.4 Export note (for later)

When you eventually export the game, add `*.sql` to **Export → Resources →
Filters to export non-resource files**, or migrations will be missing from the
build.

## Check it works

1. Run the game. The output shows
   `SaveManager: slot 'default' at tick 360 (<path>)`. A new world starts at
   06:00 on day 1 (`START_TICK`): the survivor wakes having survived the
   night. Note the path.
2. Click to walk somewhere distinctive. Wait a few seconds. Close the window
   with the **X button**, not the editor's Stop button.
3. Run again. The output shows `… at tick N` with N > 360, and the body appears
   **where you left it**.
4. Open `<path>/world.sqlite` in a SQLite browser such as *DB Browser for
   SQLite* (read-only). `world_meta` has `world_seed` and `current_tick`;
   `entities` has `agent_a_0001` with an opaque handle like `e_3fa91c02`.
5. Try a different slot: run with `-- --slot=test` (Project → Project Settings
   → Editor → Run → Main Run Args, or from the terminal). This starts a fresh
   world at tick 360.

## Common mistakes

- **Stopping with the editor's Stop button.** That kills the process with no
  quit notification, so nothing after the last hourly flush is saved. Use the
  window's X (or `--quit-after` from the terminal).
- **Using `res://` paths for the database.** `res://` is read-only in exported
  games. Saves always go to `user://`.
- **Opening the live database in a DB browser while the game runs and writing
  to it.** Only ever read, and preferably only while the game is closed.
- **Windows line endings in the SQL file.** The runner normalises CRLF, but the
  `.gitattributes` from step 03 is the real protection.
