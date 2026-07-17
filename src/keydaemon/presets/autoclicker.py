"""
Autoclicker preset.

Arms a toggle hotkey: press the toggle key to start clicking the left mouse
button ~20x per second (±0.02s jitter) at the cursor, press it again
to stop. The program stays alive between presses so you can start/stop as often
as you like. Press the exit key to quit entirely.

The jitter keeps the timing slightly irregular so it doesn't look perfectly
robotic. For a configurable version (button, rate, keys), see
examples/autoclicker.py.
"""

from __future__ import annotations

from keydaemon.builder import MacroBuilder

# Single source of truth — build(), the startup message, and the tests all read
# these. Change a key here and everything that mentions it follows.
TOGGLE_KEY = "o"  # press to start clicking, press again to stop
EXIT_KEY = "esc"  # press to quit


def build() -> MacroBuilder:
    return (
        MacroBuilder()
        .times_per_second(10)
        .jitter(0.02)
        .click("left")
        .loop()
        .hotkey(TOGGLE_KEY)
        .exit_key(EXIT_KEY)
    )


if __name__ == "__main__":
    macro = build()
    # Derive the message from the built macro so the text can never disagree
    # with the actual key bindings.
    print(
        f"Autoclicker armed. Hover over your target. "
        f"Press {macro._hotkey.upper()} to start/stop, {macro._exit_key.upper()} to quit."
    )
    macro.run().join()
    print("Stopped.")
