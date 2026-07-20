from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol

from keydaemon._types import (
    MOUSE_BUTTONS,
    POSITION_JITTER_PX,
    SMOOTH_STEP_DELAY,
    SMOOTH_STEPS,
    TAP_DURATION_MAX,
    TAP_DURATION_MIN,
    COLOR_POLL_INTERVAL,
)


class InputController(Protocol):
    """Structural protocol — tests inject a mock without subclassing."""
    keyboard: object
    mouse: object
    Key: object
    Button: object


def _resolve_key(name: str, Key: object) -> object:
    """Map a string key name to a pynput Key or raw string."""
    resolved = getattr(Key, name, None)
    return resolved if resolved is not None else name


def _resolve_button(name: str, Button: object) -> object:
    resolved = getattr(Button, name, None)
    if resolved is None:
        raise ValueError(f"Unknown mouse button: {name!r}")
    return resolved


# Inputs currently held down (a press: with no matching release: yet).
# A stop releases ONLY these — releasing something that was never pressed injects
# a spurious "up" event, and a stray right-button-up makes apps like the Ruffle
# Flash player open their right-click context menu. A plain clicker holds
# nothing, so its stop must release nothing.
#
# Both sets are process-global, shared by every runner: any runner's stop sweeps
# everything currently held. On a race (one thread pressing while another
# releases-all) the releaser wins — the sets are snapshotted and cleared under
# the lock; a press that lands after the snapshot stays tracked and is released
# by the next stop. Taps are NOT tracked: a tap always completes its own
# press→release on its thread, so releasing it from the stop path would inject
# exactly the kind of spurious key-up this mechanism exists to avoid.
_held_mouse_buttons: set[str] = set()
_held_keys: set[str] = set()
_held_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Keyboard actions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TapAction:
    key: str
    duration: float | None = None  # None = random default

    def execute(self, ctrl: InputController, stop_requested: Callable[[], bool] = lambda: False) -> None:
        k = _resolve_key(self.key, ctrl.Key)
        hold = self.duration if self.duration is not None else random.uniform(TAP_DURATION_MIN, TAP_DURATION_MAX)
        ctrl.keyboard.press(k)
        time.sleep(hold)
        ctrl.keyboard.release(k)


@dataclass(frozen=True)
class PressAction:
    key: str

    def execute(self, ctrl: InputController, stop_requested: Callable[[], bool] = lambda: False) -> None:
        if self.key in MOUSE_BUTTONS:
            btn = _resolve_button(self.key, ctrl.Button)
            ctrl.mouse.press(btn)
            with _held_lock:
                _held_mouse_buttons.add(self.key)
        else:
            ctrl.keyboard.press(_resolve_key(self.key, ctrl.Key))
            with _held_lock:
                _held_keys.add(self.key)


@dataclass(frozen=True)
class ReleaseAction:
    key: str

    def execute(self, ctrl: InputController, stop_requested: Callable[[], bool] = lambda: False) -> None:
        if self.key in MOUSE_BUTTONS:
            btn = _resolve_button(self.key, ctrl.Button)
            ctrl.mouse.release(btn)
            with _held_lock:
                _held_mouse_buttons.discard(self.key)
        else:
            ctrl.keyboard.release(_resolve_key(self.key, ctrl.Key))
            with _held_lock:
                _held_keys.discard(self.key)


@dataclass(frozen=True)
class TypeAction:
    text: str

    def execute(self, ctrl: InputController, stop_requested: Callable[[], bool] = lambda: False) -> None:
        ctrl.keyboard.type(self.text)


@dataclass(frozen=True)
class WaitAction:
    seconds: float

    def execute(self, ctrl: InputController, stop_requested: Callable[[], bool] = lambda: False) -> None:
        time.sleep(self.seconds)


# ---------------------------------------------------------------------------
# Mouse actions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MoveToAction:
    x: int
    y: int
    smooth: bool = False
    jitter: bool = True

    def execute(self, ctrl: InputController, stop_requested: Callable[[], bool] = lambda: False) -> None:
        tx = self.x + (random.randint(-POSITION_JITTER_PX, POSITION_JITTER_PX) if self.jitter else 0)
        ty = self.y + (random.randint(-POSITION_JITTER_PX, POSITION_JITTER_PX) if self.jitter else 0)
        cx, cy = ctrl.mouse.position
        if self.smooth:
            for i in range(1, SMOOTH_STEPS + 1):
                if stop_requested():
                    return
                t = i / SMOOTH_STEPS
                t_curved = t * t * (3 - 2 * t)
                nx = int(cx + (tx - cx) * t_curved)
                ny = int(cy + (ty - cy) * t_curved)
                # use move() so SendInput fires WM_MOUSEMOVE (required for drag in apps)
                ctrl.mouse.move(nx - cx, ny - cy)
                cx, cy = nx, ny
                time.sleep(SMOOTH_STEP_DELAY)
        else:
            # SetCursorPos for non-drawing teleport (before button press).
            # Use move_by() when button is held — it sends SendInput which generates drag events.
            ctrl.mouse.position = (tx, ty)


@dataclass(frozen=True)
class MoveByAction:
    dx: int
    dy: int
    smooth: bool = False
    jitter: bool = True  # disable for precise drawing

    def execute(self, ctrl: InputController, stop_requested: Callable[[], bool] = lambda: False) -> None:
        jdx = self.dx + (random.randint(-2, 2) if self.jitter else 0)
        jdy = self.dy + (random.randint(-2, 2) if self.jitter else 0)
        if self.smooth:
            for i in range(1, SMOOTH_STEPS + 1):
                if stop_requested():
                    return
                t = i / SMOOTH_STEPS
                t_curved = t * t * (3 - 2 * t)
                step_x = int(jdx * t_curved) - int(jdx * ((i - 1) / SMOOTH_STEPS) * (((i-1)/SMOOTH_STEPS) * (3 - 2 * (i-1)/SMOOTH_STEPS)))
                ctrl.mouse.move(step_x, 0)
                time.sleep(SMOOTH_STEP_DELAY)
            # ensure exact delta reached
        else:
            ctrl.mouse.move(jdx, jdy)


@dataclass(frozen=True)
class ClickAction:
    button: str = "left"
    count: int = 1

    def execute(self, ctrl: InputController, stop_requested: Callable[[], bool] = lambda: False) -> None:
        btn = _resolve_button(self.button, ctrl.Button)
        ctrl.mouse.click(btn, self.count)


@dataclass(frozen=True)
class ScrollAction:
    amount: int
    horizontal: bool = False

    def execute(self, ctrl: InputController, stop_requested: Callable[[], bool] = lambda: False) -> None:
        if self.horizontal:
            ctrl.mouse.scroll(self.amount, 0)
        else:
            ctrl.mouse.scroll(0, self.amount)


# ---------------------------------------------------------------------------
# Screen condition actions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WaitForColorAction:
    x: int
    y: int
    hex_color: str
    timeout: float | None = None  # seconds; None = wait forever
    tolerance: int = 10

    def execute(self, ctrl: InputController, stop_requested: Callable[[], bool] = lambda: False) -> None:
        from keydaemon.screen import color_matches
        elapsed = 0.0
        while not stop_requested():
            if color_matches(self.x, self.y, self.hex_color, self.tolerance):
                return
            if self.timeout is not None and elapsed >= self.timeout:
                raise TimeoutError(
                    f"Pixel at ({self.x},{self.y}) did not match {self.hex_color!r} "
                    f"within {self.timeout}s"
                )
            time.sleep(COLOR_POLL_INTERVAL)
            elapsed += COLOR_POLL_INTERVAL


# ---------------------------------------------------------------------------
# Control actions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SelfStopAction:
    """Stop the macro this action runs in (and any children of its runner)."""

    def execute(self, ctrl: InputController, stop_requested: Callable[[], bool] = lambda: False) -> None:
        # Control flow, not a signal: the scheduler catches _SelfStop and exits
        # its loop, then the owning runner's thread wrapper calls runner.stop()
        # — cascading to children and releasing held inputs.
        raise _SelfStop()


@dataclass(frozen=True)
class KillAllAction:
    """Stop every macro in the process — same effect as the emergency kill key.

    This is the sanctioned way for a macro to invoke the global kill (the
    hardware combo itself is reserved and unbindable; see keydaemon.guard).
    Exists so conditional macros can bail out of everything, e.g.
    "if the screen goes red, kill all automation".
    """

    def execute(self, ctrl: InputController, stop_requested: Callable[[], bool] = lambda: False) -> None:
        from keydaemon.profile import stop_all  # runtime import avoids a cycle
        stop_all()
        # stop_all() already latched our own stop event, but raising makes the
        # exit immediate and unconditional rather than waiting for the next check.
        raise _SelfStop()


class _SelfStop(Exception):
    """Clean-exit control flow raised by SelfStopAction / KillAllAction."""


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DoAction:
    """Reference to another saved macro's action sequence (builder ``.do()``).

    A reference, never executed: MacroBuilder.run() flattens it into the
    target's actions via loader.resolve_do_actions() before any runner sees
    it, and .save() writes it back as a ``do:<name>`` string (the TOML loader
    flattens that form itself at load time).
    """
    name: str

    def execute(self, ctrl: InputController, stop_requested: Callable[[], bool] = lambda: False) -> None:
        raise RuntimeError(
            f"Unresolved do-reference to macro {self.name!r} — a resolution "
            "step was skipped before running"
        )


# ---------------------------------------------------------------------------
# Union type
# ---------------------------------------------------------------------------

Action = (
    TapAction
    | PressAction
    | ReleaseAction
    | TypeAction
    | WaitAction
    | MoveToAction
    | MoveByAction
    | ClickAction
    | ScrollAction
    | WaitForColorAction
    | SelfStopAction
    | KillAllAction
    | DoAction
)
