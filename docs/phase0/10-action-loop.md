# Step 10 — Action loop with the stand-in mind

**Goal:** the mind service commands the body. The body executes one primitive
action at a time and reports each result back, so the loop runs on its own.

```
mind: action_command(move_to)  →  Godot: action_update(started)
                                  … body walks …
                               ←  action_update(completed, percepts:[arrived])
mind: next action_command      →  …
```

## 10.1 ActionRunner

`godot/entities/agent/action_runner.gd`
```gdscript
extends Node
## Executes ONE primitive action at a time for this body, as commanded by the mind,
## and reports the outcome back. Outcomes are resolved against world truth here.

var _current := ""   # action_id in progress

@onready var _body: AgentBody = get_parent()
@onready var _loco: Locomotion = $"../Locomotion"


func _ready() -> void:
	MindBridge.message.connect(_on_message)
	MindBridge.connected.connect(_announce)
	_loco.arrived.connect(func(): _finish("completed"))
	_loco.failed.connect(func(reason: String): _finish("failed", reason))


func _announce() -> void:
	if Spatial.nav == null:
		await Spatial.nav_ready
	var p := _body.sim_position
	MindBridge.send("agent_spawned", {"agent_id": _body.agent_id,
			"position": {"x": p.x, "y": p.y, "z": p.z}}, _body.agent_id)


func _on_message(env: Dictionary) -> void:
	if env.get("type") != "action_command" or env.get("agent_id") != _body.agent_id:
		return
	var cmd: Dictionary = env["payload"]
	if _current != "":
		_loco.stop()
		_finish("interrupted", "superseded")
	_current = cmd["action_id"]
	MindBridge.send("action_update", {"action_id": _current, "status": "started"}, _body.agent_id)
	match cmd["action_type"]:
		"move_to":
			var t: Dictionary = cmd["params"]["target"]
			_loco.move_to(Vector3(t["x"], t.get("y", 0.0), t["z"]))
		_:
			_finish("failed", "unknown_action")


func _finish(status: String, reason: String = "") -> void:
	if _current == "":
		return
	var payload := {"action_id": _current, "status": status}
	if reason != "":
		payload["reason"] = reason
	if status == "completed":
		payload["percepts"] = [{"modality": "proprioception", "event": "arrived"}]
	_current = ""
	MindBridge.send("action_update", payload, _body.agent_id)
```

Add it to `agent_body.tscn`:
```
AgentBody (Node)
├── Locomotion (Node)
├── ActionRunner (Node)     script: entities/agent/action_runner.gd   ← new
└── View2D (Node2D)
    └── Sprite2D
```

Notes:
- `agent_spawned` is sent only after **both** the handshake and the navigation
  map are ready, so the first command can't fail because the map isn't ready.
- A new command **interrupts** the current one, which is reported as
  `interrupted` / `superseded`. One body, one action.
- The outcome is reported as a **percept** (`proprioception: arrived`), not as
  a fact. Phase 1 builds on exactly this shape.

## 10.2 Remove the developer click tool

Delete the `DevClickToWalk` node from `main.tscn` and the file
`dev/dev_click_to_walk.gd`. From now on **only the mind moves the body.**

## Check it works

Start the mind service, then run the game.

1. Within a second the body starts walking a rectangle: (20,0) → (20,15) →
   (0,15) → (0,0) metres, over and over.
2. Press **=** twice (16×). It walks the loop much faster, and the mind keeps
   up.
3. Stop the mind service while it walks. The body finishes its current leg and
   then waits (there is no mind, so no new orders). Start the service again
   and the loop resumes.
4. Close the game, then reopen it. The body continues from where it stopped.

**About speed:** 80 m per game minute is a brisk human walk. At 1× (1 game
minute per real second) the body crosses a 20 m leg in a quarter of a second,
which looks fast because a whole day passes in 24 real minutes. That is
correct. The real map in Phase 1 has distances of hundreds of metres.

## 10.3 One-command launcher

So you don't have to start two programs by hand each time:

`tools/run_dev.ps1` (Windows)
```powershell
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not $env:GODOT) { Write-Error "Set the GODOT environment variable (step 01)."; exit 1 }
$py = Join-Path $root "mind_service\.venv\Scripts\python.exe"
$mind = Start-Process -FilePath $py -ArgumentList "-m", "mind" -WorkingDirectory (Join-Path $root "mind_service") -PassThru
try {
    & $env:GODOT --path (Join-Path $root "godot") -- @args
} finally {
    Stop-Process -Id $mind.Id -ErrorAction SilentlyContinue
}
```

`tools/run_dev.sh` (Linux/macOS)
```bash
#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
: "${GODOT:?Set the GODOT environment variable (step 01)}"
(cd "$root/mind_service" && exec .venv/bin/python -m mind) &
mind_pid=$!
trap 'kill $mind_pid 2>/dev/null || true' EXIT
"$GODOT" --path "$root/godot" -- "$@"
```

Usage: `tools/run_dev.ps1 --slot=test --speed=16`. Anything after the script
name is passed through to the game.

## Common mistakes

- **Making the body act on its own when there are no orders** (wandering,
  idling). Not in Phase 0: an inactive mind means an inactive body.
- **Sending an `action_update` for every frame of movement.** Send `started` and
  a final status only. `progress` is reserved for long actions later.
