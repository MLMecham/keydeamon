from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

import click

from keydaemon._paths import macro_path, macros_dir, pid_file, log_file
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
pattern = "///{name}"

[behavior]
replace = "your replacement text here"
# OR to run a sub-macro instead of typing text:
# do = "macro_name"
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
# hotkey = "f6"   # optional: press this key to trigger

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
    """keydaemon — background daemon for keyboard/mouse automation."""


@main.command()
@click.argument("name")
@click.option("--detach", is_flag=True, help="Run in background (detached from terminal).")
def run(name: str, detach: bool) -> None:
    """Run a macro or profile by name."""
    if detach:
        _run_detached(name)
        return

    from keydaemon._paths import macro_path
    from keydaemon.loader import is_profile, load_macro, load_profile
    from keydaemon.profile import Profile, stop_all
    from keydaemon.runner import DaemonRunner, ExpandRunner

    click.echo(f"Emergency kill: {GLOBAL_KILL_KEY}  (or: keydaemon stop)")

    if is_profile(name):
        macro_names = load_profile(name)
        p = Profile(name=name)
        for mname in macro_names:
            lm = load_macro(mname)
            if lm.trigger_type == "expand":
                runner = ExpandRunner(
                    pattern=lm.expand_pattern or "",
                    replace=lm.expand_replace,
                    actions=lm.actions if not lm.expand_replace else None,
                )
            else:
                runner = DaemonRunner(
                    actions=lm.actions,
                    interval=lm.interval,
                    repeat_times=lm.repeat_times,
                    jitter=lm.jitter,
                )
            p.add_runner(runner)
        p.start()
        click.echo(f"Running profile '{name}' with {len(macro_names)} macro(s). Ctrl+C to stop.")
    else:
        lm = load_macro(name)
        if lm.trigger_type == "expand":
            runner = ExpandRunner(
                pattern=lm.expand_pattern or "",
                replace=lm.expand_replace,
                actions=lm.actions if not lm.expand_replace else None,
            )
            p = Profile(name=name, exit_key=lm.exit_key)
            p.add_runner(runner)
            p.start()
        else:
            runner = DaemonRunner(
                actions=lm.actions,
                interval=lm.interval,
                repeat_times=lm.repeat_times,
                jitter=lm.jitter,
            )
            p = Profile(name=name, exit_key=lm.exit_key)
            p.add_runner(runner)
            p.start()
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
    """Stop all running macros, or a specific profile by name."""
    pid = _read_pid()
    if pid:
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False, capture_output=True)
            else:
                os.kill(pid, signal.SIGTERM)
            pid_file().unlink(missing_ok=True)
            click.echo("Stopped.")
        except ProcessLookupError:
            pid_file().unlink(missing_ok=True)
            click.echo("No process found (already stopped).")
    else:
        click.echo("No running keydaemon process found.")


@main.command(name="list")
def list_macros() -> None:
    """List all macros in the keydaemon data directory."""
    from keydaemon.loader import list_macros, is_profile
    names = list_macros()
    if not names:
        click.echo(f"No macros found in {macros_dir()}")
        return
    for name in names:
        tag = " [profile]" if is_profile(name) else ""
        click.echo(f"  {name}{tag}")


@main.command()
@click.argument("name")
@click.option("--type", "macro_type", default="loop",
              type=click.Choice(["loop", "expand", "manual", "profile"]),
              help="Type of macro to scaffold.")
def new(name: str, macro_type: str) -> None:
    """Create a new macro file from a template."""
    path = macro_path(name)
    if path.exists():
        click.echo(f"Error: {path} already exists.", err=True)
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

def _run_detached(name: str) -> None:
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
    pid_file().write_text(str(proc.pid))
    click.echo(f"Running '{name}' in background. PID: {proc.pid}")
    click.echo(f"Emergency kill: {GLOBAL_KILL_KEY}  (or: keydaemon stop)")
    click.echo(f"Logs: {log_file()}")


def _read_pid() -> int | None:
    p = pid_file()
    if not p.exists():
        return None
    try:
        return int(p.read_text().strip())
    except (ValueError, OSError):
        return None


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
