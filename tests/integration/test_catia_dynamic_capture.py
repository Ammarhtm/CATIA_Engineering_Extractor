
from pathlib import Path
import time

import pyautogui
import win32con
import win32gui

from catia_extractor.catia.connection import connect_to_catia
from test_catia_dynamic_window import find_catia_windows


OUTPUT = Path("output/debug/dynamic_capture")


def test_catia_dynamic_capture():
    session = connect_to_catia()
    document = session.document

    windows = find_catia_windows()
    assert len(windows) == 1, (
        "Expected exactly one CATIA window"
    )

    hwnd = windows[0]["hwnd"]

    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        time.sleep(1)

    # Bring CATIA to foreground where Windows permits it.
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception as exc:
        print("Foreground request:", repr(exc))

    time.sleep(1)

    # Get visible window bounds.
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)

    screen_width, screen_height = pyautogui.size()

    # Clip to the primary screen.
    x1 = max(0, left)
    y1 = max(0, top)
    x2 = min(screen_width, right)
    y2 = min(screen_height, bottom)

    assert x2 > x1 and y2 > y1, (
        "CATIA window is outside the primary screen"
    )

    OUTPUT.mkdir(parents=True, exist_ok=True)

    image = pyautogui.screenshot(
        region=(x1, y1, x2 - x1, y2 - y1)
    )

    path = OUTPUT / "catia_window.png"
    image.save(path)

    print("\n====== DYNAMIC CAPTURE ======")
    print("Document:", document.Name)
    print("Window rect:", (left, top, right, bottom))
    print("Captured region:", (x1, y1, x2, y2))
    print("Image size:", image.size)
    print("Saved:", path.resolve())

    assert path.exists()
    assert image.width > 300
    assert image.height > 200
