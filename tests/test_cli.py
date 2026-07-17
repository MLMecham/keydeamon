import subprocess
import sys

from click.testing import CliRunner

from keydaemon import cli


def _pid_setup(tmp_path, monkeypatch):
    """Point the CLI's pid machinery at a temp dir."""
    monkeypatch.setattr(cli, "pids_dir", lambda: tmp_path)
    monkeypatch.setattr(cli, "pid_file", lambda name: tmp_path / f"{name}.pid")
    return tmp_path


def test_python_dash_m_entrypoint_works():
    # --detach respawns via `python -m keydaemon`; this used to crash with
    # "No module named keydaemon.__main__" and orphan a corpse PID.
    result = subprocess.run(
        [sys.executable, "-m", "keydaemon", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "keydaemon" in result.stdout


def test_stop_by_name_kills_only_that_pid(tmp_path, monkeypatch):
    _pid_setup(tmp_path, monkeypatch)
    (tmp_path / "afk.pid").write_text("111")
    (tmp_path / "clicker.pid").write_text("222")
    killed = []
    monkeypatch.setattr(cli, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(cli, "_kill_pid", killed.append)

    result = CliRunner().invoke(cli.main, ["stop", "afk"])

    assert result.exit_code == 0
    assert killed == [111]
    assert not (tmp_path / "afk.pid").exists()
    assert (tmp_path / "clicker.pid").exists()  # untouched


def test_stop_without_name_sweeps_all(tmp_path, monkeypatch):
    _pid_setup(tmp_path, monkeypatch)
    (tmp_path / "afk.pid").write_text("111")
    (tmp_path / "clicker.pid").write_text("222")
    killed = []
    monkeypatch.setattr(cli, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(cli, "_kill_pid", killed.append)

    result = CliRunner().invoke(cli.main, ["stop"])

    assert result.exit_code == 0
    assert sorted(killed) == [111, 222]
    assert list(tmp_path.glob("*.pid")) == []


def test_stop_unknown_name_reports_nothing_running(tmp_path, monkeypatch):
    _pid_setup(tmp_path, monkeypatch)
    result = CliRunner().invoke(cli.main, ["stop", "ghost"])
    assert result.exit_code == 0
    assert "No running process for 'ghost'" in result.output


def test_stop_cleans_stale_pid_without_killing(tmp_path, monkeypatch):
    _pid_setup(tmp_path, monkeypatch)
    (tmp_path / "afk.pid").write_text("111")
    killed = []
    monkeypatch.setattr(cli, "_pid_alive", lambda pid: False)
    monkeypatch.setattr(cli, "_kill_pid", killed.append)

    result = CliRunner().invoke(cli.main, ["stop", "afk"])

    assert killed == []  # dead process: nothing to kill
    assert not (tmp_path / "afk.pid").exists()  # but the stale file is removed
    assert "already stopped" in result.output


def test_detach_writes_per_name_pid_file(tmp_path, monkeypatch):
    _pid_setup(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "log_file", lambda: tmp_path / "log.txt")
    monkeypatch.setattr(cli, "macro_path", lambda n: tmp_path / f"{n}.toml")
    (tmp_path / "afk.toml").write_text("")  # the macro exists

    class FakeProc:
        pid = 4242

    monkeypatch.setattr(cli.subprocess, "Popen", lambda *a, **k: FakeProc())
    result = CliRunner().invoke(cli.main, ["run", "afk", "--detach"])

    assert result.exit_code == 0
    assert (tmp_path / "afk.pid").read_text() == "4242"


def test_detach_refuses_second_run_of_same_name(tmp_path, monkeypatch):
    _pid_setup(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "macro_path", lambda n: tmp_path / f"{n}.toml")
    (tmp_path / "afk.toml").write_text("")  # the macro exists
    (tmp_path / "afk.pid").write_text("111")
    monkeypatch.setattr(cli, "_pid_alive", lambda pid: True)

    result = CliRunner().invoke(cli.main, ["run", "afk", "--detach"])

    assert result.exit_code == 1
    assert "already running" in result.output
    assert (tmp_path / "afk.pid").read_text() == "111"  # not clobbered


def test_list_shows_running_status(tmp_path, monkeypatch):
    _pid_setup(tmp_path, monkeypatch)
    from keydaemon import loader
    monkeypatch.setattr(loader, "list_macros", lambda: ["afk", "clicker"])
    monkeypatch.setattr(loader, "is_profile", lambda name: False)
    (tmp_path / "afk.pid").write_text("111")
    monkeypatch.setattr(cli, "_pid_alive", lambda pid: True)

    result = CliRunner().invoke(cli.main, ["list"])

    assert "afk [running, PID 111]" in result.output
    assert "clicker" in result.output
    assert "clicker [running" not in result.output


def test_run_unknown_name_errors_and_names_presets(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "macro_path", lambda n: tmp_path / f"{n}.toml")
    result = CliRunner().invoke(cli.main, ["run", "ghost"])
    assert result.exit_code == 1
    assert "no macro or built-in preset named 'ghost'" in result.output
    assert "autoclicker" in result.output  # tells the user what IS available


def test_run_preset_installs_toml_first(monkeypatch, tmp_path):
    # `run autoclicker` with no TOML must materialize it, then run it. Stub the
    # actual run machinery — we only care about the install-on-first-run step.
    monkeypatch.setattr(cli, "macro_path", lambda n: tmp_path / f"{n}.toml")
    from keydaemon import export
    monkeypatch.setattr(export, "macro_path", lambda n: tmp_path / f"{n}.toml")

    installed = tmp_path / "autoclicker.toml"

    import keydaemon.loader as loader_mod
    import keydaemon.profile as profile_mod

    class FakeProfile:
        def __init__(self, *a, **k): ...
        def add_runner(self, r): ...
        def start(self): ...
        is_running = False

    monkeypatch.setattr(loader_mod, "macro_path", lambda n: tmp_path / f"{n}.toml")
    monkeypatch.setattr(profile_mod, "Profile", FakeProfile)

    result = CliRunner().invoke(cli.main, ["run", "autoclicker"])

    assert result.exit_code == 0, result.output
    assert installed.exists()
    assert "installed" in result.output
    # second run: file already there, no reinstall message
    result2 = CliRunner().invoke(cli.main, ["run", "autoclicker"])
    assert "installed" not in result2.output


def test_new_from_preset(monkeypatch, tmp_path):
    from keydaemon import export
    monkeypatch.setattr(export, "macro_path", lambda n: tmp_path / f"{n}.toml")

    result = CliRunner().invoke(cli.main, ["new", "myclicky", "--from", "autoclicker"])
    assert result.exit_code == 0
    assert (tmp_path / "myclicky.toml").exists()

    # refuses overwrite without --force
    result = CliRunner().invoke(cli.main, ["new", "myclicky", "--from", "autoclicker"])
    assert result.exit_code == 1
    assert "already exists" in result.output

    result = CliRunner().invoke(cli.main, ["new", "myclicky", "--from", "autoclicker", "--force"])
    assert result.exit_code == 0


def test_list_shows_uninstalled_presets(tmp_path, monkeypatch):
    _pid_setup(tmp_path, monkeypatch)
    from keydaemon import loader
    monkeypatch.setattr(loader, "list_macros", lambda: [])
    result = CliRunner().invoke(cli.main, ["list"])
    assert result.exit_code == 0
    assert "autoclicker [built-in preset" in result.output
    assert "minecraft_afk [built-in preset" in result.output


def test_list_hides_preset_shadowed_by_toml(tmp_path, monkeypatch):
    _pid_setup(tmp_path, monkeypatch)
    from keydaemon import loader
    monkeypatch.setattr(loader, "list_macros", lambda: ["autoclicker"])
    monkeypatch.setattr(loader, "is_profile", lambda name: False)
    result = CliRunner().invoke(cli.main, ["list"])
    assert result.output.count("autoclicker") == 1  # the TOML entry, no preset dup
