"""Serialize a MacroBuilder to macro TOML — the reverse of loader._parse_action.

Built-in presets are Python (MacroBuilder code), but the CLI runs only TOML
files from the macros directory. Rather than teaching the CLI a second dispatch
path, a preset is *installed*: its builder is serialized to a normal TOML file
the user can read, edit, and re-run like any hand-written macro. Regenerating
the file (keydaemon new <name> --from <preset> --force) resets it to defaults.

Python can express things TOML can't (computed values, per-action jitter
overrides, non-default tolerances). If a preset ever uses one of those, this
module raises rather than silently dropping the detail — such a preset must
stay Python-only.
"""
from __future__ import annotations

from pathlib import Path

from keydaemon._paths import macro_path
from keydaemon._types import LOOP_FOREVER
from keydaemon.actions import (
    Action,
    ClickAction,
    KillAllAction,
    MoveByAction,
    MoveToAction,
    PressAction,
    ReleaseAction,
    ScrollAction,
    SelfStopAction,
    TapAction,
    TypeAction,
    WaitAction,
    WaitForColorAction,
)
from keydaemon.builder import MacroBuilder


def _toml_str(value: str, context: str) -> str:
    if "\n" in value:
        raise ValueError(f"{context} contains a newline — not expressible in a macro TOML string")
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _action_str(a: Action) -> str:
    """One Action back to the loader's string form (see loader._parse_action)."""
    if isinstance(a, TapAction):
        return f"tap:{a.key}" if a.duration is None else f"tap:{a.key}:{a.duration}"
    if isinstance(a, PressAction):
        return f"press:{a.key}"
    if isinstance(a, ReleaseAction):
        return f"release:{a.key}"
    if isinstance(a, TypeAction):
        return f"type:{a.text}"
    if isinstance(a, WaitAction):
        return f"wait:{a.seconds}"
    if isinstance(a, ClickAction):
        return f"click:{a.button}" if a.count == 1 else f"click:{a.button}:{a.count}"
    if isinstance(a, (MoveToAction, MoveByAction)):
        if not a.jitter:
            raise ValueError(
                "move with jitter=False can't be expressed in TOML — the loader "
                "has no syntax for it"
            )
        if isinstance(a, MoveToAction):
            base = f"move_to:{a.x},{a.y}"
        else:
            base = f"move_by:{a.dx},{a.dy}"
        return base + (":smooth" if a.smooth else "")
    if isinstance(a, ScrollAction):
        return f"scroll:{a.amount}" + (":horizontal" if a.horizontal else "")
    if isinstance(a, WaitForColorAction):
        if a.tolerance != 10:
            raise ValueError("wait_for_color with non-default tolerance can't be expressed in TOML")
        s = f"wait_for_color:{a.x},{a.y}:{a.hex_color}"
        return s if a.timeout is None else f"{s}:{a.timeout}"
    if isinstance(a, SelfStopAction):
        return "stop:self"
    if isinstance(a, KillAllAction):
        return "stop:all"
    raise ValueError(f"Action {type(a).__name__} can't be expressed in TOML")


def builder_to_toml(b: MacroBuilder, name: str, description: str = "") -> str:
    """Render a MacroBuilder as macro TOML that load_macro() reads back identically."""
    lines = ["[meta]", f"name = {_toml_str(name, 'name')}"]
    if description:
        lines.append(f"description = {_toml_str(description, 'description')}")
    if b._exit_key:
        lines.append(f'exit_key = "{b._exit_key}"')

    expansions: dict[str, str] = getattr(b, "_expansions", {}) or {}
    action_pattern = getattr(b, "_expand_pattern", None)
    is_expand = bool(expansions) or action_pattern is not None

    lines += ["", "[trigger]"]
    if is_expand:
        lines.append('type = "expand"')
        if action_pattern is not None:
            lines.append(f"pattern = {_toml_str(action_pattern, 'pattern')}")
        if expansions:
            lines += ["", "[expansions]"]
            for pattern, replacement in expansions.items():
                lines.append(
                    f"{_toml_str(pattern, 'pattern')} = {_toml_str(replacement, 'replacement')}"
                )
    elif b._hotkey:
        lines += ['type = "manual"', f'hotkey = "{b._hotkey}"', f'mode = "{b._hotkey_mode}"']
    else:
        lines.append('type = "loop"')

    if not is_expand:
        lines += ["", "[behavior]"]
        if b._interval is not None:
            lines.append(f"every = {b._interval}")
        if b._jitter:
            lines.append(f"jitter = {b._jitter}")
        lines.append(f"repeat = {-1 if b._repeat_times == LOOP_FOREVER else b._repeat_times}")

    if not is_expand or action_pattern is not None:
        lines += ["", "[actions]", "sequence = ["]
        for a in b._actions:
            lines.append(f"    {_toml_str(_action_str(a), 'action')},")
        lines += ["]", ""]
    else:
        lines.append("")
    return "\n".join(lines)


def install_preset(preset_name: str, as_name: str | None = None, force: bool = False) -> Path:
    """Materialize a built-in preset as a TOML file in the macros directory.

    as_name lets a preset be forked under a different macro name. Refuses to
    overwrite an existing file unless force=True (regeneration).
    """
    import importlib

    import keydaemon
    from keydaemon.presets import available

    names = available()
    if preset_name not in names:
        raise ValueError(
            f"No built-in preset named {preset_name!r}. Available: {', '.join(names)}"
        )
    as_name = as_name or preset_name
    path = macro_path(as_name)
    if path.exists() and not force:
        raise FileExistsError(f"{path} already exists (use --force to overwrite)")

    builder = keydaemon.preset(preset_name)
    mod = importlib.import_module(f"keydaemon.presets.{preset_name}")
    doc = mod.__doc__ or ""
    description = next((ln.strip() for ln in doc.splitlines() if ln.strip()), "")
    path.write_text(builder_to_toml(builder, name=as_name, description=description), encoding="utf-8")
    return path
