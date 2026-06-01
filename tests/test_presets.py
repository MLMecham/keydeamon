import pytest
import keydaemon
from keydaemon.builder import MacroBuilder
from keydaemon._types import LOOP_FOREVER


def test_minecraft_afk_returns_builder():
    b = keydaemon.preset("minecraft_afk")
    assert isinstance(b, MacroBuilder)


def test_minecraft_afk_has_interval():
    b = keydaemon.preset("minecraft_afk")
    assert b._interval is not None
    assert b._interval > 0


def test_minecraft_afk_has_jitter():
    b = keydaemon.preset("minecraft_afk")
    assert b._jitter > 0


def test_minecraft_afk_loops_forever():
    b = keydaemon.preset("minecraft_afk")
    assert b._repeat_times == LOOP_FOREVER


def test_minecraft_afk_has_actions():
    b = keydaemon.preset("minecraft_afk")
    assert len(b._actions) > 0


def test_unknown_preset_raises_import_error():
    with pytest.raises(ImportError, match="No preset named"):
        keydaemon.preset("nonexistent_preset_xyz")


def test_macro_returns_builder():
    b = keydaemon.macro()
    assert isinstance(b, MacroBuilder)


def test_macro_builder_is_empty():
    b = keydaemon.macro()
    assert b._actions == []
    assert b._interval is None
