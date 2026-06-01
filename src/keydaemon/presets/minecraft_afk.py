"""
Minecraft singleplayer anti-AFK preset.

Fires every 4.5 minutes (±30s jitter): step forward, step back, jump.
Resets the AFK timer while barely moving the character.
Safe for singleplayer — do not use on public servers with anti-cheat.
"""
from __future__ import annotations

from keydaemon.builder import MacroBuilder


def build() -> MacroBuilder:
    return (
        MacroBuilder()
        .every(270)
        .jitter(30)
        .tap("w")
        .wait(0.1)
        .tap("s")
        .wait(0.05)
        .tap("space")
        .loop()
    )
