"""Preset -> TOML serialization and the install flow."""
import pytest

import keydaemon
from keydaemon import export, loader
from keydaemon._types import LOOP_FOREVER
from keydaemon.actions import (
    ClickAction,
    KillAllAction,
    MoveToAction,
    SelfStopAction,
    TapAction,
)
from keydaemon.builder import MacroBuilder
from keydaemon.export import builder_to_toml, install_preset
from keydaemon.presets import available


def _load_from_text(tmp_path, monkeypatch, name, text):
    p = tmp_path / f"{name}.toml"
    p.write_text(text, encoding="utf-8")
    monkeypatch.setattr(loader, "macro_path", lambda n: p)
    return loader.load_macro(name)


def test_available_finds_shipped_presets():
    names = available()
    assert "autoclicker" in names
    assert "minecraft_afk" in names


@pytest.mark.parametrize("preset_name", ["autoclicker", "minecraft_afk"])
def test_preset_roundtrips_through_toml(tmp_path, monkeypatch, preset_name):
    b = keydaemon.preset(preset_name)
    text = builder_to_toml(b, name=preset_name, description="desc")
    lm = _load_from_text(tmp_path, monkeypatch, preset_name, text)

    assert lm.actions == b._actions
    assert lm.interval == b._interval
    assert lm.repeat_times == b._repeat_times
    assert lm.jitter == b._jitter
    assert lm.exit_key == b._exit_key
    assert lm.hotkey == b._hotkey
    if b._hotkey:
        assert lm.hotkey_mode == b._hotkey_mode


def test_stop_actions_roundtrip(tmp_path, monkeypatch):
    b = MacroBuilder().tap("space").stop_self()
    b._actions.append(KillAllAction())
    text = builder_to_toml(b, name="stops")
    lm = _load_from_text(tmp_path, monkeypatch, "stops", text)
    assert lm.actions == [TapAction(key="space"), SelfStopAction(), KillAllAction()]


def test_repeat_forever_serializes_as_minus_one():
    b = MacroBuilder().click("left").loop()
    text = builder_to_toml(b, name="x")
    assert "repeat = -1" in text
    assert b._repeat_times == LOOP_FOREVER


def test_unexpressible_action_raises():
    b = MacroBuilder()
    b._actions.append(MoveToAction(x=1, y=2, jitter=False))
    with pytest.raises(ValueError, match="jitter=False"):
        builder_to_toml(b, name="x")


def test_newline_in_string_raises():
    b = MacroBuilder().type("two\nlines")
    with pytest.raises(ValueError, match="newline"):
        builder_to_toml(b, name="x")


def test_install_preset_writes_file(tmp_path, monkeypatch):
    monkeypatch.setattr(export, "macro_path", lambda n: tmp_path / f"{n}.toml")
    from keydaemon.presets import autoclicker
    path = install_preset("autoclicker")
    assert path.exists()
    assert f'hotkey = "{autoclicker.TOGGLE_KEY}"' in path.read_text(encoding="utf-8")


def test_install_preset_refuses_overwrite_without_force(tmp_path, monkeypatch):
    monkeypatch.setattr(export, "macro_path", lambda n: tmp_path / f"{n}.toml")
    install_preset("autoclicker")
    with pytest.raises(FileExistsError):
        install_preset("autoclicker")
    install_preset("autoclicker", force=True)  # regeneration path


def test_install_preset_as_fork_name(tmp_path, monkeypatch):
    monkeypatch.setattr(export, "macro_path", lambda n: tmp_path / f"{n}.toml")
    path = install_preset("autoclicker", as_name="myclicky")
    assert path.name == "myclicky.toml"
    assert 'name = "myclicky"' in path.read_text(encoding="utf-8")


def test_install_unknown_preset_raises():
    with pytest.raises(ValueError, match="No built-in preset"):
        install_preset("ghost")


def test_expand_bank_roundtrips(tmp_path, monkeypatch):
    b = (MacroBuilder()
         .expand("///sig", "Mitchell Mecham")
         .expand("///gg", "good game!"))
    text = builder_to_toml(b, name="sig", description="signature")
    lm = _load_from_text(tmp_path, monkeypatch, "sig", text)
    assert lm.trigger_type == "expand"
    assert lm.expansions == {"///sig": "Mitchell Mecham", "///gg": "good game!"}
    assert lm.expand_pattern is None


def test_expand_with_actions_roundtrips(tmp_path, monkeypatch):
    b = MacroBuilder().tap("f5").wait(0.2).expand("///reload")
    text = builder_to_toml(b, name="reload")
    lm = _load_from_text(tmp_path, monkeypatch, "reload", text)
    assert lm.trigger_type == "expand"
    assert lm.expand_pattern == "///reload"
    assert lm.expand_replace is None
    assert lm.actions == b._actions
