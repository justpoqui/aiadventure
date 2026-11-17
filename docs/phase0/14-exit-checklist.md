# Step 14 — Phase 0 exit checklist

Phase 0 is done when **every** box is ticked. Run through it in one sitting on
a clean start (reboot, then start Ollama), and record the date and commit hash
at the bottom.

## Hardware & model
- [ ] `docs/benchmarks/phase0.md` is committed with your real numbers (step 02)
- [ ] `qwen3:8b` runs at 100% GPU with Godot open; peak VRAM ≤ 7.5 GB
- [ ] `python -m mind.tools.smoke_llm` returns a valid, first-person thought (step 12)

## Protocol & connection
- [ ] `pytest -q` in `mind_service`: all 16 pass
- [ ] `export_schemas --check` → up to date
- [ ] Godot connects whichever program starts first (step 09, checks 2–3)
- [ ] A protocol mismatch produces one clear error and no retry loop (step 09, check 5)
- [ ] Closing the game leaves no traceback in the mind log

## Simulation & 3D-readiness
- [ ] The stand-in mind walks the body around its rectangle with no input from you (step 10)
- [ ] Speed controls (Space, =, −) behave, and movement scales with game time
- [ ] `Vector2` appears in `sim/` only in `sim_units.gd` and `sim_navigation_2d.gd`
- [ ] The `DevClickToWalk` tool has been deleted

## Persistence & saves
- [ ] Quit, then relaunch: same tick, same body position (step 08)
- [ ] Daily checkpoints happen at exact multiples of 1440, and each manifest's tick matches its database (step 11)
- [ ] `--restore=day_0001` restores both databases to tick 1440
- [ ] A failed checkpoint leaves older snapshots untouched, and no `.partial` folder survives a restart
- [ ] A corrupted snapshot is refused on restore (checksum)

## Repository hygiene
- [ ] CI is green on the latest push (step 13)
- [ ] `git status` is clean, with no `.sqlite`, `.venv`, or `.godot/` committed
- [ ] Every scaffold is marked as such (`ScriptedMind`, `smoke_thought`)

## Sign-off

```
Date: ____________     Commit: ____________
Notes / surprises: ______________________________________________
```

When this is complete, Phase 1 starts. The stand-in mind is replaced by the
first real cognitive loop: perception, beliefs, needs, and memory.
