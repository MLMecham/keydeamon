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
    afk_jump.toml          ← loop macro
    autofill_a.toml        ← expand listener
    open_inventory.toml    ← manual macro (used as do sub-sequence)
    farm_sequence.toml     ← loop macro (uses do:open_inventory)
    minecraft.toml         ← profile (starts multiple macros concurrently)
    productivity.toml      ← profile
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
    _types.py              # LOOP_FOREVER = -1, shared constants
    _paths.py              # platformdirs wrapper — single source of truth for data dir paths
    actions.py             # Action dataclasses (all input primitives + WaitForColorAction)
    screen.py              # Pixel reading utility (Pillow wrapper)
    scheduler.py           # Timing/iteration loop (pure — no threads)
    runner.py              # DaemonRunner + ExpandRunner
    profile.py             # Profile class — owns registry + exit key + stop_all()
    builder.py             # MacroBuilder fluent API
    loader.py              # TOML → MacroBuilder (resolves do at load time)
    cli.py                 # click CLI entry point
    presets/
        __init__.py
        minecraft_afk.py
```

**Dependency order (no cycles):**
`_types` → `_paths` → `screen` → `actions` → `scheduler` → `runner` → `profile` ← `loader` ← `cli`
`builder` → `actions`, `_types` (lazy import of `runner` inside `.run()`)

---

## Kill Hierarchy

### Tier 1: Global Emergency Kill
- Always enforced across ALL running profiles simultaneously
- Default: `Ctrl+Shift+Alt+F12` — complex enough to never hit accidentally
- No macro sequence can use this key — loader rejects any file that tries
- Configurable in `config.toml` but always active
- Printed at startup:
```
> Emergency kill: Ctrl+Shift+Alt+F12  (or: keydaemon stop)
```

### Tier 2: Per-Macro Self-Kill

**A) User-facing exit key** — real keypress, stops just this macro:
```toml
[meta]
exit_key = "f6"
```

**B) Programmatic self-stop** — internal UUID token, no keypress:
```toml
sequence = [
    "wait_for_color:234,456:#3A7D44",
    "click:left",
    "stop:self",
]
```
Each macro gets a UUID at load time. `stop:self` fires that token — impossible to conflict, no keypress, paves way for future conditional logic.

### Full Kill Reference
```
Ctrl+Shift+Alt+F12        → kills ALL profiles (always enforced)
exit_key = "f6"           → kills just this macro (optional)
stop:self                 → macro stops itself (UUID token)
keydaemon stop            → CLI: kill all
keydaemon stop minecraft  → CLI: kill one profile
```

---

## CLI Commands

```bash
keydaemon run afk_jump               # blocks terminal (Ctrl+C to stop)
keydaemon run afk_jump --detach      # spawns background process, writes PID file
keydaemon run minecraft              # runs all macros in profile
keydaemon run minecraft --detach
keydaemon stop                       # stop all (reads PID file)
keydaemon stop minecraft             # stop one named profile
keydaemon list                       # show all macros + running status
keydaemon enable afk_jump
keydaemon disable autofill_a
keydaemon new my_macro               # scaffold loop macro (default)
keydaemon new my_macro --type expand
keydaemon new my_macro --type manual
keydaemon new my_session --type profile
keydaemon capture my_form_macro      # click-to-record mouse positions
keydaemon capture my_macro --color   # hover+F9 to record pixel color
```

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

**`--detach`:** Spawns a subprocess, writes PID file to data dir, logs to `keydaemon.log`.

---

## Future: v2 Conditional Branching

- `if_color:x,y:#hex` → `then` / `else` in sequences
- `repeat_until_color` with fallback actions while waiting
- Builds on `screen.py` and existing dispatch table — no rework needed

## Future: GUI App (separate project)

- System tray (`pystray`), macro browser, visual editor
- `start_on_boot` (Windows registry / macOS launchd)
- Thin wrapper on top of `keydaemon` package
