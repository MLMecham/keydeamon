# Changelog

<!--next-version-placeholder-->

## Unreleased

- `.do("name")` on `MacroBuilder` — Python twin of the TOML `do:` verb.
  Stored as a reference: `.run()` reads the target macro's TOML fresh each
  time (edits to the target take effect on the next run) and flattens it
  before the kill-key guard, so a sub-macro can't smuggle in kill-combo keys;
  `.save()` writes `do:name` so saved macros stay composable.
- Fixed: `do:` targeting a profile declared via `[meta] type = "profile"`
  (rather than `[trigger]`) silently flattened to zero actions instead of
  being rejected.

## v0.1.0 (16/07/2026)

First release of `keydaemon` — a lightweight, programmable input automation
daemon: a clean Python API and CLI alternative to GUI macro recorders like
AutoHotkey. Loop macros, text expansion, hotkey-armed sequences, and pixel
color conditions, defined in TOML files or a fluent Python builder.

### Engine
- Fluent `MacroBuilder` API: taps, holds, typing, mouse movement (teleport,
  relative, smooth), clicks, scrolling, drag sugar, `wait_for_color` pixel
  conditions, timing jitter throughout for natural variance.
- TOML macro files (one per macro) with `do:` sub-macro composition,
  flattened at load time with cycle detection.
- Runner lifecycle tree: every runner auto-registers in a global backstop,
  `stop()` is idempotent and cascades children-first — runaway threads are
  impossible by construction.
- Hotkey trigger (`toggle` / `once` modes): arm a macro behind a global
  hotkey; the process stays alive between presses.

### Safety
- Emergency kill combo (`Ctrl+Shift+Alt+F12`) stops everything, always.
  Hardcoded and unreachable from macros: the loader and builder reject any
  macro that binds it or synthesizes it by holding its keys.
- Sanctioned kill actions instead: `stop:self` (this macro + its children)
  and `stop:all` (everything in the process), also as `.stop_self()` /
  `.kill_all()` in Python.
- Every stop path releases held inputs — mouse buttons and keyboard keys are
  tracked while held and swept on stop; no stuck Shift key, and no spurious
  release events for inputs that were never held.

### CLI
- `keydaemon run <name>` for macros, profiles, and built-in presets — a
  preset installs itself as an editable TOML on first run, and prints its
  controls ("Press F6 to start/stop. Press F8 to quit.") derived from its
  actual bindings.
- `--detach` background runs with one PID file per name: concurrent detached
  macros, `keydaemon stop <name>` for one, bare `keydaemon stop` for all,
  stale PID cleanup, refusal to double-start a name.
- `keydaemon list` shows macros, profiles, live running status with PID, and
  uninstalled built-in presets.
- `keydaemon new <name>` templates (loop/expand/manual/profile), plus
  `--from <preset>` to fork a preset under any name and `--force` to reset
  one to defaults.
- `keydaemon capture` records mouse click positions or pixel colors into a
  macro file.

### Presets
- `autoclicker` — F6 toggles ~4 cps left-clicking with timing jitter, F8 quits.
- `minecraft_afk` — anti-AFK step/jump every ~4.5 minutes (singleplayer use).
