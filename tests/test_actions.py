from unittest.mock import MagicMock, patch
import pytest

from keydaemon.actions import (
    TapAction, PressAction, ReleaseAction, TypeAction,
    WaitAction, ClickAction, MoveToAction, MoveByAction,
    ScrollAction, WaitForColorAction, SelfStopAction, _SelfStop,
)


def _ctrl():
    ctrl = MagicMock()
    ctrl.Key = MagicMock()
    ctrl.Button = MagicMock()
    ctrl.mouse.position = (0, 0)
    return ctrl


def test_tap_calls_press_and_release():
    ctrl = _ctrl()
    with patch("keydaemon.actions.time.sleep"):
        TapAction(key="w").execute(ctrl)
    ctrl.keyboard.press.assert_called_once()
    ctrl.keyboard.release.assert_called_once()


def test_tap_explicit_duration_sleeps_that_long():
    ctrl = _ctrl()
    with patch("keydaemon.actions.time.sleep") as mock_sleep:
        TapAction(key="w", duration=0.15).execute(ctrl)
    mock_sleep.assert_called_once_with(0.15)


def test_press_keyboard():
    ctrl = _ctrl()
    PressAction(key="shift").execute(ctrl)
    ctrl.keyboard.press.assert_called_once()


def test_press_mouse_button():
    ctrl = _ctrl()
    PressAction(key="left").execute(ctrl)
    ctrl.mouse.press.assert_called_once()


def test_release_keyboard():
    ctrl = _ctrl()
    ReleaseAction(key="shift").execute(ctrl)
    ctrl.keyboard.release.assert_called_once()


def test_release_mouse_button():
    ctrl = _ctrl()
    ReleaseAction(key="left").execute(ctrl)
    ctrl.mouse.release.assert_called_once()


def test_press_mouse_marks_held_and_release_clears():
    from keydaemon.actions import _held_mouse_buttons, _held_lock

    with _held_lock:
        _held_mouse_buttons.clear()
    ctrl = _ctrl()
    PressAction(key="right").execute(ctrl)
    assert "right" in _held_mouse_buttons
    ReleaseAction(key="right").execute(ctrl)
    assert "right" not in _held_mouse_buttons


def test_click_does_not_mark_button_held():
    # A clicker holds nothing — so a later stop releases nothing (no stray events).
    from keydaemon.actions import _held_mouse_buttons, _held_lock

    with _held_lock:
        _held_mouse_buttons.clear()
    ctrl = _ctrl()
    ClickAction(button="left").execute(ctrl)
    assert "left" not in _held_mouse_buttons


def test_type_action():
    ctrl = _ctrl()
    TypeAction(text="hello").execute(ctrl)
    ctrl.keyboard.type.assert_called_once_with("hello")


def test_wait_action_sleeps():
    ctrl = _ctrl()
    with patch("keydaemon.actions.time.sleep") as mock_sleep:
        WaitAction(seconds=1.5).execute(ctrl)
    mock_sleep.assert_called_once_with(1.5)


def test_click_action():
    ctrl = _ctrl()
    ClickAction(button="left", count=2).execute(ctrl)
    ctrl.mouse.click.assert_called_once()


def test_scroll_vertical():
    ctrl = _ctrl()
    ScrollAction(amount=3).execute(ctrl)
    ctrl.mouse.scroll.assert_called_once_with(0, 3)


def test_scroll_horizontal():
    ctrl = _ctrl()
    ScrollAction(amount=2, horizontal=True).execute(ctrl)
    ctrl.mouse.scroll.assert_called_once_with(2, 0)


def test_move_to_sets_position():
    ctrl = _ctrl()
    MoveToAction(x=100, y=200, jitter=False).execute(ctrl)
    assert ctrl.mouse.position == (100, 200)


def test_move_by_calls_move():
    ctrl = _ctrl()
    MoveByAction(dx=10, dy=20).execute(ctrl)
    ctrl.mouse.move.assert_called()


def test_self_stop_raises():
    ctrl = _ctrl()
    with pytest.raises(_SelfStop):
        SelfStopAction(token="abc").execute(ctrl)


def test_wait_for_color_returns_when_match():
    ctrl = _ctrl()
    with patch("keydaemon.screen.color_matches", return_value=True):
        WaitForColorAction(x=0, y=0, hex_color="#FF0000").execute(ctrl)


def test_wait_for_color_times_out():
    ctrl = _ctrl()
    with patch("keydaemon.screen.color_matches", return_value=False):
        with patch("keydaemon.actions.time.sleep"):
            with pytest.raises(TimeoutError):
                WaitForColorAction(x=0, y=0, hex_color="#FF0000", timeout=1.0).execute(ctrl)
