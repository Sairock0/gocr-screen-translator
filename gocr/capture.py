"""Screen region capture (physical pixels) using mss."""
from __future__ import annotations

import numpy as np

from gocr import winapi


def clamp_rect(x: int, y: int, w: int, h: int) -> tuple[int, int, int, int]:
    """Moves the rectangle so it stays inside the monitor that contains its center."""
    mx, my, mw, mh = winapi.monitor_rect_physical(x + w // 2, y + h // 2)
    w, h = min(w, mw), min(h, mh)
    x = min(max(x, mx), mx + mw - w)
    y = min(max(y, my), my + mh - h)
    return int(x), int(y), int(w), int(h)


def intersect_monitor(x: int, y: int, w: int, h: int, center: tuple[int, int] | None = None) -> tuple[int, int, int, int]:
    """Crops the rectangle to the monitor (without moving it)."""
    cx, cy = center if center else (x + w // 2, y + h // 2)
    mx, my, mw, mh = winapi.monitor_rect_physical(cx, cy)
    x0, y0 = max(x, mx), max(y, my)
    x1, y1 = min(x + w, mx + mw), min(y + h, my + mh)
    return int(x0), int(y0), int(max(1, x1 - x0)), int(max(1, y1 - y0))


def grab(x: int, y: int, w: int, h: int) -> np.ndarray:
    """Returns the region as a BGRA array (height, width, 4)."""
    import mss  # one instance per call: mss is not thread-safe

    with mss.mss() as sct:
        shot = sct.grab({"left": int(x), "top": int(y), "width": int(w), "height": int(h)})
        return np.array(shot, dtype=np.uint8)
