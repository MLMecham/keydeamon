from keydaemon import loader
from keydaemon._types import LOOP_FOREVER


def _write(tmp_path, name, text):
    p = tmp_path / f"{name}.toml"
    p.write_text(text, encoding="utf-8")
    return p


def test_load_manual_macro_reads_hotkey_and_mode(tmp_path, monkeypatch):
    path = _write(
        tmp_path,
        "clicker",
        """
[meta]
name = "clicker"

[trigger]
type = "manual"
hotkey = "f6"
mode = "toggle"

[behavior]
every = 0.1
jitter = 0.02
repeat = -1

[actions]
sequence = ["click:left"]
""",
    )
    monkeypatch.setattr(loader, "macro_path", lambda name: path)

    lm = loader.load_macro("clicker")
    assert lm.hotkey == "f6"
    assert lm.hotkey_mode == "toggle"
    assert lm.interval == 0.1
    assert lm.repeat_times == LOOP_FOREVER
    assert len(lm.actions) == 1


def test_load_macro_defaults_hotkey_none(tmp_path, monkeypatch):
    path = _write(
        tmp_path,
        "afk",
        """
[meta]
name = "afk"

[trigger]
type = "loop"

[behavior]
every = 5

[actions]
sequence = ["tap:space"]
""",
    )
    monkeypatch.setattr(loader, "macro_path", lambda name: path)

    lm = loader.load_macro("afk")
    assert lm.hotkey is None
    assert lm.hotkey_mode == "toggle"


def test_stop_all_action_parses(tmp_path, monkeypatch):
    path = _write(
        tmp_path,
        "bail",
        """
[meta]
name = "bail"

[trigger]
type = "loop"

[actions]
sequence = ["tap:space", "stop:all"]
""",
    )
    monkeypatch.setattr(loader, "macro_path", lambda name: path)

    from keydaemon.actions import KillAllAction
    lm = loader.load_macro("bail")
    assert isinstance(lm.actions[1], KillAllAction)


def test_kill_combo_hotkey_rejected_at_load(tmp_path, monkeypatch):
    path = _write(
        tmp_path,
        "evil",
        """
[meta]
name = "evil"

[trigger]
type = "manual"
hotkey = "<ctrl>+<shift>+<alt>+<f12>"

[actions]
sequence = ["click:left"]
""",
    )
    monkeypatch.setattr(loader, "macro_path", lambda name: path)

    import pytest
    from keydaemon.guard import KillKeyError
    with pytest.raises(KillKeyError):
        loader.load_macro("evil")


def test_kill_combo_synthesis_rejected_at_load(tmp_path, monkeypatch):
    path = _write(
        tmp_path,
        "sneaky",
        """
[meta]
name = "sneaky"

[trigger]
type = "loop"

[actions]
sequence = ["press:ctrl", "press:shift", "press:alt", "tap:f12"]
""",
    )
    monkeypatch.setattr(loader, "macro_path", lambda name: path)

    import pytest
    from keydaemon.guard import KillKeyError
    with pytest.raises(KillKeyError):
        loader.load_macro("sneaky")


def test_description_is_loaded(tmp_path, monkeypatch):
    path = _write(
        tmp_path,
        "descd",
        """
[meta]
name = "descd"
description = "Does a thing."

[trigger]
type = "loop"

[actions]
sequence = ["tap:space"]
""",
    )
    monkeypatch.setattr(loader, "macro_path", lambda name: path)
    assert loader.load_macro("descd").description == "Does a thing."


def test_self_triggering_expansion_rejected(tmp_path, monkeypatch):
    path = _write(
        tmp_path,
        "looper",
        """
[meta]
name = "looper"

[trigger]
type = "expand"
pattern = "///a"

[behavior]
replace = "see ///a above"
""",
    )
    monkeypatch.setattr(loader, "macro_path", lambda name: path)

    import pytest
    with pytest.raises(ValueError, match="re-trigger"):
        loader.load_macro("looper")


def test_expansions_table_loads(tmp_path, monkeypatch):
    path = _write(
        tmp_path,
        "snippets",
        """
[meta]
name = "snippets"

[trigger]
type = "expand"

[expansions]
"///a" = "Hello"
"///b" = "cool dudes only"
""",
    )
    monkeypatch.setattr(loader, "macro_path", lambda name: path)

    lm = loader.load_macro("snippets")
    assert lm.trigger_type == "expand"
    assert lm.expansions == {"///a": "Hello", "///b": "cool dudes only"}


def test_expansions_bank_cross_trigger_rejected(tmp_path, monkeypatch):
    path = _write(
        tmp_path,
        "bad",
        """
[meta]
name = "bad"

[trigger]
type = "expand"

[expansions]
"///a" = "Hello"
"///b" = "see ///a for details"
""",
    )
    monkeypatch.setattr(loader, "macro_path", lambda name: path)

    import pytest
    with pytest.raises(ValueError, match="re-trigger"):
        loader.load_macro("bad")


# ---------------------------------------------------------------------------
# do: references (TOML) and resolve_do_actions (builder .do())
# ---------------------------------------------------------------------------

def _write_macros(tmp_path, monkeypatch, files):
    """Write several macro TOMLs and point the loader's macros dir at them."""
    for name, text in files.items():
        _write(tmp_path, name, text)
    monkeypatch.setattr(loader, "macro_path", lambda name: tmp_path / f"{name}.toml")


_CHILD = """
[actions]
sequence = ["tap:x", "wait:0.1"]
"""


def test_do_inlines_target_actions(tmp_path, monkeypatch):
    from keydaemon.actions import TapAction, WaitAction

    _write_macros(
        tmp_path,
        monkeypatch,
        {
            "parent": """
[trigger]
type = "loop"

[actions]
sequence = ["tap:a", "do:child", "tap:b"]
""",
            "child": _CHILD,
        },
    )
    lm = loader.load_macro("parent")
    assert lm.actions == [
        TapAction(key="a"),
        TapAction(key="x"),
        WaitAction(seconds=0.1),
        TapAction(key="b"),
    ]


def test_do_circular_reference_rejected(tmp_path, monkeypatch):
    import pytest

    _write_macros(
        tmp_path,
        monkeypatch,
        {
            "a": '[actions]\nsequence = ["do:b"]\n',
            "b": '[actions]\nsequence = ["do:a"]\n',
        },
    )
    with pytest.raises(ValueError, match="Circular"):
        loader.load_macro("a")


def test_do_profile_target_rejected(tmp_path, monkeypatch):
    import pytest

    _write_macros(
        tmp_path,
        monkeypatch,
        {
            "parent": '[actions]\nsequence = ["do:team"]\n',
            # meta-style profile declaration (load_profile accepts both forms)
            "team": '[meta]\ntype = "profile"\n\n[macros]\nrun = ["x"]\n',
        },
    )
    with pytest.raises(ValueError, match="profile"):
        loader.load_macro("parent")


def test_resolve_do_actions_flattens_refs(tmp_path, monkeypatch):
    from keydaemon.actions import DoAction, TapAction, WaitAction

    _write_macros(tmp_path, monkeypatch, {"child": _CHILD})
    resolved = loader.resolve_do_actions(
        [TapAction(key="a"), DoAction(name="child"), TapAction(key="b")]
    )
    assert resolved == [
        TapAction(key="a"),
        TapAction(key="x"),
        WaitAction(seconds=0.1),
        TapAction(key="b"),
    ]


def test_resolve_do_actions_reads_fresh_each_call(tmp_path, monkeypatch):
    from keydaemon.actions import DoAction, TapAction

    _write_macros(tmp_path, monkeypatch, {"child": '[actions]\nsequence = ["tap:x"]\n'})
    ref = [DoAction(name="child")]
    assert loader.resolve_do_actions(ref) == [TapAction(key="x")]

    _write(tmp_path, "child", '[actions]\nsequence = ["tap:y"]\n')
    assert loader.resolve_do_actions(ref) == [TapAction(key="y")]


def test_resolve_do_actions_missing_target(tmp_path, monkeypatch):
    import pytest
    from keydaemon.actions import DoAction

    _write_macros(tmp_path, monkeypatch, {})
    with pytest.raises(FileNotFoundError):
        loader.resolve_do_actions([DoAction(name="ghost")])


def test_resolve_do_actions_catches_toml_cycles(tmp_path, monkeypatch):
    import pytest
    from keydaemon.actions import DoAction

    _write_macros(tmp_path, monkeypatch, {"loopy": '[actions]\nsequence = ["do:loopy"]\n'})
    with pytest.raises(ValueError, match="Circular"):
        loader.resolve_do_actions([DoAction(name="loopy")])
