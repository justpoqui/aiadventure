# Step 01 — Workstation setup

**Goal:** every tool installed, at a known version, with nothing left that
works only "on my machine".

## 1.1 Install the tools

| Tool | Version | Notes |
|------|---------|-------|
| NVIDIA driver | latest Game Ready or Studio | Needed for Ollama to use the 5060 Ti |
| Git | any recent | Enable "Git Credential Manager" on Windows |
| Python | **3.12.x** | Windows: tick "Add python.exe to PATH" |
| Godot | latest **4.x stable, standard** | Unzip anywhere. Godot is a single executable. |
| Ollama | latest | Runs as a background service or tray app |
| VS Code (recommended) | latest | Extensions: *godot-tools*, *Python*, *Even Better TOML*, *YAML* |

## 1.2 Make Godot callable from the terminal

Set an environment variable `GODOT` to the full path of the Godot executable.
The run scripts use it.

**Windows (PowerShell):**
```powershell
setx GODOT "C:\Tools\Godot\Godot_v4.x-stable_win64.exe"
# close and reopen the terminal afterwards
```
**Linux/macOS:**
```bash
echo 'export GODOT="$HOME/tools/godot/Godot_v4.x-stable_linux.x86_64"' >> ~/.bashrc
source ~/.bashrc
```

## 1.3 Get the repository

```bash
git clone https://github.com/justpoqui/aiadventure.git
cd aiadventure
git checkout ccr-953f197b-thkzyo      # the branch that holds the architecture docs
git checkout -b phase0                 # your working branch for this phase
```

## Check it works

Run each line. Every one must print a version, not an error.

```bash
git --version
python --version          # must say 3.12.x  (on Linux it may be python3)
"$GODOT" --version        # PowerShell: & $env:GODOT --version
ollama --version
nvidia-smi                # must list "NVIDIA GeForce RTX 5060 Ti" with 8 GB
```

## Common mistakes

- **Two Pythons installed.** `python --version` shows 3.11 or 3.13. Use the
  `py -3.12` launcher on Windows, or install 3.12 and put it first on PATH.
- **The Godot .NET build.** That build is only needed for C#. We use GDScript,
  so get the standard build.
- **Forgetting to reopen the terminal after `setx`.** The new variable isn't
  visible until you do.
