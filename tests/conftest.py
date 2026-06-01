"""Mock pynput at import time so tests never need a display or real keyboard."""
import sys
from unittest.mock import MagicMock

pynput_mock = MagicMock()
sys.modules["pynput"] = pynput_mock
sys.modules["pynput.keyboard"] = pynput_mock.keyboard
sys.modules["pynput.mouse"] = pynput_mock.mouse
