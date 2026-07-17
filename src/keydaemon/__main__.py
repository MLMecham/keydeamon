"""Enable `python -m keydaemon` — the detached runner respawns through this."""
from keydaemon.cli import main

if __name__ == "__main__":
    main()
