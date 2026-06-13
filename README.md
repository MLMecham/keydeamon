# keydaemon

A lightweight, programmable keyboard/mouse automation daemon for personal use — a clean Python API and CLI instead of a GUI macro recorder. It runs quietly in the background: text expansion, anti-AFK loops, form filling, autoclickers, drawing, and pixel-watching.

> **Not for** kernel-level anti-cheat games (Valorant, Fortnite, PUBG). **Fine for** Minecraft, singleplayer/private servers, productivity, and desktop automation.

---

## Install

```bash
uv sync --extra dev      # install with dev/test dependencies
uv run pytest            # run the test suite
uv run keydaemon --help  # the CLI
```

Dependencies: `pynput` (input), `Pillow` (pixel color), `platformdirs` (data dir), `click` (CLI).

---

## Quick start

### Python API — the fluent builder

Everything is built with `keydaemon.macro()` and runs when you call `.run()`:

```python
import keydaemon

# Press space every 60s (±5s jitter), forever:
keydaemon.macro().every(60).jitter(5).tap("space").loop().run()

# Hold shift, tap A, release shift:
keydaemon.macro().press("shift").tap("a").release("shift").run()

# Move, click, and type:
keydaemon.macro().move_to(234, 456).click().type("hello").run()
```

`.run()` returns a runner. Keep the process alive with `.join()`, or stop early with `.stop()`:

```python
runner = keydaemon.macro().every(30).tap("space").loop().run()
runner.stop()          # stop this macro
keydaemon.stop_all()   # stop everything, everywhere
```

### Autoclicker (toggle hotkey)

The autoclicker is armed behind a hotkey: it sits idle until you press the toggle key, clicks while on, and toggles off on the next press — the process stays alive the whole time.

```python
import keydaemon
keydaemon.preset("autoclicker").run().join()
```

- **O** → start/stop clicking (hover your cursor over the target first)
- **Esc** → quit

Run it straight from the preset file:

```bash
uv run python -m keydaemon.presets.autoclicker
```

Or use the configurable script (clicks-per-second, button, double-click, keys) in [`examples/autoclicker.py`](examples/autoclicker.py).

---

## Triggers — *when* a macro fires

| Trigger | How it starts | Builder / TOML |
|---|---|---|
| **Loop** | Immediately, on a timer | `.every(s).loop()` — `type = "loop"` |
| **Hotkey** | When you press a key (toggle or once) | `.hotkey(key, mode)` — `type = "manual"`, `hotkey`, `mode` |
| **Expand** | When you type a text pattern | `type = "expand"`, `pattern` |
| **Profile** | Starts several macros together | `type = "profile"`, `macros.run = [...]` |

### Hotkey toggle in detail

```python
# Press F6 to start the loop, press F6 again to stop. Esc quits the program.
keydaemon.macro().every(0.1).click("left").loop().hotkey("f6").exit_key("esc").run().join()
```

- `mode="toggle"` (default) — same key starts and stops, repeatedly.
- `mode="once"` — each press fires the loop a single time.

Because the program stays armed between presses, the toggle key *is* your start button — there's no startup countdown to race.

---

## Tools — *what* a macro does (actions)

### Keyboard
| Builder | Description |
|---|---|
| `.tap("w")` | Press + release (random 40–80 ms hold by default) |
| `.tap("w", 0.15)` | Press + release with an explicit hold |
| `.press("shift")` | Press and hold (until released) |
| `.release("shift")` | Release a held key |
| `.type("hello world")` | Type a string |
| `.sequence(["w","a","s","d"])` | Tap several keys in order |

### Mouse
| Builder | Description |
|---|---|
| `.move_to(x, y)` | Teleport cursor to an absolute position (±5 px jitter) |
| `.move_by(dx, dy)` | Relative move (use while a button is held, for drags) |
| `.move_to(x, y, smooth=True)` | Curved, multi-step movement |
| `.click("left")` | Click at the current position |
| `.click("left", count=2)` | Double-click |
| `.scroll(3)` / `.scroll(-3)` | Scroll down / up |
| `.drag_to(x1,y1,x2,y2)` | Move, hold left, smooth-drag, release |

`press`/`release` work for both keys and mouse buttons (`"left"`, `"right"`, `"middle"`).

### Screen conditions
| Builder | Description |
|---|---|
| `.wait_for_color(x, y, "#3A7D44")` | Pause until the pixel matches a color |
| `.wait_for_color(x, y, "#3A7D44", timeout=30)` | Same, but raise after 30 s |

### Timing & anti-detection
| Builder | Description |
|---|---|
| `.every(seconds)` | Delay between loop iterations |
| `.jitter(seconds)` | ± random wobble added to the interval |
| `.loop()` / `.loop(n)` | Run forever / `n` times |
| `.repeat(n)` | Alias for a finite count |

Tap durations and `move_to` landing points are randomized by default, so output isn't perfectly robotic.

---

## Stopping safely

keydaemon is built so a runaway thread can't survive. Every runner auto-registers in a global backstop, and `stop()` is idempotent and cascades to any child it owns.

| Key / call | Scope |
|---|---|
| `exit_key("esc")` | Stop this macro/profile |
| Toggle hotkey (e.g. `O`) | Pause/resume the clicker (program stays alive) |
| **Ctrl + Shift + Alt + F12** | Emergency kill — stops **every** macro, always |
| `keydaemon.stop_all()` / `keydaemon stop` | Stop everything |

When a macro stops, only mouse buttons it was actually *holding* are released — so a plain clicker sends no stray events on stop.

---

## CLI

Macros live as TOML files in your OS data dir (`%APPDATA%\keydaemon\macros\` on Windows).

```bash
keydaemon run my_macro              # run a macro or profile (Ctrl+C to stop)
keydaemon run my_macro --detach     # run in the background
keydaemon stop                      # stop all
keydaemon list                      # list macros and profiles
keydaemon new my_macro --type manual  # scaffold a hotkey macro (loop/expand/manual/profile)
keydaemon capture my_macro          # click-to-record mouse positions
keydaemon capture my_macro --color  # hover + F9 to record pixel colors
keydaemon enable my_macro / disable my_macro
```

A hotkey-toggle clicker as a TOML macro (`keydaemon new clicker --type manual`):

```toml
[trigger]
type = "manual"
hotkey = "f6"      # press to start/stop
mode = "toggle"

[behavior]
every = 0.1
jitter = 0.02
repeat = -1        # -1 = loop until toggled off

[actions]
sequence = ["click:left"]
```

---

## Built-in presets

| Preset | What it does |
|---|---|
| `autoclicker` | Toggle-hotkey left-clicker (O toggles, Esc quits) |
| `minecraft_afk` | Singleplayer anti-AFK: nudge forward/back/jump every ~4.5 min |

```python
keydaemon.preset("autoclicker").run().join()
keydaemon.preset("minecraft_afk").run()
```

---

## Examples

- [`examples/autoclicker.py`](examples/autoclicker.py) — configurable autoclicker (rate, button, keys)
- [`examples/flower.py`](examples/flower.py) — draws a rose-curve flower in a browser sketch app

See [`PLAN.md`](PLAN.md) for the full architecture and design notes.
