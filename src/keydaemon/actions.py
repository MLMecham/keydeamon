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


# Mouse buttons currently held down (a press: with no matching release: yet).
# A stop releases ONLY these — releasing a button that was never pressed injects a
# spurious "button up" event, and a stray right-button-up makes apps like the
# Ruffle Flash player open their right-click context menu. A plain clicker holds
# nothing, so its stop must release nothing.
_held_mouse_buttons: set[str] = set()
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
    """Signals the owning runner to stop via its UUID token."""
    token: str

    def execute(self, ctrl: InputController, stop_requested: Callable[[], bool] = lambda: False) -> None:
        # The scheduler checks stop_requested() after each action.
        # SelfStopAction works by registering its token with the runner's stop event
        # before the sequence runs. The runner treats a raised _SelfStop as clean exit.
        raise _SelfStop(self.token)


class _SelfStop(Exception):
    def __init__(self, token: str) -> None:
        self.token = token


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
)
