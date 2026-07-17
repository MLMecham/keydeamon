from pathlib import Path
from platformdirs import user_data_dir

APP_NAME = "keydaemon"


def data_dir() -> Path:
    p = Path(user_data_dir(APP_NAME))
    p.mkdir(parents=True, exist_ok=True)
    return p


def macros_dir() -> Path:
    p = data_dir() / "macros"
    p.mkdir(parents=True, exist_ok=True)
    return p


def pids_dir() -> Path:
    p = data_dir() / "pids"
    p.mkdir(parents=True, exist_ok=True)
    return p


def pid_file(name: str) -> Path:
    """PID file for one detached macro/profile — one file per name, so several
    detached runs can coexist and be stopped individually."""
    return pids_dir() / f"{name}.pid"


def log_file() -> Path:
    return data_dir() / "keydaemon.log"


def config_file() -> Path:
    return data_dir() / "config.toml"


def macro_path(name: str) -> Path:
    name = name if name.endswith(".toml") else f"{name}.toml"
    return macros_dir() / name
