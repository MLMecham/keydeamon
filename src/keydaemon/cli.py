from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

import click

from keydaemon._paths import macro_path, macros_dir, pid_file, pids_dir, log_file
from keydaemon._types import GLOBAL_KILL_KEY


MACRO_TEMPLATES = {
    "loop": """\
[meta]
name = "{name}"
description = ""
tags = []
enabled = true
start_on_boot = false

[trigger]
type = "loop"

[behavior]
every = 60       # seconds between runs
jitter = 5       # ± random seconds (anti-detection)
repeat = -1      # -1 = forever, N = run N times

[actions]
sequence = [
    # "tap:space",
    # "wait:0.1",
]
""",
    "expand": """\
[meta]
name = "{name}"
description = ""
tags = []
enabled = true
start_on_boot = false

[trigger]
type = "expand"

# Your snippet bank: type a pattern anywhere and it becomes the replacement.
# Add as many as you like — they all share one keyboard listener.
[expansions]
"///{name}" = "your replacement text here"
# "///sig" = "Your Name | you@example.com"
# "///gg"  = "good game, well played!"
""",
    "manual": """\
[meta]
name = "{name}"
description = ""
tags = []
enabled = true
start_on_boot = false

[trigger]
type = "manual"
hotkey = "f6"      # press this key to start/stop the sequence
mode = "toggle"    # "toggle" = press to start, press again to stop; "once" = fire once per press

[behavior]
every = 0.1        # seconds between repeats (omit for a single pass)
jitter = 0.02      # ± random seconds
repeat = -1        # -1 = loop until toggled off, N = run N times

[actions]
sequence = [
    # "move_to:500,300",
    # "click:left",
    # "wait:0.5",
]
""",
    "profile": """\
[meta]
name = "{name}"
type = "profile"
exit_key = "f11"   # press this key to stop all macros in this profile
start_on_boot = false

[macros]
run = [
    # "macro_one",
    # "macro_two",
]
""",
}


@click.group()
@click.version_option(package_name="keydaemon")
def main() -> None:
    """keydaemon - background daemon for keyboard/mouse automation."""


@main.command()
@click.argument("name")
@click.option("--detach", is_flag=True, help="Run in background (detached from terminal).")
def run(name: str, detach: bool) -> None:
    """Run a macro, profile, or built-in preset by name.

    TOML files in the macros directory always win; a built-in preset of that
    name is installed as a TOML on first run so it can be edited like any macro.
    """
    if detach:
        _run_detached(name)
        return

    from keydaemon.loader import is_profile, load_macro, load_profile
    from keydaemon.profile import Profile, stop_all
    from keydaemon.runner import make_runner

    _ensure_macro_exists(name)
    click.echo(f"Emergency kill: {GLOBAL_KILL_KEY}  (or: keydaemon stop)")

    if is_profile(name):
        macro_names = load_profile(name)
        p = Profile(name=name)
        loaded = [load_macro(mname) for mname in macro_names]
        for lm in loaded:
            p.add_runner(make_runner(lm))
        p.start()
        click.echo(f"Running profile '{name}' with {len(macro_names)} macro(s). Ctrl+C to stop.")
        for lm in loaded:
            controls = _controls_line(lm)
            if controls:
                click.echo(f"  {lm.name}: {controls}")
    else:
        lm = load_macro(name)
        p = Profile(name=name, exit_key=lm.exit_key)
        p.add_runner(make_runner(lm))
        p.start()
        if lm.description:
            click.echo(lm.description)
        controls = _controls_line(lm)
        if controls:
            click.echo(controls)
        click.echo(f"Running '{name}'. Ctrl+C to stop.")

    try:
        import time
        while p.is_running:
            time.sleep(0.5)
    except KeyboardInterrupt:
        click.echo("\nStopping...")
        stop_all()


@main.command()
@click.argument("name", required=False)
def stop(name: str | None) -> None:
    """Stop a detached macro/profile by name, or all of them if no name given."""
    if name is not None:
        _stop_one(pid_file(name), name)
        return
    files = sorted(pids_dir().glob("*.pid"))
    if not files:
        click.echo("No running keydaemon processes found.")
        return
    for f in files:
        _stop_one(f, f.stem)


@main.command(name="list")
def list_macros() -> None:
    """List all macros in the keydaemon data directory."""
    from keydaemon.loader import list_macros, is_profile
    names = list_macros()
    if not names:
        click.echo(f"No macros in {macros_dir()} — only built-in presets:")
    for name in names:
        tag = " [profile]" if is_profile(name) else ""
        pid = _read_pid(pid_file(name))
        if pid is not None:
            if _pid_alive(pid):
                tag += f" [running, PID {pid}]"
            else:
                pid_file(name).unlink(missing_ok=True)  # stale — process is gone
        click.echo(f"  {name}{tag}")
    from keydaemon.presets import available
    for pname in available():
        if pname not in names:
            click.echo(f"  {pname} [built-in preset - installs as TOML on first run]")


@main.command()
@click.argument("name")
@click.option("--type", "macro_type", default="loop",
              type=click.Choice(["loop", "expand", "manual", "profile"]),
              help="Type of macro to scaffold.")
@click.option("--from", "from_preset", default=None, metavar="PRESET",
              help="Generate from a built-in preset instead of a blank template.")
@click.option("--force", is_flag=True,
              help="Overwrite an existing macro file (e.g. to reset a preset to defaults).")
def new(name: str, macro_type: str, from_preset: str | None, force: bool) -> None:
    """Create a new macro file from a template or a built-in preset."""
    if from_preset is not None:
        from keydaemon.export import install_preset
        try:
            path = install_preset(from_preset, as_name=name, force=force)
        except (ValueError, FileExistsError) as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
        click.echo(f"Created {path} from preset '{from_preset}'")
        return
    path = macro_path(name)
    if path.exists() and not force:
        click.echo(f"Error: {path} already exists (use --force to overwrite).", err=True)
        sys.exit(1)
    content = MACRO_TEMPLATES[macro_type].format(name=name)
    path.write_text(content, encoding="utf-8")
    click.echo(f"Created {path}")


@main.command()
@click.argument("name")
@click.option("--color", "color_mode", is_flag=True, help="Record pixel color instead of click positions.")
def capture(name: str, color_mode: bool) -> None:
    """Record mouse click positions or pixel colors into a macro file."""
    if color_mode:
        _capture_color(name)
    else:
        _capture_clicks(name)


@main.command()
@click.argument("name")
def enable(name: str) -> None:
    """Set enabled = true in a macro file."""
    _set_enabled(name, True)


@main.command()
@click.argument("name")
def disable(name: str) -> None:
    """Set enabled = false in a macro file."""
    _set_enabled(name, False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_key(key: str) -> str:
    """Human display for a key binding: 'f6' -> 'F6', '<ctrl>+x' -> 'CTRL+X'."""
    return "+".join(part.strip("<>").upper() for part in key.split("+"))


def _controls_line(lm) -> str:
    """Describe a LoadedMacro's controls, derived from its actual bindings so
    the text can never disagree with what the keys really do."""
    parts: list[str] = []
    if lm.trigger_type == "expand":
        expansions = getattr(lm, "expansions", {}) or {}
        if expansions:
            parts.append(
                "Expansions armed: " + ", ".join(f"'{p}'" for p in expansions) + "."
            )
        if lm.expand_pattern:
            parts.append(f"Type '{lm.expand_pattern}' to trigger.")
    if lm.hotkey:
        if lm.hotkey_mode == "once":
            parts.append(f"Press {_fmt_key(lm.hotkey)} to fire once per press.")
        else:
            parts.append(f"Press {_fmt_key(lm.hotkey)} to start/stop.")
    elif lm.trigger_type != "expand":
        parts.append("Starts immediately.")
    if lm.exit_key:
        parts.append(f"Press {_fmt_key(lm.exit_key)} to quit.")
    return " ".join(parts)


def _ensure_macro_exists(name: str) -> None:
    """Make sure `run` has a TOML to load: install the built-in preset of that
    name on first run, or exit with an error naming what IS available."""
    if macro_path(name).exists():
        return
    from keydaemon.presets import available

    presets = available()
    if name not in presets:
        click.echo(
            f"Error: no macro or built-in preset named '{name}'.\n"
            f"Macros dir: {macros_dir()}\n"
            f"Built-in presets: {', '.join(presets)}",
            err=True,
        )
        sys.exit(1)
    from keydaemon.export import install_preset

    path = install_preset(name)
    click.echo(f"First run of built-in preset '{name}' - installed {path}")
    click.echo(f"Edit that file to customize; reset it with: keydaemon new {name} --from {name} --force")


def _run_detached(name: str) -> None:
    _ensure_macro_exists(name)
    pf = pid_file(name)
    existing = _read_pid(pf)
    if existing is not None and _pid_alive(existing):
        click.echo(
            f"Error: '{name}' is already running (PID {existing}). "
            f"Stop it first: keydaemon stop {name}",
            err=True,
        )
        sys.exit(1)

    cmd = [sys.executable, "-m", "keydaemon", "run", name]
    log = log_file().open("a")
    if sys.platform == "win32":
        proc = subprocess.Popen(
            cmd,
            stdout=log,
            stderr=log,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    else:
        proc = subprocess.Popen(cmd, stdout=log, stderr=log, start_new_session=True)
    pf.write_text(str(proc.pid))
    click.echo(f"Running '{name}' in background. PID: {proc.pid}")
    click.echo(f"Emergency kill: {GLOBAL_KILL_KEY}  (or: keydaemon stop {name})")
    click.echo(f"Logs: {log_file()}")


def _read_pid(pf: Path) -> int | None:
    if not pf.exists():
        return None
    try:
        return int(pf.read_text().strip())
    except (ValueError, OSError):
        return None


def _pid_alive(pid: int) -> bool:
    """True if a process with this PID is still running.

    NEVER use os.kill(pid, 0) on Windows — any sig other than the two console
    events calls TerminateProcess, i.e. it would KILL the process we're probing.
    """
    if sys.platform == "win32":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return bool(ok) and code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, just not ours


def _kill_pid(pid: int) -> None:
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False, capture_output=True)
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def _stop_one(pf: Path, name: str) -> None:
    pid = _read_pid(pf)
    if pid is None:
        click.echo(f"No running process for '{name}'.")
        return
    if _pid_alive(pid):
        _kill_pid(pid)
        click.echo(f"Stopped '{name}' (PID {pid}).")
    else:
        click.echo(f"'{name}' was already stopped (cleaning up stale PID {pid}).")
    pf.unlink(missing_ok=True)


def _capture_clicks(name: str) -> None:
    from pynput.mouse import Listener, Button
    from pynput.keyboard import Listener as KBListener, Key

    recorded: list[str] = []
    done = False

    click.echo("Click positions to record. Press ESC when done.")

    def on_click(x, y, button, pressed):
        if pressed and button == Button.left:
            step = f"move_to:{x},{y}"
            recorded.append(step)
            recorded.append("click:left")
            click.echo(f"  Recorded: click at ({x}, {y})")

    def on_key(key):
        nonlocal done
        if key == Key.esc:
            done = True
            return False

    with Listener(on_click=on_click) as ml, KBListener(on_press=on_key) as kl:
        kl.join()

    if not recorded:
        click.echo("Nothing recorded.")
        return

    path = macro_path(name)
    sequence_lines = "\n".join(f'    "{s}",' for s in recorded)
    content = MACRO_TEMPLATES["manual"].format(name=name)
    content = content.replace(
        "    # \"move_to:500,300\",\n    # \"click:left\",\n    # \"wait:0.5\",",
        sequence_lines,
    )
    path.write_text(content, encoding="utf-8")
    click.echo(f"Saved {len(recorded) // 2} click(s) to {path}")


def _capture_color(name: str) -> None:
    from pynput.keyboard import Listener, Key
    from keydaemon.screen import get_pixel_hex

    recorded: list[tuple[int, int, str]] = []

    click.echo("Hover over a pixel and press F9 to record its color. ESC when done.")

    def on_key(key):
        if key == Key.f9:
            from pynput.mouse import Controller
            x, y = Controller().position
            hex_color = get_pixel_hex(int(x), int(y))
            recorded.append((int(x), int(y), hex_color))
            click.echo(f"  Recorded: {hex_color} at ({int(x)}, {int(y)})")
        elif key == Key.esc:
            return False

    with Listener(on_press=on_key) as kl:
        kl.join()

    if not recorded:
        click.echo("Nothing recorded.")
        return

    path = macro_path(name)
    sequence_lines = "\n".join(
        f'    "wait_for_color:{x},{y}:{c}",' for x, y, c in recorded
    )
    content = MACRO_TEMPLATES["manual"].format(name=name)
    content = content.replace(
        "    # \"move_to:500,300\",\n    # \"click:left\",\n    # \"wait:0.5\",",
        sequence_lines,
    )
    path.write_text(content, encoding="utf-8")
    click.echo(f"Saved {len(recorded)} color check(s) to {path}")


def _set_enabled(name: str, value: bool) -> None:
    path = macro_path(name)
    if not path.exists():
        click.echo(f"Error: macro '{name}' not found.", err=True)
        sys.exit(1)
    text = path.read_text(encoding="utf-8")
    val_str = "true" if value else "false"
    opposite = "false" if value else "true"
    if f"enabled = {opposite}" in text:
        text = text.replace(f"enabled = {opposite}", f"enabled = {val_str}")
    elif f"enabled = {val_str}" not in text:
        text = text.replace("[meta]", f"[meta]\nenabled = {val_str}")
    path.write_text(text, encoding="utf-8")
    click.echo(f"{'Enabled' if value else 'Disabled'} '{name}'.")
