# keydaemon — Implementation Plan

## What It Is

A lightweight, programmable input automation daemon for personal use. Target audience: developers and power users who want a clean Python API and CLI instead of GUI macro recorders like AutoHotkey. Runs silently in the background, non-blocking, minimal resource usage (<30MB RAM, ~0% CPU at idle).

**Not for:** kernel-level anti-cheat games (Valorant, Fortnite, PUBG).
**Fine for:** Minecraft, singleplayer games, productivity, private servers, desktop automation.

---

## Core Mental Model

**Everything runs inside a profile — explicit or implicit.**

```
Profile (execution context)
│   owns: thread registry + exit key + stop_all()
│
├── starts → Loop macro      (sequence on a timer, forever or N times)
├── starts → Listener        (watches for trigger, fires sequence or do)
└── starts → Manual macro    (waits to be called explicitly or via hotkey)
                    ↓
            all three compose via:
            do (inline sub-sequences, load-time flattened, no new thread)
```

Running a single macro is just an implicit single-macro profile:
```bash
keydaemon run afk_jump
# internally: Profile(macros=["afk_jump"], exit_key="f12").start()
```

The profile owns the thread registry. `stop_all()` and the exit key are the same operation — kill all threads registered to this profile.

---

## Architecture: Three Layers

```
Layer 1: keydaemon (Python package + CLI)   ← build now
         Engine: key/mouse output, timing, jitter, text expansion, TOML loading
         CLI: keydaemon run/stop/list/new/capture

Layer 2: GUI app                             ← future
         System tray, macro browser/editor, startup toggle

Layer 3: OS integration                      ← future (via GUI)
         Windows registry / macOS launchd start-on-boot
```

---

## Storage: Folder of TOML Files

Location is OS-appropriate via `platformdirs.user_data_dir("keydaemon")`:
- **Windows:** `%APPDATA%\keydaemon`
- **macOS:** `~/Library/Application Support/keydaemon`
- **Linux:** `~/.local/share/keydaemon`

```
<user_data_dir>/keydaemon/
    macros/
        afk_jump.toml      ← loop macro
        autofill_a.toml    ← expand listener
        open_inventory.toml ← manual macro (used as do sub-sequence)
        farm_sequence.toml ← loop macro (uses do:open_inventory)
        minecraft.toml     ← profile (starts multiple macros concurrently)
        autoclicker.toml   ← installed built-in preset (generated on first run)
    pids/
        afk_jump.pid       ← one PID file per detached run
    keydaemon.log          ← detached-run output
```

TOML is human-readable, built into Python 3.11+ (`tomllib`), no database or server needed. One file per macro, editable in any text editor.

---

## TOML File Schemas

### Loop Macro
```toml
[meta]
name = "AFK Jump"
description = "Keeps you active in Minecraft singleplayer"
author = "MLMecham"
version = "1.0"
created = 2026-05-31
tags = ["minecraft", "gaming", "afk"]
enabled = true
start_on_boot = false      # reserved for GUI — ignored by CLI now

[trigger]
type = "loop"

[behavior]
every = 270                # seconds between runs
jitter = 30                # ± random seconds (anti-detection)
repeat = -1                # -1 = forever, N = run N times

[actions]
sequence = [
    "tap:space",
    "wait:0.1",
    "tap:w",
    "wait:0.05",
    "tap:s",
]
```

### Text Expansion Listener
```toml
[meta]
name = "Autofill A"
tags = ["text", "productivity"]
enabled = true
start_on_boot = false

[trigger]
type = "expand"
pattern = "///a"

[behavior]
replace = "cheeseburger"
# OR instead of replace, run a sub-macro:
# do = "open_inventory"
```

### Manual Macro (reusable sub-sequence)
```toml
[meta]
name = "Open Inventory"
tags = ["minecraft"]
enabled = true

[trigger]
type = "manual"
hotkey = "f6"              # optional: press F6 to trigger

[actions]
sequence = [
    "move_to:500,300",
    "click:left",
    "wait:0.5",
]
```

### Macro using `do`
```toml
[meta]
name = "Farm Sequence"
type = "loop"

[behavior]
every = 10
jitter = 2

[actions]
sequence = [
    "do:open_inventory",   # runs open_inventory.toml inline (flattened at load time)
    "wait:0.5",
    "tap:e",
    "do:close_inventory",
]
```

### Profile
```toml
[meta]
name = "Minecraft Session"
type = "profile"
exit_key = "f12"           # press F12 to kill all threads in this profile
start_on_boot = false      # reserved for GUI

[macros]
run = ["afk_jump", "autofill_a", "farm_sequence"]
```

---

## `do` Sub-Macro Rules

- Any macro with a sequence (loop, manual) can call `do`
- Expand listeners can use `do` as their action instead of `replace`
- Profiles cannot be `do`'d (they spawn threads — wrong tool)
- `do` is resolved at **load time** (flattened into the parent sequence)
- The runner never knows `do` existed — it just sees a flat action list
- Circular `do` detection handled in loader (track seen files, raise on cycle)

---

## Action System

### Keyboard Actions
| Action syntax | Description |
|---|---|
| `tap:w` | Press + release instantly (~40–80ms random hold by default) |
| `tap:w:0.15` | Press + release with explicit 150ms hold |
| `press:shift` | Press and hold (until release) |
| `release:shift` | Release a held key |
| `type:hello world` | Type a string of text |

`tap` duration defaults to `random.uniform(0.04, 0.08)` — natural variance baked in, no extra config needed.

`press`/`release` work for both keyboard keys and mouse buttons — resolved internally.

### Mouse Actions
| Action syntax | Description |
|---|---|
| `move_to:234,456` | Absolute position (desktop apps, forms) |
| `move_by:-50,0` | Relative movement (games, camera control) |
| `move_to:234,456:smooth` | Incremental curved movement (many small steps) |
| `move_by:-200,0:smooth` | Smooth relative (natural aim movement in games) |
| `click:left` | Click at current position |
| `click:left:2` | Double click |
| `click:right` | Right click |
| `press:left` | Hold mouse button |
| `release:left` | Release mouse button |
| `scroll:3` | Scroll down 3 wheel clicks |
| `scroll:-3` | Scroll up 3 wheel clicks |
| `scroll:3:horizontal` | Horizontal scroll |

`drag_to` is sugar — implemented as `move_to + press:left + move_to:smooth + release:left` under the hood, no separate action class needed.

### Screen Condition Actions
| Action syntax | Description |
|---|---|
| `wait_for_color:234,456:#3A7D44` | Pause sequence until pixel at (234,456) matches color |
| `wait_for_color:234,456:#3A7D44:30` | Same, with 30 second timeout (raises if not met) |

Implemented as `WaitForColorAction` — polls the pixel every 1 second, respects `stop_requested()` between checks, continues the sequence when the color matches. Uses `Pillow` (`PIL.ImageGrab.grab()`) for cross-platform pixel reading.

Color capture via CLI:
```bash
keydaemon capture my_macro --color
# > Hover over the pixel to watch. Press F9 to record its color.
# > Recorded: #3A7D44 at (234, 456)
```

### Randomness / Anti-Detection
| Feature | How |
|---|---|
| Timing jitter | `jitter = 30` in TOML → `random.uniform(-30, 30)` added to `every` |
| Tap duration | Default `random.uniform(0.04, 0.08)` per tap |
| Position jitter | `move_to` lands within ±5px of target by default |
| Smooth movement | Many incremental `move_by` calls with slight curve |

---

## Module Structure

```
src/keydaemon/
    __init__.py            # Public API: macro(), preset(), load(), stop_all()
    __main__.py            # python -m keydaemon (--detach respawns through this)
    _types.py              # LOOP_FOREVER = -1, GLOBAL_KILL_KEY, shared constants
    _paths.py              # platformdirs wrapper — single source of truth for data dir paths
    actions.py             # Action dataclasses (input primitives, WaitForColorAction, stop actions)
    screen.py              # Pixel reading utility (Pillow wrapper)
    scheduler.py           # Timing/iteration loop (pure — no threads)
    runner.py              # Runner lifecycle base + DaemonRunner/ExpandRunner/HotkeyRunner
    profile.py             # Profile class — owns runners + exit key + global kill listener
    builder.py             # MacroBuilder fluent API
    loader.py              # TOML → LoadedMacro (resolves do at load time)
    guard.py               # Rejects macros that bind/synthesize the emergency kill combo
    export.py              # MacroBuilder → TOML (presets install as editable TOML files)
    cli.py                 # click CLI entry point
    presets/
        __init__.py        # available() — dynamic preset discovery
        autoclicker.py     # F6 toggle / F8 exit, ~4 cps (matches examples/autoclicker.py)
        minecraft_afk.py
```

**Dependency order (no cycles):**
`_types` → `_paths` → `screen` → `actions` → `scheduler` → `runner` → `profile` ← `loader` ← `cli`
`builder` → `actions`, `_types` (lazy import of `runner` inside `.run()`)
`guard` → `actions`, `_types` (called by `loader` and `builder.run()`)
`export` → `builder`, `actions` (called by `cli`)

---

## Kill Hierarchy

### Tier 1: Global Emergency Kill
- Always enforced across ALL running profiles simultaneously (each process
  listens for it and kills itself)
- `Ctrl+Shift+Alt+F12` — complex enough to never hit accidentally
- **Hardcoded, never configurable** — it is the user's last resort and must
  always work
- **Unreachable from macros** (`guard.py`, enforced at both TOML load and
  builder `.run()`): a macro may not bind the combo as hotkey/exit_key, and
  may not synthesize it by holding its keys (press/release simulation catches
  this, left/right modifier variants included). Raises `KillKeyError`.
- Printed at startup:
```
> Emergency kill: Ctrl+Shift+Alt+F12  (or: keydaemon stop)
```

### Tier 2: Sanctioned Kill Actions (macros CAN invoke kill semantics)

The hardware combo is reserved, but the *behavior* is available through
explicit actions — built for conditional macros ("if the screen goes red,
kill all automation"):

**A) User-facing exit key** — real keypress, stops this macro's profile:
```toml
[meta]
exit_key = "f6"
```

**B) `stop:self`** (`.stop_self()` in Python) — the macro stops its own
runner and any children, releasing all held inputs. No keypress involved;
implemented as clean control flow through the runner's cascading teardown.

**C) `stop:all`** (`.kill_all()` in Python) — every macro in the process
stops, same effect as the hardware kill combo:
```toml
sequence = [
    "wait_for_color:234,456:#3A7D44",
    "click:left",
    "stop:all",
]
```

### Full Kill Reference
```
Ctrl+Shift+Alt+F12        → kills ALL profiles (always enforced, unbindable)
exit_key = "f6"           → kills this macro's profile (optional)
stop:self                 → macro stops itself + children (releases inputs)
stop:all                  → macro kills everything in the process
keydaemon stop            → CLI: kill every detached run (sweeps pids/)
keydaemon stop minecraft  → CLI: kill one detached run by name
```

Any stop path releases held inputs: mouse buttons AND keyboard keys are
tracked while held (`press:` without `release:`) and swept on stop, so a
stopped macro never leaves Shift stuck down. The one exception is an external
hard kill of a detached process (`keydaemon stop` uses taskkill) — a graceful
shutdown channel for that is v2.

---

## CLI Commands

```bash
keydaemon run afk_jump               # blocks terminal (Ctrl+C to stop)
keydaemon run afk_jump --detach      # background process, writes pids/afk_jump.pid
keydaemon run minecraft              # runs all macros in profile
keydaemon run autoclicker            # built-in preset: installs autoclicker.toml
                                     #   on first run, then runs it like any macro
keydaemon stop                       # stop every detached run (sweeps pids/)
keydaemon stop minecraft             # stop one detached run by name
keydaemon list                       # all macros + [running, PID] + built-in presets
keydaemon enable afk_jump
keydaemon disable autofill_a
keydaemon new my_macro               # scaffold loop macro (default)
keydaemon new my_macro --type expand|manual|profile
keydaemon new turbo --from autoclicker         # fork a preset under a new name
keydaemon new autoclicker --from autoclicker --force   # reset preset to defaults
keydaemon capture my_form_macro      # click-to-record mouse positions
keydaemon capture my_macro --color   # hover+F9 to record pixel color
```

`run` prints each macro's controls at startup, derived from its real bindings
("Press F6 to start/stop. Press F8 to quit.") plus its `meta.description`.

**Presets are TOML factories:** built-in presets live as Python modules, but
the CLI only ever runs TOML. First run of a preset materializes an editable
TOML into the macros dir (via `export.builder_to_toml`); the user's file wins
from then on. `--from`/`--force` regenerate or fork. A preset that uses
Python-only features (computed values etc.) fails serialization loudly and
stays Python-only.

---

## Python API

```python
import keydaemon

keydaemon.macro().every(60).jitter(10).tap("space").loop().run()
keydaemon.macro().move_by(-50, 0, smooth=True).tap("w").run()
keydaemon.macro().press("shift").tap("a").release("shift").run()
keydaemon.macro().move_to(234, 456).click().type("hello").run()

keydaemon.load("afk_jump").run()
keydaemon.load("minecraft").run()
keydaemon.preset("minecraft_afk").run()

runner = keydaemon.macro().every(30).tap("space").run()
runner.stop()
keydaemon.stop_all()
```

---

## Dependencies

```toml
dependencies = [
    "pynput>=1.7.6",       # keyboard/mouse control and listening
    "click>=8.0",           # CLI framework
    "Pillow>=10.0",         # pixel color reading (wait_for_color)
    "platformdirs>=4.0",    # OS-appropriate data directory
    "tomli>=2.0; python_version < '3.11'",  # TOML parsing backport
]
```

---

## Platform Notes

**macOS:** pynput requires Accessibility permissions. Detected at startup with a clear error message pointing to System Settings.

**TOML dates:** `created = 2026-05-31` is parsed as `datetime.date`, not `str`. Loader handles both.

**`--detach`:** Spawns `python -m keydaemon run <name>`, writes `pids/<name>.pid`
(one per name — concurrent detached runs coexist; a second run of the same name
is refused), logs to `keydaemon.log`. Liveness probing on Windows uses ctypes
`OpenProcess` — never `os.kill(pid, 0)`, which TerminateProcess-es the target.

---

## Future: v2 Conditional Branching

- `if_color:x,y:#hex` → `then` / `else` in sequences
- `repeat_until_color` with fallback actions while waiting
- Builds on `screen.py` and existing dispatch table — no rework needed
- Pairs with `stop:self` / `stop:all` for bail-out logic ("screen went red → kill everything")

## Future: v2 Misc

- `hold` hotkey mode (act while key held — needs key-release events; GlobalHotKeys only gives activate)
- Graceful shutdown for detached processes: child polls a stop-sentinel file and
  calls `stop_all()` (releasing held inputs); `keydaemon stop` escalates to
  taskkill only on timeout

## Future: GUI App (separate project)

- System tray (`pystray`), macro browser, visual editor
- `start_on_boot` (Windows registry / macOS launchd)
- Thin wrapper on top of `keydaemon` package
