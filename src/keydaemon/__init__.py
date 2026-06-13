"""
keydaemon — background daemon for keyboard/mouse automation.

Public API:
    macro()           → MacroBuilder (fluent builder)
    preset(name)      → MacroBuilder (pre-configured)
    load(name)        → MacroBuilder (from TOML file)
    stop_all()        → None
"""
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("keydaemon")
except PackageNotFoundError:
    __version__ = "0.0.0"

from keydaemon.builder import MacroBuilder
from keydaemon.profile import stop_all

__all__ = ["macro", "preset", "load", "stop_all", "__version__", "MacroBuilder"]


def macro() -> MacroBuilder:
    """Return a new empty MacroBuilder."""
    return MacroBuilder()


def preset(name: str) -> MacroBuilder:
    """
    Load a named built-in preset and return its pre-configured MacroBuilder.

    Available presets: minecraft_afk

    Raises:
        ImportError: if no preset with that name exists.
    """
    import importlib
    try:
        mod = importlib.import_module(f"keydaemon.presets.{name}")
    except ModuleNotFoundError:
        from keydaemon.presets import __all__ as available
        raise ImportError(
            f"No preset named {name!r}. Available: {', '.join(available)}"
        ) from None
    return mod.build()


def load(name: str) -> MacroBuilder:
    """
    Load a macro or profile from a TOML file in the keydaemon data directory.

    For profiles, returns a builder whose .run() starts all listed macros.
    """
    from keydaemon.loader import is_profile, load_macro, load_profile

    if is_profile(name):
        macro_names = load_profile(name)
        return _ProfileBuilder(name, macro_names)

    lm = load_macro(name)
    b = MacroBuilder()
    b._actions = lm.actions
    b._interval = lm.interval
    b._repeat_times = lm.repeat_times
    b._jitter = lm.jitter
    b._exit_key = lm.exit_key
    return b


class _ProfileBuilder(MacroBuilder):
    """Internal: starts multiple macros concurrently on .run()."""

    def __init__(self, profile_name: str, macro_names: list[str]) -> None:
        super().__init__()
        self._profile_name = profile_name
        self._macro_names = macro_names

    def run(self):  # type: ignore[override]
        from keydaemon.loader import load_macro
        from keydaemon.profile import Profile
        from keydaemon.runner import make_runner

        p = Profile(name=self._profile_name)
        for name in self._macro_names:
            p.add_runner(make_runner(load_macro(name)))
        p.start()
        return p
