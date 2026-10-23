"""Reusable CATIA desktop capture helpers; Windows dependencies are lazy-loaded."""
from __future__ import annotations
import time
from typing import Any


def find_catia_window(document_name: str) -> int:
    """Find the visible CATIA V5 window whose title contains the document name."""
    try:
        import win32gui
    except ImportError as exc:
        raise RuntimeError("Finding a CATIA window requires pywin32 on Windows.") from exc
    matches: list[int] = []
    def callback(hwnd: int, _unused: Any) -> None:
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if "CATIA V5" in title.upper() and document_name.lower() in title.lower():
            matches.append(hwnd)
    win32gui.EnumWindows(callback, None)
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one visible CATIA V5 window for {document_name!r}; found {len(matches)}.")
    return matches[0]


def prepare_window(hwnd: int, settle_seconds: float = 1.0) -> tuple[int, int, int, int]:
    """Restore/foreground CATIA and return its visible screen region."""
    try:
        import pyautogui
        import win32con
        import win32gui
    except ImportError as exc:
        raise RuntimeError("Preparing a CATIA window requires pyautogui and pywin32 on Windows.") from exc
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        time.sleep(settle_seconds)
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass  # Windows may deny foreground activation; validate the region below.
    time.sleep(settle_seconds)
    if win32gui.IsIconic(hwnd):
        raise RuntimeError("CATIA window is minimized and cannot be captured.")
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    screen_w, screen_h = pyautogui.size()
    x1, y1 = max(0, left), max(0, top)
    x2, y2 = min(screen_w, right), min(screen_h, bottom)
    if x2-x1 <= 300 or y2-y1 <= 200:
        raise RuntimeError(f"CATIA window capture region is too small: {(x1,y1,x2-x1,y2-y1)}")
    return x1, y1, x2-x1, y2-y1


def capture(region: tuple[int, int, int, int]):
    """Capture a screen region as an RGB NumPy array."""
    try:
        import numpy as np
        import pyautogui
    except ImportError as exc:
        raise RuntimeError("Screen capture requires pyautogui and NumPy on a desktop session.") from exc
    return np.asarray(pyautogui.screenshot(region=region).convert("RGB"))


def selection_change_mask(before, after, color_range=(4,110,110,28,255,255), difference_threshold=45):
    """Mask pixels that changed and became CATIA's orange selection color."""
    import cv2
    import numpy as np
    if before.shape != after.shape:
        raise ValueError("Before/after screenshots must have identical dimensions.")
    if before.ndim != 3 or before.shape[2] != 3:
        raise ValueError("Screenshots must be three-channel RGB arrays.")
    h_min,s_min,v_min,h_max,s_max,v_max = color_range
    hsv = cv2.cvtColor(after, cv2.COLOR_RGB2HSV)
    orange = cv2.inRange(hsv, np.array([h_min,s_min,v_min],dtype=np.uint8), np.array([h_max,s_max,v_max],dtype=np.uint8))
    diff = cv2.absdiff(before, after)
    changed = np.max(diff, axis=2) > difference_threshold
    return np.where((orange > 0) & changed, 255, 0).astype(np.uint8)
