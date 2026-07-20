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


def test_kill_all():
    from keydaemon.actions import KillAllAction
    b = MacroBuilder().kill_all()
    assert isinstance(b._actions[0], KillAllAction)


def test_run_rejects_kill_combo_hotkey():
    import pytest
    from keydaemon.guard import KillKeyError
    b = MacroBuilder().click("left").hotkey("<ctrl>+<shift>+<alt>+<f12>")
    with pytest.raises(KillKeyError):
        b.run()


def test_run_rejects_kill_combo_synthesis():
    import pytest
    from keydaemon.guard import KillKeyError
    b = MacroBuilder().press("ctrl").press("shift").press("alt").tap("f12")
    with pytest.raises(KillKeyError):
        b.run()


def test_expand_banks_replacements():
    b = MacroBuilder().expand("///a", "Hello").expand("///b", "cool dudes only")
    assert b._expansions == {"///a": "Hello", "///b": "cool dudes only"}
    assert b._expand_pattern is None  # no action-mode pattern


def test_expand_allows_one_action_pattern():
    import pytest
    b = MacroBuilder().tap("f5").expand("///go")
    assert b._expand_pattern == "///go"
    with pytest.raises(ValueError, match="Only one action-firing"):
        b.expand("///again")


def test_expand_rejects_self_triggering_replacement():
    import pytest
    with pytest.raises(ValueError, match="re-trigger"):
        MacroBuilder().expand("///a", "see ///a above")


def test_run_builds_expand_runner():
    from keydaemon.runner import ExpandRunner
    r = MacroBuilder().expand("///sig", "hello").run()
    try:
        assert isinstance(r, ExpandRunner)
    finally:
        r.stop()


def test_expand_plus_hotkey_rejected():
    import pytest
    b = MacroBuilder().expand("///sig", "hello").hotkey("f6")
    with pytest.raises(ValueError, match="both an expand pattern and a hotkey"):
        b.run()


def test_save_writes_and_overwrites(tmp_path, monkeypatch):
    from keydaemon import _paths
    monkeypatch.setattr(_paths, "macro_path", lambda n: tmp_path / f"{n}.toml")

    p = MacroBuilder().every(1).tap("space").loop().save("spacer", description="taps space")
    assert p.read_text(encoding="utf-8").count("tap:space") == 1

    # Python is the source of truth: saving again just overwrites.
    MacroBuilder().every(2).tap("w").loop().save("spacer")
    text = p.read_text(encoding="utf-8")
    assert "tap:w" in text
    assert "tap:space" not in text


def test_saved_macro_loads_back_identically(tmp_path, monkeypatch):
    from keydaemon import _paths, loader
    monkeypatch.setattr(_paths, "macro_path", lambda n: tmp_path / f"{n}.toml")

    b = MacroBuilder().every(0.25).jitter(0.06).click("left").loop().hotkey("f6").exit_key("f8")
    path = b.save("clicker")
    monkeypatch.setattr(loader, "macro_path", lambda n: path)

    lm = loader.load_macro("clicker")
    assert lm.actions == b._actions
    assert lm.hotkey == "f6"
    assert lm.exit_key == "f8"
    assert lm.interval == 0.25


def test_do_appends_reference():
    from keydaemon.actions import DoAction
    b = MacroBuilder().tap("w").do("greeting")
    assert b._actions[1] == DoAction(name="greeting")


def test_run_resolves_do_refs(tmp_path, monkeypatch):
    from keydaemon import loader
    monkeypatch.setattr(loader, "macro_path", lambda n: tmp_path / f"{n}.toml")
    (tmp_path / "child.toml").write_text(
        '[actions]\nsequence = ["tap:x"]\n', encoding="utf-8"
    )

    r = MacroBuilder().tap("a").do("child").run()
    try:
        from keydaemon.actions import DoAction
        assert r._actions == [TapAction(key="a"), TapAction(key="x")]
        assert not any(isinstance(a, DoAction) for a in r._actions)
    finally:
        r.stop()


def test_run_rejects_kill_combo_smuggled_via_do(tmp_path, monkeypatch):
    import pytest
    from keydaemon import loader
    from keydaemon.guard import KillKeyError

    monkeypatch.setattr(loader, "macro_path", lambda n: tmp_path / f"{n}.toml")
    (tmp_path / "finisher.toml").write_text(
        '[actions]\nsequence = ["press:alt", "tap:f12"]\n', encoding="utf-8"
    )

    # Parent holds half the kill combo, the sub-macro supplies the rest —
    # the guard must see the flattened sequence.
    b = MacroBuilder().press("ctrl").press("shift").do("finisher")
    with pytest.raises(KillKeyError):
        b.run()


def test_unresolved_do_action_refuses_to_execute():
    import pytest
    from keydaemon.actions import DoAction
    with pytest.raises(RuntimeError, match="Unresolved"):
        DoAction(name="x").execute(None)
