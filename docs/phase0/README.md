# Phase 0 — Step-by-step guide

Phase 0 builds the **skeleton** every later phase hangs on. It contains no AI
behaviour yet. When it is done you will have:

- Godot and the Python mind service talking over a versioned protocol;
- a 2D world on a 3D-ready simulation layer, with a clock you control;
- a survivor body that walks wherever a *stand-in* mind tells it to;
- both databases created by migrations, plus working save checkpoints;
- an LLM gateway that can call Qwen3 8B safely (schema checks, reality guard, ledger);
- measured numbers for what your RTX 5060 Ti 8 GB can actually do;
- CI running the Python tests on every push.

## Do the steps in this order

| # | Step | Needs | Rough effort |
|---|------|-------|--------------|
| 01 | [Workstation setup](01-workstation-setup.md) | — | 1 h |
| 02 | [Ollama + hardware benchmark](02-ollama-benchmark.md) | 01 | 1–2 h |
| 03 | [Repository scaffolding](03-repo-scaffolding.md) | 01 | 1 h |
| 04 | [Protocol v1](04-protocol.md) | 03 | 1–2 h |
| 05 | [Mind database + migrations](05-mind-database.md) | 03 | 1 h |
| 06 | [Mind service + stand-in mind](06-mind-service.md) | 04, 05 | 2 h |
| 07 | [Godot skeleton (clock, 3D-ready entities, navigation)](07-godot-skeleton.md) | 01 | 3–4 h |
| 07b | ~~World map + the 2D look~~: replaced by the [forest world](../world/forest_world.md) (Blender tiles, TileMapLayer, wildlife) | 07 | 2 h |
| 08 | [World database + live persistence](08-world-database.md) | 07 | 2 h |
| 09 | [MindBridge + handshake](09-bridge-handshake.md) | 06, 08 | 1–2 h |
| 10 | [Action loop + launcher](10-action-loop.md) | 09 | 1 h |
| 11 | [Save checkpoints + restore](11-save-checkpoints.md) | 10 | 1–2 h |
| 12 | [LLM gateway](12-llm-gateway.md) | 02, 05 | 2–3 h |
| 13 | [Continuous integration](13-ci.md) | 06 | 30 min |
| 14 | [Character panel](14-character-panel.md) | 09 | 1 h |
| 15 | [Exit checklist](15-exit-checklist.md) | all | 1 h |

Python (04–06) and Godot (07–08) are independent tracks, so you can switch
between them. They meet at step 09.

## How this guide was verified

All code in steps 04–14 was **run before it was written down**:
- The Python service passed its 18 tests.
- The Godot side ran headless on Godot 4.6 with godot-sqlite v4.6, against the
  real mind service. That covered walking, daily checkpoints, resume, restore,
  protocol mismatch, the service starting late or restarting, saving while the
  mind is down, and snapshot consistency. The character panel (step 14) was
  rendered and screenshotted with both preview and live data. The world map
  (step 07b) was rendered, and its pathfinding was tested on the real map.
- Six real bugs found during that testing are fixed in the code and called out
  where they happened.

Not verified here, because they need your hardware: the Ollama benchmark
(step 02), the LLM smoke test against a real model (step 12), the Windows
launcher script, and the in-editor steps (scene building, navigation baking).

## Ground rules for the whole phase

1. **Commit after every step** (with the step's "check it works" passing). Small
   commits make mistakes cheap to undo.
2. **Never let Godot code read the mind database, or Python code read the world
   database.** That separation is the foundation of the whole project.
3. **Simulation units are metres and game minutes.** Pixels exist only in
   `views/` and in the three 2D adapter files `sim_units.gd`,
   `sim_navigation_2d.gd` and `nav_builder_2d.gd`. If you ever type a pixel value anywhere else in
   `sim/`, stop.
4. **Anything named "stand-in" or "scripted" is scaffolding** and will be
   deleted in Phase 1. Don't polish it.
5. Every step ends with **Check it works** and **Common mistakes**. Don't move on
   until the check passes.

## Conventions used in this guide

- Commands that differ by OS are shown as **Windows (PowerShell)** and
  **Linux/macOS**.
- `<repo>` means the folder you cloned the repository into.
- Code blocks titled with a path (e.g. `mind_service/src/mind/__main__.py`) are
  files you create at that path.
- Godot version: the latest **Godot 4.x stable, standard build** (not .NET).
  Everything here uses Godot 4 APIs only.
