import pytest
from keydaemon.builder import MacroBuilder
from keydaemon.actions import (
    TapAction, WaitAction, ClickAction, MoveToAction,
    MoveByAction, ScrollAction, PressAction, ReleaseAction,
    WaitForColorAction, SelfStopAction,
)
from keydaemon._types import LOOP_FOREVER


def test_tap_appends_action():
    b = MacroBuilder().tap("w")
    assert len(b._actions) == 1
    assert isinstance(b._actions[0], TapAction)
    assert b._actions[0].key == "w"


def test_tap_explicit_duration():
    b = MacroBuilder().tap("w", duration=0.1)
    assert b._actions[0].duration == 0.1


def test_wait_appends_action():
    b = MacroBuilder().wait(0.5)
    assert isinstance(b._actions[0], WaitAction)
    assert b._actions[0].seconds == 0.5


def test_every_sets_interval():
    b = MacroBuilder().every(60)
    assert b._interval == 60


def test_times_per_second_sets_interval():
    b = MacroBuilder().times_per_second(20)
    assert b._interval == 0.05


def test_times_per_second_is_inverse_of_every():
    assert MacroBuilder().times_per_second(10)._interval == MacroBuilder().every(0.1)._interval


def test_times_per_second_rejects_nonpositive():
    with pytest.raises(ValueError):
        MacroBuilder().times_per_second(0)


def test_jitter_sets_jitter():
    b = MacroBuilder().jitter(10)
    assert b._jitter == 10


def test_loop_sets_forever():
    b = MacroBuilder().loop()
    assert b._repeat_times == LOOP_FOREVER


def test_loop_with_times():
    b = MacroBuilder().loop(5)
    assert b._repeat_times == 5


def test_repeat_sets_count():
    b = MacroBuilder().repeat(3)
    assert b._repeat_times == 3


def test_sequence_appends_taps():
    b = MacroBuilder().sequence(["w", "a", "s", "d"])
    assert len(b._actions) == 4
    assert all(isinstance(a, TapAction) for a in b._actions)


def test_fluent_chain():
    b = MacroBuilder().every(60).jitter(5).tap("space").wait(0.1).loop()
    assert b._interval == 60
    assert b._jitter == 5
    assert b._repeat_times == LOOP_FOREVER
    assert len(b._actions) == 2


def test_click():
    b = MacroBuilder().click("right", count=2)
    assert isinstance(b._actions[0], ClickAction)
    assert b._actions[0].button == "right"
    assert b._actions[0].count == 2


def test_move_to():
    b = MacroBuilder().move_to(100, 200)
    assert isinstance(b._actions[0], MoveToAction)
    assert b._actions[0].x == 100
    assert b._actions[0].y == 200


def test_move_by():
    b = MacroBuilder().move_by(-50, 0)
    assert isinstance(b._actions[0], MoveByAction)
    assert b._actions[0].dx == -50


def test_scroll():
    b = MacroBuilder().scroll(3)
    assert isinstance(b._actions[0], ScrollAction)
    assert b._actions[0].amount == 3


def test_drag_to_produces_four_actions():
    b = MacroBuilder().drag_to(0, 0, 100, 100)
    assert len(b._actions) == 4
    assert isinstance(b._actions[1], PressAction)
    assert isinstance(b._actions[3], ReleaseAction)


def test_wait_for_color():
    b = MacroBuilder().wait_for_color(234, 456, "#3A7D44", timeout=30)
    a = b._actions[0]
    assert isinstance(a, WaitForColorAction)
    assert a.x == 234
    assert a.hex_color == "#3A7D44"
    assert a.timeout == 30


def test_stop_self():
    b = MacroBuilder().stop_self()
    assert isinstance(b._actions[0], SelfStopAction)


def test_exit_key():
    b = MacroBuilder().exit_key("f6")
    assert b._exit_key == "f6"


def test_hotkey_sets_key_and_default_mode():
    b = MacroBuilder().hotkey("f6")
    assert b._hotkey == "f6"
    assert b._hotkey_mode == "toggle"


def test_hotkey_explicit_mode():
    b = MacroBuilder().hotkey("f6", mode="once")
    assert b._hotkey_mode == "once"


def test_hotkey_is_chainable():
    b = MacroBuilder().every(0.1).click("left").loop().hotkey("f6").exit_key("f8")
    assert b._hotkey == "f6"
    assert b._exit_key == "f8"
    assert b._repeat_times == LOOP_FOREVER
