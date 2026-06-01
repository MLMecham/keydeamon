from unittest.mock import MagicMock, patch
import pytest
from keydaemon.screen import hex_to_rgb, color_matches, get_pixel_hex


def test_hex_to_rgb_with_hash():
    assert hex_to_rgb("#3A7D44") == (58, 125, 68)


def test_hex_to_rgb_without_hash():
    assert hex_to_rgb("FF0000") == (255, 0, 0)


def test_hex_to_rgb_invalid():
    with pytest.raises(ValueError):
        hex_to_rgb("ZZZ")


def test_color_matches_exact():
    with patch("keydaemon.screen.get_pixel_color", return_value=(58, 125, 68)):
        assert color_matches(0, 0, "#3A7D44", tolerance=0)


def test_color_matches_within_tolerance():
    with patch("keydaemon.screen.get_pixel_color", return_value=(60, 127, 70)):
        assert color_matches(0, 0, "#3A7D44", tolerance=5)


def test_color_not_matches_outside_tolerance():
    with patch("keydaemon.screen.get_pixel_color", return_value=(200, 0, 0)):
        assert not color_matches(0, 0, "#3A7D44", tolerance=10)


def test_get_pixel_hex_format():
    with patch("keydaemon.screen.get_pixel_color", return_value=(255, 0, 128)):
        result = get_pixel_hex(0, 0)
    assert result == "#FF0080"
