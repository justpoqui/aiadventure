# Backstory templates (world truth: never visible to the mind)

At world creation, `worldgen` picks one template from `backstories/` using the
world seed. It fills the slots from `name_pools.yaml`, has the LLM write
document prose **constrained to the listed facts**, validates the prose, and
places clues behind gates. The output is written only to `world.sqlite`
(`lore_facts`, `lore_clues`, `lore_gates`, `lore_recollections`). See
`docs/architecture/09-divinity-knockout-lore.md §3`.

## Design rules every template must satisfy

1. **Mundane and real.** No supernatural lore. The survivor must be able to
   believe all of it.
2. **Every core fact has at least 2 independent clue paths.** No two paths may
   share the same gate chain, and every path must be reachable from the
   starting state.
3. **Weak evidence.** No single clue exceeds a strength of 0.4. For each core
   fact, the strengths of its clues, plus 0.2 for each body mark and each
   recollection that supports it, sum to at least 1.2, so 3–5 fragments are needed before
   a core belief can pass 0.7 confidence.
4. **About 25% red herrings** among clues that look like they concern the
   survivor's identity.
5. **The body is a clue.** `latent_skills` and `body_marks` must be consistent
   with the backstory.
6. **Recollections are sensory**, never declarative ("smell of motor oil", not
   "you were a mechanic").
7. Only use locations that exist: `campsite, forest, trail, bridge, town_hall,
   farmhouse, general_store, garage, water_tower`.

## Slots

`{survivor.first}`, `{survivor.last}`, `{survivor.first_initial}`, `{survivor.last_initial}`,
`{survivor.they|them|their}`, `{<role>.first}`, `{<role>.last}`, `{<role>.first_initial}`,
`{<role>.role_word}` (e.g. father/mother, drawn from the cast entry), `{years_ago:N}`. Roles are declared per
template under `cast`. Pronouns are drawn per world for document prose only.

## Clue fields

| Field | Meaning |
|-------|---------|
| `form` | letter, photo, ledger, object, tape, carving, notice, mark, … |
| `at` | location (+ optional sub-location) |
| `gate` | `none`, `locked{key_at}`, `needs_repair{component}`, `needs_power{power}`, `needs_drying`, `combination{parts_at}`, `expert{skill, level}`, `climb{component}` |
| `reveals` | `fact_id: strength` (0.05–0.4) |
| `fragment` | what the clue physically shows; guidance for the prose generator |
| `decay` | `none` (default), or a natural decay rate, which is allowed only on non-core paths (see §3.4 of doc 09) |

## Destruction

If a clue entity is destroyed, it is gone from the world forever. The
survivor keeps only their **memory** of what they perceived from it. See doc
09 §3.4.

## Templates

| File | Who the survivor was | Why the town is empty |
|------|----------------------|-----------------------|
| `01_the_mechanics_child.yaml` | A mechanic who grew up above the garage, estranged from their parent | Contaminated water, evacuation |
| `02_the_surveyor.yaml` | A water-authority surveyor who came to doubt the project | Bought out for a reservoir that was never built |
| `03_the_carpenters_sibling.yaml` | A carpenter searching for a sibling who stayed | A flood washed out the road; the county closed the town |
| `04_the_mill_hand.yaml` | A logger carrying guilt over a mill accident | Slow decline after the mill closed; the water tower failed |

All four share the same opening night (a storm, a fall, a head wound), so the
starting condition is identical whichever past is true.
