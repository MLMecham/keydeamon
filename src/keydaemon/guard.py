"""Load-time protection for the emergency kill key.

GLOBAL_KILL_KEY is the one input that must always work: it is the user's
last resort when a macro floods the machine with synthetic events. Macros
therefore may not bind it as a hotkey/exit key, and may not synthesize the
combo by pressing its keys — either would shadow or hijack the escape hatch.

Macros that legitimately want kill semantics have sanctioned actions instead:
``stop:self`` / ``.stop_self()`` (this macro and its children) and
``stop:all`` / ``.kill_all()`` (every macro in the process).

Both the TOML loader and MacroBuilder.run() call ensure_kill_key_unreachable(),
so there is no path into a running macro that skips this check.
"""
from __future__ import annotations

from keydaemon._types import GLOBAL_KILL_KEY
from keydaemon.actions import Action, PressAction, ReleaseAction, TapAction

# Left/right variants count as the modifier itself — pynput's GlobalHotKeys
# treats <ctrl> as matching either physical key, so the guard must too.
_ALIASES = {
    "ctrl_l": "ctrl",
    "ctrl_r": "ctrl",
    "control": "ctrl",
    "shift_l": "shift",
    "shift_r": "shift",
    "alt_l": "alt",
    "alt_r": "alt",
    "alt_gr": "alt",
}


def _normalize_key(key: str) -> str:
    key = key.strip().lower().strip("<>")
    return _ALIASES.get(key, key)


def _combo_keys(combo: str) -> frozenset[str]:
    return frozenset(_normalize_key(part) for part in combo.split("+"))


_KILL_COMBO = _combo_keys(GLOBAL_KILL_KEY)


class KillKeyError(ValueError):
    """A macro tried to bind or synthesize the emergency kill combo."""


def _reject(name: str, how: str) -> None:
    raise KillKeyError(
        f"Macro {name!r} {how} the emergency kill combo ({GLOBAL_KILL_KEY}). "
        f"That combo is reserved so it always works. To stop macros from "
        f"within a macro, use the 'stop:self' / 'stop:all' actions "
        f"(.stop_self() / .kill_all() in Python) instead."
    )


def ensure_kill_key_unreachable(
    actions: list[Action],
    *,
    hotkey: str | None = None,
    exit_key: str | None = None,
    name: str = "macro",
) -> None:
    """Raise KillKeyError if a macro could bind or type GLOBAL_KILL_KEY.

    Checks two attack surfaces:
    1. Key bindings (hotkey / exit_key) that cover the whole kill combo.
    2. The action sequence: walks Press/Release/Tap tracking which keys are
       held, and rejects the moment all kill-combo keys would be down at once.
    """
    for label, binding in (("hotkey", hotkey), ("exit_key", exit_key)):
        if binding and _combo_keys(binding) >= _KILL_COMBO:
            _reject(name, f"binds its {label} to")

    held: set[str] = set()
    for action in actions:
        if isinstance(action, PressAction):
            held.add(_normalize_key(action.key))
            if held >= _KILL_COMBO:
                _reject(name, "presses every key of")
        elif isinstance(action, ReleaseAction):
            held.discard(_normalize_key(action.key))
        elif isinstance(action, TapAction):
            if held | {_normalize_key(action.key)} >= _KILL_COMBO:
                _reject(name, "presses every key of")
