from unittest.mock import MagicMock, patch

import pytest

from keydaemon.runner import (
    HotkeyRunner,
    Runner,
    _ALL_RUNNERS,
    make_runner,
    stop_all_runners,
)


# ---------------------------------------------------------------------------
# Runner lifecycle base — the no-runaway-threads guarantees
# ---------------------------------------------------------------------------

class _RecordingRunner(Runner):
    """Minimal Runner that logs the order its teardown fires."""

    def __init__(self, log, name):
        super().__init__()
        self._log = log
        self._name = name
        self._alive = True

    def _stop_self(self):
        self._log.append(self._name)
        self._alive = False

    @property
    def is_running(self):
        return self._alive


def test_runner_auto_registers_in_backstop():
    r = _RecordingRunner([], "r")
    assert r in _ALL_RUNNERS


def test_stop_is_idempotent():
    log = []
    r = _RecordingRunner(log, "r")
    r.stop()
    r.stop()
    r.stop()
    assert log == ["r"]  # _stop_self runs exactly once no matter how often stop() is called


def test_stop_cascades_children_before_parent():
    log = []
    parent = _RecordingRunner(log, "parent")
    parent.add_child(_RecordingRunner(log, "child_a"))
    parent.add_child(_RecordingRunner(log, "child_b"))
    parent.stop()
    assert log[-1] == "parent"
    assert set(log[:-1]) == {"child_a", "child_b"}  # both children torn down first


def test_stop_all_runners_sweeps_an_orphan():
    log = []
    orphan = _RecordingRunner(log, "orphan")  # owned by no profile, no parent
    stop_all_runners()
    assert "orphan" in log


def test_release_all_inputs_injects_nothing_when_no_button_held():
    # The autoclicker bug: a stop must not synthesize button-up events when
    # nothing is held, or a stray right-up pops the Ruffle context menu.
    from keydaemon import runner
    from keydaemon.actions import _held_mouse_buttons, _held_lock

    with _held_lock:
        _held_mouse_buttons.clear()
    with patch("pynput.mouse.Controller") as MockController:
        runner._release_all_inputs()
        MockController.assert_not_called()  # no controller built => no events sent


def test_release_all_inputs_releases_only_held_button():
    from keydaemon import runner
    from keydaemon.actions import _held_mouse_buttons, _held_lock

    with _held_lock:
        _held_mouse_buttons.clear()
        _held_mouse_buttons.add("left")
    runner._release_all_inputs()
    assert "left" not in _held_mouse_buttons  # released and cleared


def test_profile_stop_all_triggers_backstop_sweep():
    from keydaemon import profile

    log = []
    r = _RecordingRunner(log, "swept")
    profile.stop_all()
    assert "swept" in log


def _hotkey(mode="toggle"):
    return HotkeyRunner(
        hotkey="f6", actions=[], interval=0.1, repeat_times=-1, jitter=0.0, mode=mode
    )


def test_invalid_mode_rejected():
    with pytest.raises(ValueError, match="Unknown hotkey mode"):
        HotkeyRunner(hotkey="f6", actions=[], interval=None, repeat_times=1, jitter=0.0, mode="bogus")


@patch("keydaemon.runner.DaemonRunner")
def test_toggle_first_press_starts_child(MockDR):
    hr = _hotkey()
    hr._on_activate()
    MockDR.return_value.start.assert_called_once()
    assert hr._child is MockDR.return_value


@patch("keydaemon.runner.DaemonRunner")
def test_toggle_second_press_stops_child(MockDR):
    MockDR.return_value.is_running = True
    hr = _hotkey()
    hr._on_activate()  # start
    hr._on_activate()  # running -> stop
    MockDR.return_value.stop.assert_called_once()
    assert hr._child is None


@patch("keydaemon.runner.DaemonRunner")
def test_toggle_builds_fresh_child_each_start(MockDR):
    # DaemonRunner can't be restarted, so each toggle-on must construct a new one.
    MockDR.return_value.is_running = True
    hr = _hotkey()
    hr._on_activate()  # start (build #1)
    hr._on_activate()  # stop
    MockDR.return_value.is_running = False  # now reports stopped
    hr._on_activate()  # start (build #2)
    assert MockDR.call_count == 2


@patch("keydaemon.runner.DaemonRunner")
def test_once_mode_fires_when_idle(MockDR):
    MockDR.return_value.is_running = False
    hr = _hotkey(mode="once")
    hr._on_activate()
    MockDR.return_value.start.assert_called_once()


@patch("keydaemon.runner.DaemonRunner")
def test_once_mode_ignores_press_while_running(MockDR):
    MockDR.return_value.is_running = True
    hr = _hotkey(mode="once")
    hr._on_activate()  # starts
    hr._on_activate()  # still running -> ignored, no stacking
    assert MockDR.call_count == 1


@patch("keydaemon.runner.DaemonRunner")
def test_stop_cascades_to_child_and_listener(MockDR):
    MockDR.return_value.is_running = True
    hr = _hotkey()
    hr._on_activate()  # start a child
    hr._listener = MagicMock()
    hr.stop()
    MockDR.return_value.stop.assert_called_once()
    hr._listener.stop.assert_called_once()
    assert hr._stopped is True


@patch("keydaemon.runner.DaemonRunner")
def test_activate_noop_after_stop(MockDR):
    hr = _hotkey()
    hr._listener = MagicMock()
    hr.stop()
    hr._on_activate()  # should do nothing once stopped
    MockDR.assert_not_called()


def test_start_normalizes_function_key():
    from pynput import keyboard  # MagicMock from conftest

    keyboard.GlobalHotKeys.reset_mock()
    hr = _hotkey()
    hr.start()
    registered = keyboard.GlobalHotKeys.call_args.args[0]
    assert "<f6>" in registered


def test_start_leaves_single_char_unwrapped():
    from pynput import keyboard

    keyboard.GlobalHotKeys.reset_mock()
    hr = HotkeyRunner(hotkey="a", actions=[], interval=None, repeat_times=1, jitter=0.0)
    hr.start()
    registered = keyboard.GlobalHotKeys.call_args.args[0]
    assert "a" in registered


# ---------------------------------------------------------------------------
# make_runner factory
# ---------------------------------------------------------------------------

class _FakeLoaded:
    def __init__(self, **kw):
        self.trigger_type = kw.get("trigger_type", "loop")
        self.actions = kw.get("actions", [])
        self.interval = kw.get("interval")
        self.repeat_times = kw.get("repeat_times", 1)
        self.jitter = kw.get("jitter", 0.0)
        self.expand_pattern = kw.get("expand_pattern")
        self.expand_replace = kw.get("expand_replace")
        self.hotkey = kw.get("hotkey")
        self.hotkey_mode = kw.get("hotkey_mode", "toggle")


def test_make_runner_builds_hotkey_runner():
    r = make_runner(_FakeLoaded(trigger_type="manual", hotkey="f6"))
    assert isinstance(r, HotkeyRunner)


def test_make_runner_builds_daemon_runner_without_hotkey():
    from keydaemon.runner import DaemonRunner

    r = make_runner(_FakeLoaded(trigger_type="loop"))
    assert isinstance(r, DaemonRunner)


def test_make_runner_builds_expand_runner():
    from keydaemon.runner import ExpandRunner

    r = make_runner(_FakeLoaded(trigger_type="expand", expand_pattern="///x", expand_replace="y"))
    assert isinstance(r, ExpandRunner)


# ---------------------------------------------------------------------------
# stop:self / stop:all tear the runner down properly (not just the loop)
# ---------------------------------------------------------------------------

def test_self_stop_action_stops_runner_and_releases_inputs():
    from keydaemon import actions as actions_mod
    from keydaemon.actions import PressAction, SelfStopAction
    from keydaemon.runner import DaemonRunner

    r = DaemonRunner(
        actions=[PressAction(key="left"), SelfStopAction()],
        interval=0.01,
        repeat_times=-1,  # would loop forever without the stop:self
    )
    r.start()
    r.join(timeout=2)
    assert not r.is_running
    assert r._stopped  # full runner stop, not just a dead thread
    with actions_mod._held_lock:
        assert actions_mod._held_mouse_buttons == set()  # held button was released


def test_finite_run_auto_stops_runner():
    from keydaemon.actions import WaitAction
    from keydaemon.runner import DaemonRunner

    r = DaemonRunner(actions=[WaitAction(seconds=0)], interval=None, repeat_times=1)
    r.start()
    r.join(timeout=2)
    assert r._stopped  # natural completion also runs the teardown path


def test_release_all_inputs_injects_nothing_when_no_key_held():
    from keydaemon import runner
    from keydaemon.actions import _held_keys, _held_lock

    with _held_lock:
        _held_keys.clear()
    with patch("pynput.keyboard.Controller") as MockController:
        runner._release_all_inputs()
        MockController.assert_not_called()  # no controller built => no events sent


def test_release_all_inputs_releases_only_held_key():
    from keydaemon import runner
    from keydaemon.actions import _held_keys, _held_lock

    with _held_lock:
        _held_keys.clear()
        _held_keys.add("shift")
    with patch("pynput.keyboard.Controller") as MockController:
        runner._release_all_inputs()
        MockController.return_value.release.assert_called_once()
    with _held_lock:
        assert _held_keys == set()  # released and cleared


def test_stop_releases_held_keyboard_key():
    # The stuck-shift bug: press("shift") then stop must release shift.
    from keydaemon import actions as actions_mod
    from keydaemon.actions import PressAction, WaitAction
    from keydaemon.runner import DaemonRunner

    with actions_mod._held_lock:
        actions_mod._held_keys.clear()
    r = DaemonRunner(
        actions=[PressAction(key="shift"), WaitAction(seconds=5)],
        interval=None,
        repeat_times=1,
    )
    r.start()
    import time
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        with actions_mod._held_lock:
            if "shift" in actions_mod._held_keys:
                break
        time.sleep(0.01)
    r.stop()
    with actions_mod._held_lock:
        assert actions_mod._held_keys == set()  # shift released on stop


# ---------------------------------------------------------------------------
# ExpandRunner matching — the bank, the rolling buffer, the erase-and-replace
# ---------------------------------------------------------------------------

import sys
import types


def _arm(runner):
    """Start an ExpandRunner against mocked pynput; return (typist, kb_mock)."""
    kbmod = sys.modules["pynput.keyboard"]
    kbmod.Controller.reset_mock()
    kbmod.Listener.reset_mock()
    runner.start()
    on_press = kbmod.Listener.call_args.kwargs["on_press"]
    kb = kbmod.Controller.return_value
    kb.reset_mock()

    def typist(text):
        for ch in text:
            on_press(types.SimpleNamespace(char=ch))

    def special_key():
        on_press(types.SimpleNamespace())  # no .char -> non-character key

    return typist, special_key, kb


def test_expand_bank_matches_each_pattern():
    from keydaemon.runner import ExpandRunner

    r = ExpandRunner(expansions={"///a": "Hello", "///b": "cool dudes only"})
    typist, _, kb = _arm(r)

    typist("some text ///a")
    kb.type.assert_called_once_with("Hello")

    kb.reset_mock()
    typist("///b")
    kb.type.assert_called_once_with("cool dudes only")
    r.stop()


def test_expand_erases_the_trigger():
    from keydaemon.runner import ExpandRunner

    r = ExpandRunner(expansions={"///sig": "x"})
    typist, _, kb = _arm(r)
    typist("///sig")
    # one backspace press per trigger character
    assert kb.press.call_count == len("///sig")
    r.stop()


def test_special_key_resets_the_match():
    from keydaemon.runner import ExpandRunner

    r = ExpandRunner(expansions={"///a": "Hello"})
    typist, special_key, kb = _arm(r)
    typist("///")
    special_key()      # e.g. an arrow key mid-pattern
    typist("a")
    kb.type.assert_not_called()
    r.stop()


def test_expand_action_pattern_fires_actions():
    from unittest.mock import MagicMock
    from keydaemon.runner import ExpandRunner

    action = MagicMock()
    r = ExpandRunner(pattern="///go", actions=[action])
    typist, _, kb = _arm(r)
    typist("///go")
    action.execute.assert_called_once()
    kb.type.assert_not_called()  # actions, not replacement text
    r.stop()


def test_expand_requires_something_to_do():
    from keydaemon.runner import ExpandRunner

    with pytest.raises(ValueError, match="requires expansions"):
        ExpandRunner(pattern="///x")  # pattern but no replace and no actions
