# Step 03 — Repository scaffolding

**Goal:** the folder layout from `docs/architecture/02-project-structure.md`,
with ignore rules, line-ending rules, and a Python environment that installs
in one command.

## 3.1 Create the folders

Only create what Phase 0 uses. Empty placeholder folders for later phases are
noise.

```
aiadventure/
├── docs/ … (exists)
├── shared/protocol/v1/
├── godot/                      ← created by Godot in step 06
├── mind_service/
│   ├── src/mind/
│   │   ├── transport/
│   │   ├── runtime/
│   │   ├── llm/
│   │   ├── storage/migrations/
│   │   └── tools/
│   └── tests/
├── worldgen/templates/ … (exists)
├── .github/workflows/          ← CI, step 13
└── tools/
```

Put an empty `__init__.py` in `src/mind/` and in every subfolder of it.

## 3.2 `.gitignore` (repo root)

```gitignore
# Godot
godot/.godot/
godot/*.translation
godot/export_presets.cfg

# Python
__pycache__/
*.pyc
.venv/
.bench/
*.egg-info/
.pytest_cache/

# Local data — saves live in Godot's user:// folder, but never commit any DB
*.sqlite
*.sqlite-wal
*.sqlite-shm

# OS / editors
.DS_Store
Thumbs.db
.vscode/settings.json
```

## 3.3 `.gitattributes` (repo root)

This stops Windows line endings from breaking the SQL migration splitter and
the GDScript files.

```gitattributes
* text=auto eol=lf
*.png binary
*.jpg binary
*.ogg binary
*.wav binary
```

## 3.4 `mind_service/pyproject.toml`

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "mind-service"
version = "0.0.1"
requires-python = ">=3.12"
dependencies = [
  "websockets>=13",
  "pydantic>=2.7",
  "httpx>=0.27",
  "python-ulid>=2.2",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.23"]

[tool.hatch.build.targets.wheel]
packages = ["src/mind"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

ChromaDB and Jinja are **not** added yet. Memory starts in Phase 1, and adding
dependencies before they're used just adds things to break.

## 3.5 Create the Python environment

**Windows:**
```powershell
cd mind_service
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```
**Linux/macOS:**
```bash
cd mind_service
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## 3.6 First test

`mind_service/tests/test_smoke.py`
```python
import mind

def test_package_imports():
    assert mind is not None
```

## Check it works

```bash
cd mind_service
pytest -q          # → 1 passed
git status         # .venv/ must NOT appear
```

Commit: `Phase 0 step 03: repository scaffolding`.

## Common mistakes

- **Missing `__init__.py` files.** You get `ModuleNotFoundError: mind.transport`.
- **Running `pip install` without the venv activated.** Packages go into the
  global Python. Your prompt should show `(.venv)`.
- **Committing `.venv/`.** Check `git status` before every commit in this step.
