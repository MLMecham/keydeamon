"""
flower.py — draws a 6-petal rose curve in a browser sketch app until P is pressed.

Rose curve formula: r = RADIUS * |cos(k * theta)|
  k=3 with theta from 0 to 2*pi produces 6 symmetric petals.

Setup:
  1. Open a sketch/drawing app in the browser
  2. Run: uv run python examples/flower.py
  3. Hover your cursor over the canvas — the flower centers there
  4. Press P to stop

Adjust RADIUS, K, STEPS, and STEP_DELAY to taste.
"""

import math
import keydaemon
from pynput.mouse import Controller as _Mouse

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

RADIUS = 200    # petal size in pixels — how far each petal reaches from center
K = 3           # number of petals × 2 (k=3 → 6 petals, k=2 → 4, k=4 → 8, k=5 → 10)
STEPS = K * 200 # smoothness — scales automatically with petal count
SPEED = 3       # 1 = slowest, 5 = fastest
STEP_DELAY = [0.02, 0.01, 0.005, 0.002, 0.001][SPEED - 1]

# ---------------------------------------------------------------------------
# Build macro
# ---------------------------------------------------------------------------

cx, cy = int(_Mouse().position[0]), int(_Mouse().position[1])

# First point of the rose curve at theta=0: (cx + RADIUS, cy)
start_x = int(cx + RADIUS)
start_y = cy

b = keydaemon.macro()

# Teleport to curve start BEFORE pressing — avoids drawing a line from center to petal tip
b.move_to(start_x, start_y, jitter=False)
b.press("left")
b.wait(0.05)

# Trace the full curve with relative moves (SendInput — generates proper drag events)
prev_x, prev_y = start_x, start_y
for i in range(STEPS + 1):
    theta = 2 * math.pi * i / STEPS
    r = RADIUS * abs(math.cos(K * theta))
    x = int(cx + r * math.cos(theta))
    y = int(cy + r * math.sin(theta))
    b.move_by(x - prev_x, y - prev_y, jitter=False)
    b.wait(STEP_DELAY)
    prev_x, prev_y = x, y

# Close the curve — compensate for integer rounding drift over 600 steps
b.move_by(start_x - prev_x, start_y - prev_y, jitter=False)

b.release("left")
b.wait(0.1)

b.loop()
b.exit_key("p")

print(f"Drawing {K * 2}-petal flower centered at ({cx}, {cy}). Press P to stop.")

runner = b.run()
runner.join()

print("Stopped.")
