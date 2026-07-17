"""The emergency kill combo must be unreachable from any macro definition."""
import pytest

from keydaemon.actions import (
    ClickAction,
    KillAllAction,
    PressAction,
    ReleaseAction,
    SelfStopAction,
    TapAction,
)
from keydaemon.guard import KillKeyError, ensure_kill_key_unreachable


def test_normal_macro_passes():
    ensure_kill_key_unreachable(
        [TapAction(key="space"), ClickAction()],
        hotkey="f6",
        exit_key="f8",
    )


def test_hotkey_binding_of_kill_combo_rejected():
    with pytest.raises(KillKeyError):
        ensure_kill_key_unreachable([], hotkey="<ctrl>+<shift>+<alt>+<f12>")


def test_exit_key_binding_of_kill_combo_rejected():
    with pytest.raises(KillKeyError):
        ensure_kill_key_unreachable([], exit_key="ctrl+shift+alt+f12")


def test_left_right_modifier_variants_rejected():
    with pytest.raises(KillKeyError):
        ensure_kill_key_unreachable([], hotkey="<ctrl_l>+<shift_r>+<alt_gr>+<f12>")


def test_synthesizing_combo_via_presses_rejected():
    actions = [
        PressAction(key="ctrl"),
        PressAction(key="shift"),
        PressAction(key="alt"),
        PressAction(key="f12"),
    ]
    with pytest.raises(KillKeyError):
        ensure_kill_key_unreachable(actions)


def test_tap_while_modifiers_held_rejected():
    actions = [
        PressAction(key="ctrl_l"),
        PressAction(key="shift"),
        PressAction(key="alt_r"),
        TapAction(key="f12"),
    ]
    with pytest.raises(KillKeyError):
        ensure_kill_key_unreachable(actions)


def test_release_breaks_the_combo():
    # Ctrl is released before f12 — never all four down at once.
    actions = [
        PressAction(key="ctrl"),
        PressAction(key="shift"),
        PressAction(key="alt"),
        ReleaseAction(key="ctrl"),
        TapAction(key="f12"),
    ]
    ensure_kill_key_unreachable(actions)


def test_partial_combo_is_fine():
    ensure_kill_key_unreachable([PressAction(key="ctrl"), TapAction(key="f12"),
                                 ReleaseAction(key="ctrl")])
    ensure_kill_key_unreachable([TapAction(key="f12")], hotkey="f12")


def test_sanctioned_stop_actions_pass():
    ensure_kill_key_unreachable([SelfStopAction(), KillAllAction()])
