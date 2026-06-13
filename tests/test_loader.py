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
