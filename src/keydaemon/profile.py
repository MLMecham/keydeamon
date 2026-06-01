from __future__ import annotations

import platform
import sys
import weakref
from typing import TYPE_CHECKING

from keydaemon._types import GLOBAL_KILL_KEY

if TYPE_CHECKING:
    from keydaemon.runner import DaemonRunner, ExpandRunner

_PROFILE_REGISTRY: weakref.WeakSet[Profile] = weakref.WeakSet()

RunnerLike = "DaemonRunner | ExpandRunner"


class Profile:
    """
    Execution context — owns a set of runners, an exit key, and the global kill listener.
    Every macro runs inside a Profile (explicit or implicit).
    """

    def __init__(
        self,
        name: str = "default",
        exit_key: str | None = None,
    ) -> None:
        self.name = name
        self._exit_key = exit_key
        self._runners: list[RunnerLike] = []
        self._kill_listener = None

    def add_runner(self, runner: RunnerLike) -> None:
        self._runners.append(runner)

    def start(self) -> None:
        _check_macos_permissions()
        for runner in self._runners:
            runner.start()
        self._register_kill_listeners()
        _PROFILE_REGISTRY.add(self)

    def stop(self) -> None:
        for runner in self._runners:
            runner.stop()
        if self._kill_listener is not None:
            try:
                self._kill_listener.stop()
            except Exception:
                pass

    @property
    def is_running(self) -> bool:
        return any(r.is_running for r in self._runners)

    def _register_kill_listeners(self) -> None:
        from pynput import keyboard

        def on_activate_global() -> None:
            stop_all()

        def on_activate_exit() -> None:
            self.stop()

        hotkeys = {GLOBAL_KILL_KEY: on_activate_global}
        if self._exit_key:
            # Single printable chars (e.g. "p") don't use angle brackets in pynput.
            # Special/function keys (e.g. "f6", "shift") do.
            key_str = self._exit_key
            if len(key_str) > 1 and not key_str.startswith("<"):
                key_str = f"<{key_str}>"
            hotkeys[key_str] = on_activate_exit

        self._kill_listener = keyboard.GlobalHotKeys(hotkeys)
        self._kill_listener.start()


def stop_all() -> None:
    """Stop every active profile."""
    for profile in list(_PROFILE_REGISTRY):
        profile.stop()


def _check_macos_permissions() -> None:
    if platform.system() != "Darwin":
        return
    try:
        from pynput import keyboard
        # Attempt to create a controller — fails loudly if no accessibility access
        keyboard.Controller()
    except Exception:
        print(
            "\nError: keydaemon needs Accessibility permissions on macOS.\n"
            "Go to: System Settings → Privacy & Security → Accessibility\n"
            "Enable your terminal app, then re-run keydaemon.\n",
            file=sys.stderr,
        )
        sys.exit(1)
