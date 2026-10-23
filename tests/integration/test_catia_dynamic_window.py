
import time

import win32con
import win32gui
import win32process

from catia_extractor.catia.connection import connect_to_catia


def find_catia_windows():
    """Find visible top-level CATIA V5 windows."""
    windows = []

    def callback(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return

        title = win32gui.GetWindowText(hwnd)

        if "CATIA V5" not in title.upper():
            return

        _, pid = win32process.GetWindowThreadProcessId(hwnd)

        windows.append({
            "hwnd": hwnd,
            "title": title,
            "pid": pid,
        })

    win32gui.EnumWindows(callback, None)
    return windows


def restore_catia_window(hwnd):
    """Restore CATIA if minimized, then read its position."""

    if win32gui.IsIconic(hwnd):
        print("\nCATIA is minimized -> restoring...")
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        time.sleep(1)

    assert not win32gui.IsIconic(hwnd), (
        "CATIA could not be restored."
    )

    left, top, right, bottom = win32gui.GetWindowRect(hwnd)

    width = right - left
    height = bottom - top

    assert width > 300, f"Invalid CATIA width: {width}"
    assert height > 200, f"Invalid CATIA height: {height}"

    return {
        "hwnd": hwnd,
        "rect": (left, top, right, bottom),
        "width": width,
        "height": height,
    }


def test_catia_dynamic_window():
    session = connect_to_catia()
    document = session.document

    windows = find_catia_windows()

    print("\n====== CATIA WINDOW DETECTION ======")
    print("Active document:", document.Name)
    print("Windows found:", len(windows))

    assert windows, "No CATIA V5 window found"

    for window in windows:
        print("\nTitle:", window["title"])
        print("HWND:", window["hwnd"])
        print("PID:", window["pid"])
        print("Minimized:", bool(win32gui.IsIconic(window["hwnd"])))

    assert len(windows) == 1, (
        "Multiple CATIA windows found. "
        "Session-to-window matching is required."
    )

    window = windows[0]

    result = restore_catia_window(window["hwnd"])

    print("\n====== CATIA WINDOW READY ======")
    print("HWND:", result["hwnd"])
    print("PID:", window["pid"])
    print("Rect:", result["rect"])
    print("Width:", result["width"])
    print("Height:", result["height"])

    print("\nCATIA window detection: SUCCESS")

    assert result["width"] > 300
    assert result["height"] > 200
