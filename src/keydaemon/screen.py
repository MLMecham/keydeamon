from __future__ import annotations


def get_pixel_color(x: int, y: int) -> tuple[int, int, int]:
    """Return the RGB color of the pixel at screen coordinates (x, y)."""
    from PIL import ImageGrab
    img = ImageGrab.grab(bbox=(x, y, x + 1, y + 1))
    return img.getpixel((0, 0))[:3]


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert a hex color string like '#3A7D44' or '3A7D44' to (r, g, b)."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        raise ValueError(f"Invalid hex color: {hex_color!r}")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return (r, g, b)


def color_matches(x: int, y: int, hex_color: str, tolerance: int = 10) -> bool:
    """Return True if the pixel at (x, y) is within tolerance of hex_color."""
    target = hex_to_rgb(hex_color)
    actual = get_pixel_color(x, y)
    return all(abs(a - t) <= tolerance for a, t in zip(actual, target))


def get_pixel_hex(x: int, y: int) -> str:
    """Return the hex color string of the pixel at (x, y), e.g. '#3A7D44'."""
    r, g, b = get_pixel_color(x, y)
    return f"#{r:02X}{g:02X}{b:02X}"
