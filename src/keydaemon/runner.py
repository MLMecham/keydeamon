from __future__ import annotations

import threading
import uuid
import weakref
from typing import Callable

from keydaemon.actions import Action
from keydaemon.scheduler import run_scheduled

_REGISTRY: weakref.WeakSet[DaemonRunner] = weakref.WeakSet()


def _make_controller() -> object:
    """Lazily import pynput and build a unified controller. Tests patch this."""
    from pynput.keyboard import Controller as KB, Key
    from pynput.mouse import Controller as MB, Button

    class _Ctrl:
        def __init__(self) -> None:
            self.keyboard = KB()
            self.mouse = MB()
            self.Key = Key
            self.Button = Button

    return _Ctrl()


def _release_all_inputs() -> None:
    """Release all mouse buttons to prevent stuck inputs after a stop."""
    try:
        from pynput.mouse import Controller as MC, Button
        mc = MC()
        for btn in (Button.left, Button.right, Button.middle):
            try:
                mc.release(btn)
            except Exception:
                pass
    except Exception:
        pass


class DaemonRunner:
    def __init__(
        self,
        actions: list[Action],
        interval: float | None,
        repeat_times: int,
        jitter: float = 0.0,
        token: str | None = None,
    ) -> None:
        self._actions = actions
        self._interval = interval
        self._repeat_times = repeat_times
        self._jitter = jitter
        self.token: str = token or str(uuid.uuid4())
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        ctrl = _make_controller()
        self._thread = threading.Thread(
            target=run_scheduled,
            args=(
                self._actions,
                self._interval,
                self._repeat_times,
                self._jitter,
                ctrl,
                self._stop_event.is_set,
            ),
            daemon=True,
            name=f"keydaemon-{self.token[:8]}",
        )
        self._thread.start()
        _REGISTRY.add(self)

    def stop(self) -> None:
        self._stop_event.set()
        _release_all_inputs()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()


class ExpandRunner:
    """Listens for a text pattern and replaces it or fires a sub-sequence."""

    def __init__(
        self,
        pattern: str,
        replace: str | None = None,
        actions: list[Action] | None = None,
    ) -> None:
        if replace is None and not actions:
            raise ValueError("ExpandRunner requires either replace or actions")
        self._pattern = pattern
        self._replace = replace
        self._actions = actions or []
        self._buffer: list[str] = []
        self._listener = None
        self._stop_event = threading.Event()
        self.token: str = str(uuid.uuid4())

    def start(self) -> None:
        from pynput.keyboard import Controller, Key, Listener

        kb = Controller()

        def on_press(key: object) -> None:
            if self._stop_event.is_set():
                return
            try:
                char = key.char  # type: ignore[union-attr]
            except AttributeError:
                self._buffer.clear()
                return

            self._buffer.append(char)
            joined = "".join(self._buffer)

            if self._pattern in joined:
                self._buffer.clear()
                # erase the trigger
                for _ in self._pattern:
                    kb.press(Key.backspace)
                    kb.release(Key.backspace)
                if self._replace is not None:
                    kb.type(self._replace)
                else:
                    ctrl = _make_controller()
                    for action in self._actions:
                        if self._stop_event.is_set():
                            break
                        action.execute(ctrl, self._stop_event.is_set)
            elif not self._pattern.startswith(joined[-len(self._pattern):]):
                self._buffer.clear()

        self._listener = Listener(on_press=on_press)
        self._listener.start()  # type: ignore[union-attr]
        _REGISTRY.add(self)  # type: ignore[arg-type]

    def stop(self) -> None:
        self._stop_event.set()
        if self._listener is not None:
            self._listener.stop()  # type: ignore[union-attr]

    @property
    def is_running(self) -> bool:
        return self._listener is not None and self._listener.is_alive()  # type: ignore[union-attr]
