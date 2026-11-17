# Step 09 — MindBridge and handshake

**Goal:** Godot connects to the mind service, completes the versioned
handshake, survives the service starting late or restarting, and stops cleanly
on a protocol mismatch.

## 9.1 The real MindBridge

Replace the stub `autoload/mind_bridge.gd` with:

`godot/autoload/mind_bridge.gd`
```gdscript
extends Node
## WebSocket client to the Python mind service. Owns the protocol envelope.

signal connected                          # handshake complete (hello_ack received)
signal disconnected
signal message(env: Dictionary)

const PROTOCOL_VERSION := 1
const RETRY_SECONDS := 2.0
const CLOSE_PROTOCOL_MISMATCH := 1002   # WebSocket close code the mind uses for a version mismatch

var url := "ws://127.0.0.1:8765"
var mind_schema: int = 0
var _ws := WebSocketPeer.new()
var _last_state := WebSocketPeer.STATE_CLOSED
var _handshake_done := false
var _retry_in := 0.0
var _gave_up := false


func _ready() -> void:
	url = CmdArgs.all().get("mind-url", url)
	_connect()


func is_ready() -> bool:
	return _handshake_done and _ws.get_ready_state() == WebSocketPeer.STATE_OPEN


func send(type: String, payload: Dictionary, agent_id: String = "") -> void:
	if _ws.get_ready_state() != WebSocketPeer.STATE_OPEN:
		return
	var env := {
		"v": PROTOCOL_VERSION,
		"type": type,
		"msg_id": Ids.ulid(),
		"agent_id": agent_id if agent_id != "" else null,
		"tick": SimClock.tick,
		"payload": payload,
	}
	_ws.send_text(JSON.stringify(env))


## Polite close: lets the mind service see a normal shutdown instead of a dropped socket.
func close() -> void:
	_gave_up = true
	_ws.close(1000, "shutdown")
	for i in 10:
		_ws.poll()
		if _ws.get_ready_state() == WebSocketPeer.STATE_CLOSED:
			break
		OS.delay_msec(20)


func _connect() -> void:
	_ws = WebSocketPeer.new()
	# Mark "connecting" ourselves: a refused connection can jump straight to CLOSED,
	# and without this the CLOSED -> CLOSED "change" would go unnoticed and we'd never retry.
	_last_state = WebSocketPeer.STATE_CONNECTING
	if _ws.connect_to_url(url) != OK:
		_last_state = WebSocketPeer.STATE_CLOSED
		_retry_in = RETRY_SECONDS


func _process(delta: float) -> void:
	if _gave_up:
		return
	if _retry_in > 0.0:
		_retry_in -= delta
		if _retry_in <= 0.0:
			_connect()
		return
	_ws.poll()
	var state := _ws.get_ready_state()
	if state == WebSocketPeer.STATE_OPEN and _last_state != WebSocketPeer.STATE_OPEN:
		_send_hello()
	# Read before handling a close: the last message may explain WHY it closed.
	while _ws.get_available_packet_count() > 0:
		_receive(_ws.get_packet().get_string_from_utf8())
	if state == WebSocketPeer.STATE_CLOSED and _last_state != WebSocketPeer.STATE_CLOSED:
		if _handshake_done:
			disconnected.emit()
		_handshake_done = false
		if _ws.get_close_code() == CLOSE_PROTOCOL_MISMATCH:
			# Retrying can never succeed: one side needs a code update.
			push_error("Mind service rejected protocol v%d: %s" % [PROTOCOL_VERSION, _ws.get_close_reason()])
			_gave_up = true
		if not _gave_up:
			_retry_in = RETRY_SECONDS
	_last_state = state


func _send_hello() -> void:
	send("hello", {
		"client": "godot",
		"slot_dir": ProjectSettings.globalize_path(SaveManager.slot_dir),
		"world_seed": SaveManager.world_seed,
	})


func _receive(text: String) -> void:
	var env = JSON.parse_string(text)
	if typeof(env) != TYPE_DICTIONARY:
		push_error("MindBridge: unreadable message: " + text.left(200))
		return
	# Errors are handled before the version check so a mismatch can still be reported.
	if env.get("type") == "error":
		var p: Dictionary = env.get("payload", {})
		push_error("Mind service error [%s]: %s" % [p.get("code"), p.get("message")])
		return
	if int(env.get("v", -1)) != PROTOCOL_VERSION:
		push_error("MindBridge: ignoring message with protocol v%s" % env.get("v"))
		return
	if env.get("type") == "hello_ack":
		mind_schema = int(env["payload"]["mind_schema"])
		_handshake_done = true
		print("MindBridge: connected (mind schema v%d)" % mind_schema)
		connected.emit()
	message.emit(env)
```

Three details here came from bugs found while testing this guide:

| Detail | What went wrong without it |
|--------|----------------------------|
| `_connect()` sets `_last_state = STATE_CONNECTING` | A refused connection goes straight to CLOSED. That looked like "no change", so Godot **never retried** if the mind service started after the game. |
| Packets are read **before** the close is handled | Otherwise the final message is dropped. |
| A mismatch is detected from **close code 1002 and its reason** | When the error message and the close frame arrive in the same poll, Godot discards the message. The close reason always arrives. |

## 9.2 Start order doesn't matter any more

Both orders must work:
- **Mind service first, then Godot:** connects at once.
- **Godot first, then the mind service:** Godot retries every 2 s and connects
  when the service appears.

## Check it works

Run the mind service in one terminal (`python -m mind`) and the game from
Godot.

1. **Normal:** Godot prints `MindBridge: connected (mind schema v1)`. The mind
   log shows `hello from godot: slot=<the same path as SaveManager printed>`.
2. **Late start:** stop the mind service, run the game, wait 5 s, then start the
   service. Godot connects within about 2 s.
3. **Restart:** with both running, stop the mind service (Ctrl+C) and start it
   again. Godot prints `connected` a second time.
4. **Clean exit:** close the game window. The mind log shows
   `godot disconnected` with **no traceback**.
5. **Protocol mismatch:** temporarily change `PROTOCOL_VERSION` to `2` in
   `mind_bridge.gd` and run. Godot prints **one** error,
   `Mind service rejected protocol v2: mind speaks v1, got v2`, and does
   **not** retry. The mind log shows exactly one `protocol_mismatch`.
   **Change it back to 1.**
6. Check `<slot>/mind.sqlite` now exists next to `world.sqlite`.

## Common mistakes

- **Checking the protocol version before handling `error` messages.** A
  mismatched client then can't even read why it was rejected.
- **Calling `poll()` only while the socket is open.** It must be called every
  frame, including while connecting and closing.
- **Firewall prompts on Windows.** Allow Python on *private* networks only. It
  listens on 127.0.0.1, so it is never exposed anyway.
