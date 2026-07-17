from __future__ import annotations

import threading
import uuid
import weakref
from typing import Callable

from keydaemon.actions import Action
from keydaemon.scheduler import run_scheduled

# Backstop registry: EVERY runner auto-registers here in Runner.__init__, so a
# global sweep can reach anything — even a child orphaned by a broken owner chain.
# Weak refs so finished runners are collected; live ones stay reachable for kill.
_ALL_RUNNERS: weakref.WeakSet[Runner] = weakref.WeakSet()


def stop_all_runners() -> None:
    """Hard backstop: stop every live runner, regardless of who owns it.

    stop() is idempotent, so calling this alongside an ordered profile teardown
    is safe — anything already stopped is a no-op, anything orphaned still dies.
    """
    for r in list(_ALL_RUNNERS):
        try:
            r.stop()
        except Exception:
            pass


class Runner:
    """
    Lifecycle base for every runner — the single mechanism that makes runaway
    threads impossible.

    Three guarantees, none of which a subclass can accidentally opt out of:

    1. Auto-registration: __init__ adds self to _ALL_RUNNERS. You cannot build a
       runner that escapes the global backstop sweep.
    2. Idempotent, cascading stop(): stops children first, then self, exactly
       once. Safe to call from the owner tree AND the flat sweep — they overlap
       harmlessly.
    3. Template-method teardown: subclasses implement _stop_self() (kill my
       thread/listener). They can't forget to stop children — the base does it.

    Children are stopped before parents so a supervisor (e.g. HotkeyRunner)
    always tears its loop down before releasing its own listener.
    """

    def __init__(self, token: str | None = None) -> None:
        self.token: str = token or str(uuid.uuid4())
        self._children: list[Runner] = []
        self._stopped: bool = False
        self._lock = threading.Lock()
        _ALL_RUNNERS.add(self)

    def add_child(self, child: Runner) -> None:
        """Register a sub-runner so stop() cascades to it (children-first)."""
        with self._lock:
            self._children.append(child)

    def stop(self) -> None:
        with self._lock:
            if self._stopped:
                return
            self._stopped = True
            children = list(self._children)
            self._children.clear()
        # Cascade OUTSIDE our lock (each child takes its own) — no nested locking.
        for child in children:
            try:
                child.stop()
            except Exception:
                pass
        self._stop_self()

    def _stop_self(self) -> None:
        """Subclass hook: tear down own thread/listener. Must not raise."""

    @property
    def is_running(self) -> bool:  # overridden by subclasses
        return False


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
    """Release only the mouse buttons and keyboard keys currently held, to
    prevent stuck inputs after a stop. Inputs that were never pressed are left
    untouched — injecting a spurious 'up' (a right-button-up especially) makes
    apps like the Ruffle Flash player open a context menu. A plain clicker holds
    nothing, so this is a no-op for it and no stray events are sent."""
    from keydaemon.actions import _held_keys, _held_lock, _held_mouse_buttons

    with _held_lock:
        held_buttons = list(_held_mouse_buttons)
        held_keys = list(_held_keys)
        _held_mouse_buttons.clear()
        _held_keys.clear()
    if held_buttons:
        try:
            from pynput.mouse import Controller as MC, Button
            mc = MC()
            for name in held_buttons:
                btn = getattr(Button, name, None)
                if btn is not None:
                    try:
                        mc.release(btn)
                    except Exception:
                        pass
        except Exception:
            pass
    if held_keys:
        try:
            from pynput.keyboard import Controller as KC, Key
            kc = KC()
            for name in held_keys:
                # Same resolution as actions._resolve_key: named Key or raw char.
                key = getattr(Key, name, None)
                try:
                    kc.release(key if key is not None else name)
                except Exception:
                    pass
        except Exception:
            pass


class DaemonRunner(Runner):
    def __init__(
        self,
        actions: list[Action],
        interval: float | None,
        repeat_times: int,
        jitter: float = 0.0,
        token: str | None = None,
    ) -> None:
        super().__init__(token)
        self._actions = actions
        self._interval = interval
        self._repeat_times = repeat_times
        self._jitter = jitter
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        ctrl = _make_controller()

        def _run() -> None:
            try:
                run_scheduled(
                    self._actions,
                    self._interval,
                    self._repeat_times,
                    self._jitter,
                    ctrl,
                    self._stop_event.is_set,
                )
            finally:
                # However the loop ended (finite run done, stop:self/stop:all,
                # crash), tear down properly: cascade to children and release
                # held inputs. stop() is idempotent and join-free, so calling
                # it from our own thread is safe.
                self.stop()

        self._thread = threading.Thread(
            target=_run,
            daemon=True,
            name=f"keydaemon-{self.token[:8]}",
        )
        self._thread.start()

    def _stop_self(self) -> None:
        self._stop_event.set()
        _release_all_inputs()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()


class HotkeyRunner(Runner):
    """
    Arms a global hotkey that starts/stops a child action loop.

    Unlike DaemonRunner (which runs immediately) or ExpandRunner (which fires on
    typed text), HotkeyRunner stays armed and reacts to a single hotkey:

        mode="toggle"  press starts the child loop; press again stops it.
                       The same key is both "start" and "stop" — a real toggle.
        mode="once"    each press fires the child loop once (ignored while it's
                       still running, so presses don't stack).

    The runner itself lives until stop() (listener stays alive between presses),
    so exit_key / global kill / stop_all terminate it *and* any running child.

    A FRESH DaemonRunner is built on every start because DaemonRunner.stop()
    latches its stop event and cannot be restarted.
    """

    def __init__(
        self,
        hotkey: str,
        actions: list[Action],
        interval: float | None,
        repeat_times: int,
        jitter: float = 0.0,
        mode: str = "toggle",
        token: str | None = None,
    ) -> None:
        if mode not in ("toggle", "once"):
            raise ValueError(f"Unknown hotkey mode: {mode!r} (use 'toggle' or 'once')")
        super().__init__(token)  # provides token, _lock, _stopped, _children, auto-register
        self._hotkey = hotkey
        self._actions = actions
        self._interval = interval
        self._repeat_times = repeat_times
        self._jitter = jitter
        self._mode = mode
        self._listener = None
        self._child: DaemonRunner | None = None

    def _make_child(self) -> DaemonRunner:
        return DaemonRunner(
            actions=list(self._actions),
            interval=self._interval,
            repeat_times=self._repeat_times,
            jitter=self._jitter,
        )

    def _on_activate(self) -> None:
        # Runs on the listener thread — keep it quick and serialized.
        with self._lock:
            if self._stopped:
                return
            child_running = self._child is not None and self._child.is_running
            if self._mode == "once":
                if child_running:
                    return  # don't stack overlapping fires
                self._child = self._make_child()
                self._child.start()
                return
            # toggle
            if child_running:
                self._child.stop()  # type: ignore[union-attr]
                self._child = None
            else:
                self._child = self._make_child()
                self._child.start()

    def start(self) -> None:
        from pynput import keyboard

        # GlobalHotKeys wants <f6>/<shift> for special keys but bare chars for letters.
        key_str = self._hotkey
        if len(key_str) > 1 and not key_str.startswith("<"):
            key_str = f"<{key_str}>"
        self._listener = keyboard.GlobalHotKeys({key_str: self._on_activate})
        self._listener.start()  # type: ignore[union-attr]

    def _stop_self(self) -> None:
        # _stopped is already set under lock by Runner.stop(), so no concurrent
        # _on_activate can touch _child past this point — safe to read it here.
        child = self._child
        self._child = None
        if child is not None:
            child.stop()
        if self._listener is not None:
            try:
                self._listener.stop()  # type: ignore[union-attr]
            except Exception:
                pass

    def join(self, timeout: float | None = None) -> None:
        if self._listener is not None:
            self._listener.join(timeout)  # type: ignore[union-attr]

    @property
    def is_running(self) -> bool:
        return self._listener is not None and self._listener.is_alive()  # type: ignore[union-attr]


class ExpandRunner(Runner):
    """Listens for typed text patterns — a *bank* of them — with one listener.

    Two kinds of entry share the single keyboard listener and match buffer:

    - expansions: {pattern: replacement} — typing a pattern erases it and
      types its replacement. Many can be armed at once ("///a", "///b", ...).
    - one optional action pattern — typing it erases it and fires this
      macro's action sequence instead of text.

    Matching uses a rolling buffer capped at the longest pattern: each typed
    character appends, the tail is kept, and a fire happens the moment the
    buffer ends with any armed pattern. Any non-character key resets the match.
    """

    def __init__(
        self,
        pattern: str | None = None,
        replace: str | None = None,
        actions: list[Action] | None = None,
        expansions: dict[str, str] | None = None,
    ) -> None:
        expansions = dict(expansions or {})
        if pattern and replace is not None:
            # single pattern+replace is sugar for a one-entry bank
            expansions[pattern] = replace
            pattern = None
        if not expansions and not (pattern and actions):
            raise ValueError(
                "ExpandRunner requires expansions (pattern -> replacement) "
                "and/or a pattern with actions"
            )
        super().__init__()
        self._expansions = expansions
        self._action_pattern = pattern
        self._actions = actions or []
        self._buffer: list[str] = []
        self._listener = None
        self._stop_event = threading.Event()

    def _patterns(self) -> list[str]:
        pats = list(self._expansions)
        if self._action_pattern:
            pats.append(self._action_pattern)
        return pats

    def start(self) -> None:
        from pynput.keyboard import Controller, Key, Listener

        kb = Controller()
        patterns = self._patterns()
        max_len = max(len(p) for p in patterns)

        def on_press(key: object) -> None:
            if self._stop_event.is_set():
                return
            try:
                char = key.char  # type: ignore[union-attr]
            except AttributeError:
                self._buffer.clear()
                return
            if char is None:
                self._buffer.clear()
                return

            self._buffer.append(char)
            del self._buffer[:-max_len]  # rolling tail — old chars can't match
            joined = "".join(self._buffer)

            for pattern in patterns:
                if not joined.endswith(pattern):
                    continue
                self._buffer.clear()
                # erase the trigger
                for _ in pattern:
                    kb.press(Key.backspace)
                    kb.release(Key.backspace)
                replacement = self._expansions.get(pattern)
                if replacement is not None:
                    kb.type(replacement)
                else:
                    ctrl = _make_controller()
                    from keydaemon.actions import _SelfStop
                    for action in self._actions:
                        if self._stop_event.is_set():
                            break
                        try:
                            action.execute(ctrl, self._stop_event.is_set)
                        except _SelfStop:
                            # stop:self / stop:all inside an expansion sequence
                            # stops this runner; pynput allows stopping the
                            # listener from its own callback.
                            self.stop()
                            return
                return

        self._listener = Listener(on_press=on_press)
        self._listener.start()  # type: ignore[union-attr]

    def _stop_self(self) -> None:
        self._stop_event.set()
        if self._listener is not None:
            try:
                self._listener.stop()  # type: ignore[union-attr]
            except Exception:
                pass

    def join(self, timeout: float | None = None) -> None:
        if self._listener is not None:
            self._listener.join(timeout)  # type: ignore[union-attr]

    @property
    def is_running(self) -> bool:
        return self._listener is not None and self._listener.is_alive()  # type: ignore[union-attr]


def make_runner(lm: object) -> DaemonRunner | ExpandRunner | HotkeyRunner:
    """
    Build the right runner for a loaded macro. Single source of truth so the CLI,
    profile loader, and Python API never drift on how a macro maps to a runner.

    `lm` is a keydaemon.loader.LoadedMacro (duck-typed to avoid an import cycle).
    """
    if lm.trigger_type == "expand":  # type: ignore[attr-defined]
        return ExpandRunner(
            pattern=lm.expand_pattern,  # type: ignore[attr-defined]
            replace=lm.expand_replace,  # type: ignore[attr-defined]
            actions=lm.actions if not lm.expand_replace else None,  # type: ignore[attr-defined]
            expansions=getattr(lm, "expansions", None),
        )
    if getattr(lm, "hotkey", None):
        return HotkeyRunner(
            hotkey=lm.hotkey,  # type: ignore[attr-defined]
            actions=lm.actions,  # type: ignore[attr-defined]
            interval=lm.interval,  # type: ignore[attr-defined]
            repeat_times=lm.repeat_times,  # type: ignore[attr-defined]
            jitter=lm.jitter,  # type: ignore[attr-defined]
            mode=getattr(lm, "hotkey_mode", "toggle"),
        )
    return DaemonRunner(
        actions=lm.actions,  # type: ignore[attr-defined]
        interval=lm.interval,  # type: ignore[attr-defined]
        repeat_times=lm.repeat_times,  # type: ignore[attr-defined]
        jitter=lm.jitter,  # type: ignore[attr-defined]
    )
