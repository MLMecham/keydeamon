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


def pid_file() -> Path:
    return data_dir() / "keydaemon.pid"


def log_file() -> Path:
    return data_dir() / "keydaemon.log"


def config_file() -> Path:
    return data_dir() / "config.toml"


def macro_path(name: str) -> Path:
    name = name if name.endswith(".toml") else f"{name}.toml"
    return macros_dir() / name
