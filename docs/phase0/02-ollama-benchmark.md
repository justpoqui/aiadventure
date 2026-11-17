# Step 02 — Ollama setup and hardware benchmark

**Goal:** configure Ollama for an 8 GB card, then **measure** speed and VRAM
for each model role. The architecture's numbers (`01-system-architecture.md
§6`) are estimates. This step replaces them with yours.

## 2.1 Configure Ollama

These four settings matter on 8 GB:

| Variable | Value | Why |
|----------|-------|-----|
| `OLLAMA_FLASH_ATTENTION` | `1` | Required for a quantized KV cache; faster |
| `OLLAMA_KV_CACHE_TYPE` | `q8_0` | Halves KV-cache VRAM with negligible quality loss |
| `OLLAMA_MAX_LOADED_MODELS` | `1` | Never hold two big models in VRAM at once |
| `OLLAMA_KEEP_ALIVE` | `30m` | Keeps the model loaded between thoughts |

**Windows:**
```powershell
setx OLLAMA_FLASH_ATTENTION 1
setx OLLAMA_KV_CACHE_TYPE q8_0
setx OLLAMA_MAX_LOADED_MODELS 1
setx OLLAMA_KEEP_ALIVE 30m
```
Then **quit Ollama from the system tray and start it again**. It only reads
these variables at startup.

**Linux (systemd service):**
```bash
sudo systemctl edit ollama
# add, then save:
# [Service]
# Environment="OLLAMA_FLASH_ATTENTION=1"
# Environment="OLLAMA_KV_CACHE_TYPE=q8_0"
# Environment="OLLAMA_MAX_LOADED_MODELS=1"
# Environment="OLLAMA_KEEP_ALIVE=30m"
sudo systemctl restart ollama
```

## 2.2 Pull the models

```bash
ollama pull qwen3:8b               # primary (~5.2 GB)
ollama pull qwen3-embedding:0.6b   # embeddings (run on CPU)
ollama pull qwen3:14b              # optional: overnight reflection & worldgen (~9.3 GB)
```

If `qwen3-embedding:0.6b` isn't available in your Ollama version, use
`nomic-embed-text` and note it in your results.

## 2.3 Quick manual sanity check

```bash
ollama run qwen3:8b "Say hello in five words." --verbose
ollama ps
```

`ollama ps` must show `qwen3:8b` with **`100% GPU`** in the PROCESSOR column.
If it says something like `25%/75% CPU/GPU`, something else is using VRAM.
Close games and browsers with hardware acceleration, then re-check.

## 2.4 The benchmark script

Create it now. It is standalone and uses only `httpx`.

`tools/benchmark_ollama.py`
```python
"""Phase 0 hardware benchmark. Usage:
    python tools/benchmark_ollama.py                 # 8B only
    python tools/benchmark_ollama.py --with-14b      # also test 14B (slow)
Prints a markdown table; paste it into docs/benchmarks/phase0.md.
"""
import argparse, json, statistics, time
import httpx

OLLAMA = "http://127.0.0.1:11434"
client = httpx.Client(base_url=OLLAMA, timeout=600)

# ~1.5k tokens of realistic L2 context: percepts + beliefs + memories
CONTEXT = "\n".join(
    f"- Memory {i}: I walked past a rusted metal structure near the trail; "
    f"the wind was cold and I felt uneasy about the planks on the bridge." for i in range(60)
)
SYSTEM = ("You are the inner voice of a person who woke in a forest with no memory. "
          "Think in first person. Only mention things listed in the context.")
USER = f"Context:\n{CONTEXT}\n\nWhat do you make of what you have seen today?"
SCHEMA = {
    "type": "object",
    "properties": {
        "thought": {"type": "string"},
        "beliefs": {"type": "array", "items": {"type": "object", "properties": {
            "description": {"type": "string"}, "confidence": {"type": "number"}},
            "required": ["description", "confidence"]}},
    },
    "required": ["thought", "beliefs"],
}

def chat(model: str, think: bool) -> dict:
    t0 = time.perf_counter()
    r = client.post("/api/chat", json={
        "model": model, "stream": False, "think": think, "format": SCHEMA,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": USER}],
        "options": {"num_ctx": 8192, "temperature": 0.7, "seed": 42},
    })
    r.raise_for_status()
    d = r.json()
    json.loads(d["message"]["content"])            # must be valid JSON
    return {
        "wall_s": time.perf_counter() - t0,
        "prompt_tokens": d.get("prompt_eval_count", 0),
        "prompt_tps": d.get("prompt_eval_count", 0) / max(d.get("prompt_eval_duration", 1) / 1e9, 1e-9),
        "gen_tokens": d.get("eval_count", 0),
        "gen_tps": d.get("eval_count", 0) / max(d.get("eval_duration", 1) / 1e9, 1e-9),
    }

def vram(model: str) -> str:
    for m in client.get("/api/ps").json().get("models", []):
        if m["name"].startswith(model):
            pct = 100 * m.get("size_vram", 0) / max(m.get("size", 1), 1)
            return f"{m.get('size_vram', 0) / 2**30:.2f} GB ({pct:.0f}% on GPU)"
    return "not loaded"

def bench(model: str, think: bool, runs: int) -> list[str]:
    chat(model, think)                              # warm-up: includes model load, discarded
    res = [chat(model, think) for _ in range(runs)]
    med = lambda k: statistics.median(r[k] for r in res)
    return [model, "on" if think else "off", f"{med('prompt_tokens'):.0f}", f"{med('prompt_tps'):.0f}",
            f"{med('gen_tokens'):.0f}", f"{med('gen_tps'):.1f}", f"{med('wall_s'):.1f}", vram(model)]

def bench_embed(runs: int = 20) -> str:
    texts = [f"I saw a rusted tower near the trail, number {i}" for i in range(runs)]
    client.post("/api/embed", json={"model": EMBED, "input": texts[0], "options": {"num_gpu": 0}})
    t0 = time.perf_counter()
    for t in texts:
        client.post("/api/embed", json={"model": EMBED, "input": t, "options": {"num_gpu": 0}}).raise_for_status()
    return f"{EMBED} on CPU: {1000 * (time.perf_counter() - t0) / runs:.0f} ms per memory"

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-14b", action="store_true")
    ap.add_argument("--embed-model", default="qwen3-embedding:0.6b")
    a = ap.parse_args()
    EMBED = a.embed_model
    rows = [bench("qwen3:8b", False, 5), bench("qwen3:8b", True, 3)]
    if a.with_14b:
        rows.append(bench("qwen3:14b", True, 2))
    print("| model | think | prompt tok | prompt tok/s | gen tok | gen tok/s | wall s | VRAM |")
    print("|---|---|---|---|---|---|---|---|")
    for r in rows:
        print("| " + " | ".join(r) + " |")
    print()
    print(bench_embed())
```

## 2.5 Run it the right way

The game and the model share the GPU, so measure with **Godot open**. Any empty
Godot project running a scene is fine for now.

```bash
python -m venv .bench
.bench\Scripts\Activate.ps1          # Windows PowerShell
# source .bench/bin/activate         # Linux/macOS
pip install httpx
# start any Godot scene, then:
python tools/benchmark_ollama.py --with-14b
```

In a second terminal, watch memory while it runs: `nvidia-smi -l 1`.

## 2.6 Record the results

Create `docs/benchmarks/phase0.md` with:
1. the printed table;
2. peak VRAM from `nvidia-smi` with Godot running;
3. your conclusion, in the format below.

```
L2 call (8B, think off): ___ s  → ___ thoughts per real minute
Reflection (8B, think on): ___ s per call
14B usable for overnight reflection? yes / no (gen tok/s = ___)
Embedding on CPU: ___ ms per memory
```

## Check it works

- The 8B rows show **100% on GPU**.
- Peak VRAM with Godot open is **≤ 7.5 GB**, leaving headroom.
- Every call returned valid JSON (the script raises an error if not).
- `docs/benchmarks/phase0.md` is committed.

**Decision rules:**
- If 8B think-off wall time is over 10 s, lower `num_ctx` to 4096 and re-run.
- If 14B generates fewer than 3 tokens/s, disable "deep sleep" mode and use 8B
  for reflection.

## Common mistakes

- **Forgetting to restart Ollama after setting the variables.** Nothing changes
  until you do.
- **Counting the first call.** It includes loading the model from disk, which
  is why the script discards a warm-up.
- **Benchmarking with Chrome or a game open.** They steal VRAM and make the 8B
  model spill to the CPU.
- **Running embeddings on the GPU.** Without `num_gpu: 0` it may evict or
  shrink the main model.
