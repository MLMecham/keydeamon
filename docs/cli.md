# CLI Guide

The CLI runs macros defined as TOML files in your OS data directory (`%LOCALAPPDATA%\keydaemon\keydaemon\macros\` on Windows). One file per macro, editable in any text editor.

```bash
keydaemon --help            # every command
keydaemon <command> --help  # details for one
```

## Running things

```bash
keydaemon run my_macro               # foreground — Ctrl+C to stop
keydaemon run my_macro --detach      # background process
keydaemon run minecraft              # a profile: starts all its macros together
keydaemon run autoclicker            # a built-in preset (see below)
```

Every run prints the macro's controls, derived from its **actual** bindings — edit `hotkey = "f6"` to `"f9"` in the TOML and the startup message says ++f9++ automatically:

```text
Emergency kill: <ctrl>+<shift>+<alt>+<f12>  (or: keydaemon stop)
Autoclicker preset.
Press F6 to start/stop. Press F8 to quit.
Running 'autoclicker'. Ctrl+C to stop.
```

## Built-in presets install as TOML

The CLI only ever runs TOML — presets are *factories* for TOML files. The first `keydaemon run autoclicker` generates `autoclicker.toml` into your macros dir and runs it; from then on **your file wins**, so customizing a preset is just editing a file.

```bash
keydaemon new turbo --from autoclicker           # fork a preset under a new name
keydaemon new autoclicker --from autoclicker --force   # reset one to defaults
```

| Preset | What it does |
|---|---|
| `autoclicker` | ++f6++ toggles ~4 cps left-clicking (with jitter), ++f8++ quits |
| `minecraft_afk` | Singleplayer anti-AFK: step forward/back + jump every ~4.5 min |

## Stopping and listing

```bash
keydaemon list            # macros, profiles, [running, PID] status, presets
keydaemon stop clicker    # stop one detached run
keydaemon stop            # stop all detached runs
```

Detached runs get one PID file each (`pids/<name>.pid`), so they coexist and stop independently. Starting the same name twice is refused. Stale PID files (process already gone) are cleaned automatically.

## Creating macros

```bash
keydaemon new my_macro                  # blank loop macro (default)
keydaemon new my_macro --type manual    # hotkey-armed macro
keydaemon new my_macro --type expand    # text expansion
keydaemon new my_session --type profile # run several macros together
keydaemon capture my_macro              # click-to-record mouse positions
keydaemon capture my_macro --color      # hover + F9 to record pixel colors
keydaemon enable my_macro / disable my_macro
```

## TOML anatomy

```toml
[meta]
name = "AFK Jump"
description = "Keeps you active in Minecraft singleplayer"  # printed at startup
exit_key = "f8"            # optional: press to stop this macro

[trigger]
type = "loop"              # loop | manual | expand | profile
# hotkey = "f6"            # manual only: arm behind a hotkey
# mode = "toggle"          # toggle (press start/press stop) or once

[behavior]
every = 270                # seconds between runs
jitter = 30                # ± random seconds (anti-detection)
repeat = -1                # -1 = forever, N = run N times

[actions]
sequence = [
    "tap:space",
    "wait:0.1",
    "tap:w",
]
```

### Action vocabulary

| Syntax | Does |
|---|---|
| `tap:w` / `tap:w:0.15` | Press + release (random 40–80 ms hold, or explicit) |
| `press:shift` / `release:shift` | Hold / release a key or mouse button |
| `type:hello world` | Type a string |
| `wait:0.5` | Pause |
| `click:left` / `click:left:2` | Click / double-click |
| `move_to:500,300` / `move_to:500,300:smooth` | Absolute cursor move (±5 px jitter) |
| `move_by:-50,0` | Relative move (drags, camera) |
| `scroll:3` / `scroll:3:horizontal` | Scroll |
| `wait_for_color:234,456:#3A7D44` / `...:#3A7D44:30` | Pause until a pixel matches (optional timeout) |
| `stop:self` / `stop:all` | The macro stops itself / everything ([safety](safety.md)) |
| `do:other_macro` | Inline another macro's sequence (flattened at load, cycles rejected) |
