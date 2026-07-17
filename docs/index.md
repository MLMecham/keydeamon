<p align="center">
  <img src="assets/logos/KeyDaemon_NoBack.png" width="260" alt="KeyDaemon — the daemon key">
</p>

# keydaemon

**A lightweight, programmable keyboard/mouse automation daemon** — a clean Python API and CLI instead of a GUI macro recorder. It runs quietly in the background: autoclickers, anti-AFK loops, text expansion, form filling, drawing, and pixel-watching.

!!! warning "Know where to point it"
    **Not for** kernel-level anti-cheat games (Valorant, Fortnite, PUBG).
    **Fine for** Minecraft, singleplayer/private servers, productivity, and desktop automation.

---

## Install

```bash
git clone https://github.com/MLMecham/keydeamon
cd keydeamon
uv sync --extra dev        # install with dev/test dependencies
uv run keydaemon --help    # the CLI
```

Want `keydaemon` available in every terminal? Install it as a uv tool:

```bash
uv tool install --editable .
```

## The first 30 seconds

```bash
keydaemon run autoclicker
```

```text
First run of built-in preset 'autoclicker' - installed ...\macros\autoclicker.toml
Emergency kill: <ctrl>+<shift>+<alt>+<f12>  (or: keydaemon stop)
Autoclicker preset.
Press F6 to start/stop. Press F8 to quit.
Running 'autoclicker'. Ctrl+C to stop.
```

Hover over your target, press ++f6++, and the daemon clicks ~4×/second with human-ish jitter until you press ++f6++ again. ++f8++ quits. The preset installed itself as an ordinary TOML file — edit it to make it yours.

## Build in Python, run from the CLI

Write a macro with the fluent builder, try it, then `.save()` it — that writes an ordinary TOML into your macros dir, and it becomes a first-class CLI macro:

```python
import keydaemon

# Hotkey-armed clicker: F6 toggles, F8 quits. Try it:
clicker = keydaemon.macro().every(0.1).click("left").loop().hotkey("f6").exit_key("f8")
clicker.run().join()

# Like it? Make it permanent:
clicker.save("clicker")
```

```bash
keydaemon run clicker            # from any terminal, from now on
keydaemon run clicker --detach   # or as a background process
```

Saving again overwrites — your Python script is the source of truth. The TOML it writes is human-readable and hand-editable:

```toml
[trigger]
type = "manual"
hotkey = "f6"      # press to start/stop
mode = "toggle"

[behavior]
every = 0.1
repeat = -1        # loop until toggled off

[actions]
sequence = ["click:left"]
```

[More recipes — expansion, anti-AFK, form filling :material-arrow-right:](examples.md){ .md-button }

## Triggers — *when* a macro fires

| Trigger | How it starts | Builder / TOML |
|---|---|---|
| **Loop** | Immediately, on a timer | `.every(s).loop()` — `type = "loop"` |
| **Hotkey** | When you press a key (toggle or once) | `.hotkey(key, mode)` — `type = "manual"`, `hotkey`, `mode` |
| **Expand** | When you type a text pattern — bank many per macro | `.expand(pattern, replace)` chained — `type = "expand"`, `[expansions]` |
| **Profile** | Starts several macros together | `type = "profile"`, `macros.run = [...]` |

## The daemon always lets go

Automation that injects input needs a way out that *cannot fail*. keydaemon's kill hierarchy is the core of its design — a reserved hardware combo no macro can bind or fake, sanctioned `stop:self` / `stop:all` actions for macros that need to bail out, and held-input tracking so a stopped macro never leaves a key stuck down.

[Read the safety model :material-arrow-right:](safety.md){ .md-button .md-button--primary }

## Where things live

```text
<user_data_dir>/keydaemon/     # %LOCALAPPDATA%\keydaemon\keydaemon on Windows
    macros/                    # one TOML per macro — presets install here too
    pids/                      # one PID file per detached run
    keydaemon.log              # output from --detach runs
```
