# Step 11 — Save checkpoints and restore

**Goal:** coordinated, crash-safe snapshots of *both* databases at the same
tick, verified by checksum, and restorable.

The code was installed in step 08 (`SaveManager.checkpoint()` and
`_restore_snapshot()`) and step 06 (`Session.on_save_request`). This step is
about understanding it and proving it.

## 11.1 How a checkpoint works

```
Godot SaveManager                          Mind service
─────────────────                          ────────────
pause clock at tick T
flush world (one transaction)
make  snapshots/<label>.partial/
send  save_request(<label>.partial)  ───▶  VACUUM INTO <label>.partial/mind.sqlite
                                     ◀───  save_ready { sha256 }
verify the mind file's sha256 matches
VACUUM INTO <label>.partial/world.sqlite
write manifest.json (tmp file → rename)
swap .partial → <label>  (replaces any old one)
resume clock
```

**Guarantees, and why each exists:**

| Guarantee | Mechanism |
|-----------|-----------|
| Both databases are at the same tick | The clock pauses **mid-frame** (`sim_clock.gd` re-checks `paused` on every tick). Without that, at high speed the rest of the frame's ticks kept running after the pause, and a snapshot claimed tick 10090 while holding 10080. That was a real bug found in testing. |
| A failed checkpoint never damages an older one | Snapshots are built in `<label>.partial` and swapped in only when complete. Without that, an earlier version wiped the existing `day_0003` before failing. |
| A half-written snapshot is never loaded | `manifest.json` is written last. Restore refuses any folder without one. `.partial` folders are deleted at startup. |
| Corruption is detected | sha256 of both files is in the manifest and checked on restore |
| Stale WAL files can't corrupt a restore | Restore deletes `-wal` and `-shm` files before copying |

**When checkpoints happen:** automatically at the start of every game day
(`day_NNNN`), and manually with **F5** in-game (`manual_<tick>`).

## 11.2 Restore

Restore runs at startup, **before** either database is opened:
```
godot … -- --slot=test --restore=day_0002
```
Godot copies the snapshot's `world.sqlite` and `mind.sqlite` over the live slot
after verifying their checksums. It copies the mind file but never opens it,
because that file belongs to the mind service.

## Check it works

Run everything with `tools/run_dev.ps1 --slot=savetest --speed=600` (a game day
then takes about 2.4 s), wait about 10 s, and close the window.

1. Output: `checkpoint 'day_0001' saved at tick 1440`, then `day_0002` at
   2880, and so on. **Every tick is an exact multiple of 1440.**
2. Open `snapshots/day_0002/manifest.json`. `tick` is 2880. Open that folder's
   `world.sqlite`: `world_meta.current_tick` is also `2880`.
3. **Restore:** run `--slot=savetest --restore=day_0001`. The output shows
   `Restore: … restored from 'day_0001' (tick 1440)`, then
   `SaveManager: … at tick 1440`.
4. **Failure safety:** stop the mind service, run with `--speed=600` for a few
   seconds. You see `checkpoint … FAILED`. The **older snapshots are
   untouched**, and no `.partial` folder remains after the next start.
5. **Corruption detection:** edit one byte of a snapshot's `world.sqlite` (or
   just append text to it), then try to restore it. You get
   `checksum mismatch … Not restoring`.

## Common mistakes

- **Copying save files while the game is running.** Use checkpoints, which
  exist for exactly this.
- **Adding something to the world without adding it to `flush()`.** If it isn't
  flushed, it isn't saved. Every new kind of persistent state needs a column or
  table, a migration, and a flush or restore path.
- **Saving the Chroma index in snapshots** (Phase 1+). Don't: it is rebuilt
  from `mind.sqlite`.
