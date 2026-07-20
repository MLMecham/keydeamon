from __future__ import annotations

from typing import TYPE_CHECKING

from keydaemon._types import LOOP_FOREVER
from keydaemon.actions import (
    Action,
    ClickAction,
    DoAction,
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
        self._expansions: dict[str, str] = {}
        self._expand_pattern: str | None = None  # action-mode pattern (no replace)

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

    def expand(self, pattern: str, replace: str | None = None) -> MacroBuilder:
        """
        Trigger on typed text: whenever `pattern` is typed anywhere, the trigger
        text is erased and `replace` is typed in its place.

        Call repeatedly to build a *bank* — every entry shares one keyboard
        listener::

            keydaemon.macro().expand("///a", "Hello").expand("///b", "cool dudes only")

        With replace=None, typing the pattern runs this macro's action sequence
        instead of typing text (at most one such action pattern per macro).

        Patterns must be typed without modifier keys mid-pattern (lowercase);
        any special key resets the match buffer.
        """
        if replace is None:
            if self._expand_pattern is not None:
                raise ValueError(
                    "Only one action-firing expand pattern per macro — text "
                    "replacements (replace=...) can be banked without limit"
                )
            self._expand_pattern = pattern
        else:
            self._expansions[pattern] = replace
        # No pattern may appear inside any replacement (its own or another's) —
        # typing that replacement would re-trigger an expansion forever.
        for pat in [*self._expansions, *([self._expand_pattern] if self._expand_pattern else [])]:
            for rep in self._expansions.values():
                if pat in rep:
                    raise ValueError(
                        f"replacement text {rep!r} contains the trigger pattern "
                        f"{pat!r} — typing it would re-trigger an expansion forever"
                    )
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
    # Composition
    # ------------------------------------------------------------------

    def do(self, name: str) -> MacroBuilder:
        """Run the saved macro `name`'s action sequence at this point.

        Python twin of the TOML ``do:`` verb. Stored as a reference, not a
        copy: .run() reads the target's TOML fresh each time (editing the
        target changes every macro that does it), and .save() writes
        ``do:name`` so the reference survives in the file. Only the target's
        actions run — its own scheduling (every/repeat/jitter) is ignored.
        Circular references and profile targets are rejected at run time.
        """
        self._actions.append(DoAction(name=name))
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

    def run(self) -> DaemonRunner | HotkeyRunner | ExpandRunner:
        from keydaemon.guard import ensure_kill_key_unreachable
        from keydaemon.loader import resolve_do_actions
        from keydaemon.runner import DaemonRunner, ExpandRunner, HotkeyRunner
        from keydaemon.profile import Profile

        # Flatten .do() refs first so the guard sees the real combined
        # sequence — a sub-macro must not be able to smuggle in kill-combo keys.
        actions = resolve_do_actions(self._actions)
        ensure_kill_key_unreachable(
            actions, hotkey=self._hotkey, exit_key=self._exit_key
        )
        if self._expansions or self._expand_pattern is not None:
            if self._hotkey is not None:
                raise ValueError("A macro can't have both an expand pattern and a hotkey")
            runner = ExpandRunner(
                pattern=self._expand_pattern,
                actions=actions if self._expand_pattern else None,
                expansions=self._expansions,
            )
        elif self._hotkey is not None:
            runner = HotkeyRunner(
                hotkey=self._hotkey,
                actions=actions,
                interval=self._interval,
                repeat_times=self._repeat_times,
                jitter=self._jitter,
                mode=self._hotkey_mode,
            )
        else:
            runner = DaemonRunner(
                actions=actions,
                interval=self._interval,
                repeat_times=self._repeat_times,
                jitter=self._jitter,
            )
        p = Profile(exit_key=self._exit_key)
        p.add_runner(runner)
        p.start()
        return runner

    def save(self, name: str, description: str = ""):
        """
        Write this macro to the keydaemon macros directory as `<name>.toml`,
        overwriting any existing file of that name — the Python script is the
        source of truth, so running it stamps its current behavior over the TOML.

        The saved file is a first-class CLI macro: run it with
        ``keydaemon run <name>``, see it in ``keydaemon list``, detach it,
        stop it by name.

        Raises ValueError if the macro uses Python-only features that TOML
        can't express (the file is left untouched in that case).
        """
        from keydaemon._paths import macro_path
        from keydaemon.export import builder_to_toml
        from keydaemon.guard import ensure_kill_key_unreachable

        ensure_kill_key_unreachable(
            self._actions, hotkey=self._hotkey, exit_key=self._exit_key, name=name
        )
        text = builder_to_toml(self, name=name, description=description)
        path = macro_path(name)
        path.write_text(text, encoding="utf-8")
        return path
