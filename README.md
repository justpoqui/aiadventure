# aiadventure

A persistent single-player AI life simulation built in **Godot 4**. One amnesiac
survivor wakes at a forest campsite near an abandoned town. With no quests or
scripts, they form beliefs, memories, goals, routines, and an identity of their
own.

**Status:** architecture review. No implementation until the review is signed off.

Start with [`docs/architecture/00-overview-and-review.md`](docs/architecture/00-overview-and-review.md).

| Layer | Technology |
|-------|------------|
| World, rendering, perception, action resolution | Godot 4 (GDScript), 2D now with 3D-ready simulation, `world.sqlite` |
| Mind (cognition for every agent) | Python 3.12 Mind Service, `mind.sqlite` |
| Long-term memory index | ChromaDB (derived, rebuildable) |
| Language model | Ollama: Qwen3 8B on an 8 GB GPU (14B optional for overnight reflection; Llama/DeepSeek pluggable) |
| Planning | Hierarchical intentions + GOAP |
