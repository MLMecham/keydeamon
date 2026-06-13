"""
autoclicker.py — a toggle-key autoclicker.

Launch it and it sits armed and idle. Press the TOGGLE_KEY to start clicking
wherever your cursor is; press it again to stop. Start/stop as often as you
like — the program keeps running. Press EXIT_KEY to quit for good.

Clicks happen at the cursor's current position, so just hover over the target.

Setup:
  1. Run: uv run python examples/autoclicker.py
  2. Hover over your target, press TOGGLE_KEY (default: F6) to start/stop
  3. Press EXIT_KEY (default: F8) to quit

Adjust the configuration below to taste.
"""

import keydaemon

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CPS = 10            # clicks per second
BUTTON = "left"     # "left", "right", or "middle"
CLICKS = 1          # clicks per fire — set 2 for double-clicks
JITTER = 0.02       # +/- seconds of random timing wobble (0 = perfectly steady)
TOGGLE_KEY = "f6"   # press to start clicking, press again to stop
EXIT_KEY = "f8"     # press to quit the program

# ---------------------------------------------------------------------------
# Build macro
# ---------------------------------------------------------------------------

interval = 1.0 / CPS

runner = (
    keydaemon.macro()
    .every(interval)
    .jitter(JITTER)
    .click(BUTTON, count=CLICKS)
    .loop()
    .hotkey(TOGGLE_KEY)     # arm behind the toggle key instead of running immediately
    .exit_key(EXIT_KEY)
    .run()
)

print(
    f"Autoclicker armed: {BUTTON} {CLICKS}x at ~{CPS} cps. "
    f"Press {TOGGLE_KEY.upper()} to start/stop, {EXIT_KEY.upper()} to quit."
)

runner.join()
print("Stopped.")
