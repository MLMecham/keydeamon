from __future__ import annotations

from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from keydaemon.runner import DaemonRunner, HotkeyRunner


class MacroBuilder:
    """Fluent builder — accumulates state, does nothing until .run()."""

    def __init__(self) -> None:
        self._actions: list[Action] = []
        self._interval: float | None = None
        self._repeat_times: int = 1
        self._jitter: float = 0.0
        self._exit_key: str | None = None
        self._hotkey: str | None = None
        self._hotkey_mode: str = "toggle"

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------

    def every(self, seconds: float) -> MacroBuilder:
        self._interval = seconds
        return self

    def times_per_second(self, n: float) -> MacroBuilder:
        """Set the loop rate as a frequency instead of a period.

        ``times_per_second(20)`` is sugar for ``every(1 / 20)``. Clickers and
        anti-AFK loops are easier to reason about in Hz than in seconds.
        """
        if n <= 0:
            raise ValueError(f"times_per_second needs a positive rate, got {n!r}")
        self._interval = 1.0 / n
        return self

    def jitter(self, seconds: float) -> MacroBuilder:
        self._jitter = seconds
        return self

    def loop(self, times: int = LOOP_FOREVER) -> MacroBuilder:
        self._repeat_times = times
        return self

    def repeat(self, times: int) -> MacroBuilder:
        self._repeat_times = times
        return self

    def exit_key(self, key: str) -> MacroBuilder:
        self._exit_key = key
        return self

    def hotkey(self, key: str, mode: str = "toggle") -> MacroBuilder:
        """
        Arm this macro behind a hotkey instead of running immediately.

        mode="toggle" (default): press the key to start the loop, press again to
        stop it. mode="once": each press fires the loop a single time.
        The program stays alive between presses; use exit_key to quit entirely.
        """
        self._hotkey = key
        self._hotkey_mode = mode
        return self

    # ------------------------------------------------------------------
    # Keyboard actions
    # ------------------------------------------------------------------

    def tap(self, key: str, duration: float | None = None) -> MacroBuilder:
        self._actions.append(TapAction(key=key, duration=duration))
        return self

    def press(self, key: str) -> MacroBuilder:
        self._actions.append(PressAction(key=key))
        return self

    def release(self, key: str) -> MacroBuilder:
        self._actions.append(ReleaseAction(key=key))
        return self

    def type(self, text: str) -> MacroBuilder:
        self._actions.append(TypeAction(text=text))
        return self

    def wait(self, seconds: float) -> MacroBuilder:
        self._actions.append(WaitAction(seconds=seconds))
        return self

    def sequence(self, keys: list[str]) -> MacroBuilder:
        for key in keys:
            self.tap(key)
        return self

    # ------------------------------------------------------------------
    # Mouse actions
    # ------------------------------------------------------------------

    def move_to(self, x: int, y: int, smooth: bool = False, jitter: bool = True) -> MacroBuilder:
        self._actions.append(MoveToAction(x=x, y=y, smooth=smooth, jitter=jitter))
        return self

    def move_by(self, dx: int, dy: int, smooth: bool = False, jitter: bool = True) -> MacroBuilder:
        self._actions.append(MoveByAction(dx=dx, dy=dy, smooth=smooth, jitter=jitter))
        return self

    def click(self, button: str = "left", count: int = 1) -> MacroBuilder:
        self._actions.append(ClickAction(button=button, count=count))
        return self

    def scroll(self, amount: int, horizontal: bool = False) -> MacroBuilder:
        self._actions.append(ScrollAction(amount=amount, horizontal=horizontal))
        return self

    def drag_to(self, x1: int, y1: int, x2: int, y2: int) -> MacroBuilder:
        """Sugar: move to start, hold left, smooth move to end, release."""
        self._actions.append(MoveToAction(x=x1, y=y1))
        self._actions.append(PressAction(key="left"))
        self._actions.append(MoveToAction(x=x2, y=y2, smooth=True, jitter=False))
        self._actions.append(ReleaseAction(key="left"))
        return self

    # ------------------------------------------------------------------
    # Screen conditions
    # ------------------------------------------------------------------

    def wait_for_color(
        self,
        x: int,
        y: int,
        hex_color: str,
        timeout: float | None = None,
        tolerance: int = 10,
    ) -> MacroBuilder:
        self._actions.append(
            WaitForColorAction(x=x, y=y, hex_color=hex_color, timeout=timeout, tolerance=tolerance)
        )
        return self

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def stop_self(self) -> MacroBuilder:
        """Stop this macro (and its runner's children) when reached."""
        self._actions.append(SelfStopAction())
        return self

    def kill_all(self) -> MacroBuilder:
        """Stop EVERY macro in the process when reached — the programmatic
        equivalent of the emergency kill key. Pair with conditions (e.g. a
        wait_for_color) to bail out of all automation when something looks wrong."""
        self._actions.append(KillAllAction())
        return self

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run(self) -> DaemonRunner | HotkeyRunner:
        from keydaemon.guard import ensure_kill_key_unreachable
        from keydaemon.runner import DaemonRunner, HotkeyRunner
        from keydaemon.profile import Profile

        ensure_kill_key_unreachable(
            self._actions, hotkey=self._hotkey, exit_key=self._exit_key
        )
        if self._hotkey is not None:
            runner = HotkeyRunner(
                hotkey=self._hotkey,
                actions=list(self._actions),
                interval=self._interval,
                repeat_times=self._repeat_times,
                jitter=self._jitter,
                mode=self._hotkey_mode,
            )
        else:
            runner = DaemonRunner(
                actions=list(self._actions),
                interval=self._interval,
                repeat_times=self._repeat_times,
                jitter=self._jitter,
            )
        p = Profile(exit_key=self._exit_key)
        p.add_runner(runner)
        p.start()
        return runner
