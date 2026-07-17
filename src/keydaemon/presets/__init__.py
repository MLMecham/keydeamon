"""Built-in presets. Run with `keydaemon run <name>` or load with keydaemon.preset(name)."""


def available() -> list[str]:
    """Names of every built-in preset, discovered from the package contents."""
    import pkgutil
    return sorted(
        m.name for m in pkgutil.iter_modules(__path__) if not m.name.startswith("_")
    )
