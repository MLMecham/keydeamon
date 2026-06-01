from __future__ import annotations

import random
import time
from typing import Callable

from keydaemon._types import LOOP_FOREVER, SCHEDULER_TICK
from keydaemon.actions import Action, _SelfStop


def run_scheduled(
    actions: list[Action],
    interval: float | None,
    repeat_times: int,
    jitter: float,
    controller: object,
    stop_requested: Callable[[], bool],
) -> None:
    """
    Blocking scheduler loop — intended to run inside a DaemonRunner thread.

    Executes the action list, waits the interval (with jitter), then repeats.
    Sleeps in SCHEDULER_TICK increments so stop_requested() is checked frequently.
    """
    iteration = 0
    while not stop_requested():
        if repeat_times != LOOP_FOREVER and iteration >= repeat_times:
            break

        for action in actions:
            if stop_requested():
                return
            try:
                action.execute(controller, stop_requested)
            except _SelfStop:
                return

        iteration += 1

        # Don't sleep after the final iteration of a finite run
        is_last = repeat_times != LOOP_FOREVER and iteration >= repeat_times
        if interval is not None and not is_last and not stop_requested():
            delay = interval + random.uniform(-jitter, jitter)
            delay = max(0.0, delay)
            _interruptible_sleep(delay, stop_requested)


def _interruptible_sleep(seconds: float, stop_requested: Callable[[], bool]) -> None:
    """Sleep for `seconds` but wake up every SCHEDULER_TICK to check stop."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if stop_requested():
            return
        remaining = end - time.monotonic()
        time.sleep(min(SCHEDULER_TICK, remaining))
