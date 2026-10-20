"""Windows API helpers (ctypes). Other platforms get fallbacks so the UI can be
opened during development."""
from __future__ import annotations

import logging
import sys

from PySide6.QtCore import QRect
from PySide6.QtGui import QGuiApplication

log = logging.getLogger(__name__)

IS_WIN = sys.platform == "win32"

if IS_WIN:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)

    class POINT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

    class RECT(ctypes.Structure):
        _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                    ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT), ("rcWork", RECT),
                    ("dwFlags", wintypes.DWORD), ("szDevice", wintypes.WCHAR * 32)]

    user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
    user32.GetCursorPos.restype = wintypes.BOOL
    user32.MonitorFromPoint.argtypes = [POINT, wintypes.DWORD]
    user32.MonitorFromPoint.restype = wintypes.HANDLE
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFOEXW)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    user32.GetSystemMetrics.restype = ctypes.c_int
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_size_t]

    if ctypes.sizeof(ctypes.c_void_p) == 8:
        _GetWindowLong = user32.GetWindowLongPtrW
        _SetWindowLong = user32.SetWindowLongPtrW
        _LONG = ctypes.c_ssize_t
    else:
        _GetWindowLong = user32.GetWindowLongW
        _SetWindowLong = user32.SetWindowLongW
        _LONG = ctypes.c_long
    _GetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int]
    _GetWindowLong.restype = _LONG
    _SetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int, _LONG]
    _SetWindowLong.restype = _LONG

    GWL_EXSTYLE = -20
    WS_EX_TRANSPARENT = 0x00000020
    WS_EX_TOOLWINDOW = 0x00000080
    WS_EX_TOPMOST = 0x00000008
    WS_EX_NOACTIVATE = 0x08000000
    MONITOR_DEFAULTTONEAREST = 2
    SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
    SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79


def cursor_pos() -> tuple[int, int]:
    """Cursor position in physical pixels."""
    if IS_WIN:
        pt = POINT()
        if user32.GetCursorPos(ctypes.byref(pt)):
            return pt.x, pt.y
    from PySide6.QtGui import QCursor
    p = QCursor.pos()
    scr = QGuiApplication.screenAt(p) or QGuiApplication.primaryScreen()
    dpr = scr.devicePixelRatio() if scr else 1.0
    return int(p.x() * dpr), int(p.y() * dpr)


def virtual_screen() -> tuple[int, int, int, int]:
    """(x, y, width, height) of the virtual desktop in physical pixels."""
    if IS_WIN:
        return (user32.GetSystemMetrics(SM_XVIRTUALSCREEN), user32.GetSystemMetrics(SM_YVIRTUALSCREEN),
                user32.GetSystemMetrics(SM_CXVIRTUALSCREEN), user32.GetSystemMetrics(SM_CYVIRTUALSCREEN))
    scr = QGuiApplication.primaryScreen()
    g = scr.virtualGeometry()
    dpr = scr.devicePixelRatio()
    return int(g.x() * dpr), int(g.y() * dpr), int(g.width() * dpr), int(g.height() * dpr)


def _monitor_for_point(x: int, y: int):
    """Returns (device_name, (left, top, right, bottom)) of the monitor under the point."""
    pt = POINT(int(x), int(y))
    hmon = user32.MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST)
    info = MONITORINFOEXW()
    info.cbSize = ctypes.sizeof(MONITORINFOEXW)
    if not user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
        return None
    r = info.rcMonitor
    return info.szDevice, (r.left, r.top, r.right, r.bottom)


def monitor_rect_physical(x: int, y: int) -> tuple[int, int, int, int]:
    """Physical (x, y, w, h) rectangle of the monitor under the point."""
    if IS_WIN:
        m = _monitor_for_point(x, y)
        if m:
            l, t, r, b = m[1]
            return l, t, r - l, b - t
    return virtual_screen()


def _screen_and_origin(x: int, y: int):
    """QScreen under a physical point and the physical origin of that monitor.
    Qt 6 does not always use the device name (\\\\.\\DISPLAY2) as the screen name,
    so if it does not match, the screen is found by physical size and position."""
    screens = QGuiApplication.screens()
    if IS_WIN:
        m = _monitor_for_point(x, y)
        if m:
            name, (left, top, right, bottom) = m
            for s in screens:
                if s.name().lower() == name.lower():
                    return s, (left, top)
            pw, ph = right - left, bottom - top
            best, best_d = None, None
            for s in screens:
                g, dpr = s.geometry(), s.devicePixelRatio() or 1.0
                if abs(g.width() * dpr - pw) > 4 or abs(g.height() * dpr - ph) > 4:
                    continue
                d = min(abs(g.x() - left) + abs(g.y() - top), abs(g.x() - left / dpr) + abs(g.y() - top / dpr))
                if best_d is None or d < best_d:
                    best, best_d = s, d
            if best is not None:
                return best, (left, top)
    primary = QGuiApplication.primaryScreen()
    return primary, (0, 0)


def _same_monitor(a: tuple[int, int], b: tuple[int, int]) -> bool:
    ma, mb = _monitor_for_point(*a), _monitor_for_point(*b)
    return bool(ma and mb and ma == mb)


def phys_rect_to_logical(x: int, y: int, w: int, h: int) -> QRect:
    """Converts a rectangle in physical pixels to Qt logical coordinates."""
    cx, cy = x + w // 2, y + h // 2
    if IS_WIN:
        # Most reliable: anchor to the cursor, whose physical (Windows) and logical (Qt)
        # positions are both known. Works with several monitors and mixed scaling (100 %, 125 %...).
        try:
            from PySide6.QtGui import QCursor
            px, py = cursor_pos()
            if _same_monitor((px, py), (cx, cy)):
                lp = QCursor.pos()
                scr = QGuiApplication.screenAt(lp) or _screen_and_origin(cx, cy)[0]
                dpr = scr.devicePixelRatio() or 1.0
                return QRect(int(round(lp.x() + (x - px) / dpr)), int(round(lp.y() + (y - py) / dpr)),
                             max(1, int(round(w / dpr))), max(1, int(round(h / dpr))))
        except Exception:
            log.exception("Fallo al convertir coordenadas")
    scr, (ox, oy) = _screen_and_origin(cx, cy)
    if scr is None:
        return QRect(x, y, w, h)
    dpr = scr.devicePixelRatio() or 1.0
    g = scr.geometry()
    if IS_WIN:
        lx = g.x() + (x - ox) / dpr
        ly = g.y() + (y - oy) / dpr
    else:
        lx, ly = x / dpr, y / dpr
    return QRect(int(round(lx)), int(round(ly)), max(1, int(round(w / dpr))), max(1, int(round(h / dpr))))


def _screen_at_phys(x: int, y: int):
    if IS_WIN:
        try:
            from PySide6.QtGui import QCursor
            if _same_monitor(cursor_pos(), (x, y)):
                scr = QGuiApplication.screenAt(QCursor.pos())
                if scr is not None:
                    return scr
        except Exception:
            pass
    return _screen_and_origin(x, y)[0]


def dpr_at_phys(x: int, y: int) -> float:
    scr = _screen_at_phys(x, y)
    return scr.devicePixelRatio() if scr else 1.0


def logical_screen_rect_at_phys(x: int, y: int) -> QRect:
    scr = _screen_at_phys(x, y)
    return scr.geometry() if scr else QRect(0, 0, 1920, 1080)


def make_overlay_window(widget, click_through: bool) -> None:
    """Keeps a window from stealing focus (so the user stays in the game) and,
    optionally, lets clicks pass through it."""
    if not IS_WIN:
        return
    try:
        hwnd = int(widget.winId())
        style = _GetWindowLong(hwnd, GWL_EXSTYLE)
        style |= WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST
        if click_through:
            style |= WS_EX_TRANSPARENT
        else:
            style &= ~WS_EX_TRANSPARENT
        _SetWindowLong(hwnd, GWL_EXSTYLE, style)
    except Exception:
        log.exception("Could not adjust the overlay window style")


def exclude_from_capture(widget, exclude: bool = True) -> bool:
    """exclude=True: the window does not appear in screen captures (Windows 10 2004+), so live
    OCR never reads our own translations. exclude=False: visible to captures again
    (so the Windows snipping tool includes the translation)."""
    if not IS_WIN:
        return False
    try:
        fn = user32.SetWindowDisplayAffinity
        fn.argtypes = [wintypes.HWND, wintypes.DWORD]
        fn.restype = wintypes.BOOL
        ok = bool(fn(int(widget.winId()), 0x11 if exclude else 0x0))  # WDA_EXCLUDEFROMCAPTURE / WDA_NONE
        if not ok:
            log.warning("SetWindowDisplayAffinity failed (error %s)", ctypes.get_last_error())
        return ok
    except Exception:
        log.exception("Could not change the capture visibility")
        return False


SNIP_PROCESSES = {"screenclippinghost.exe", "snippingtool.exe", "screensketch.exe"}


def foreground_process_name() -> str:
    """Executable name of the foreground window (lowercase)."""
    if not IS_WIN:
        return ""
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                        ctypes.POINTER(wintypes.DWORD)]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        hwnd = user32.GetForegroundWindow()
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        h = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(520)
            size = wintypes.DWORD(520)
            if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return buf.value.rsplit("\\", 1)[-1].lower()
        finally:
            kernel32.CloseHandle(h)
    except Exception:
        pass
    return ""


def send_snip_keys(kind: str) -> None:
    """Re-sends Win+Shift+S (or Print Screen) after preparing the screen."""
    if not IS_WIN:
        return
    KEYUP, EXT = 0x2, 0x1
    kb = user32.keybd_event
    if kind == "prtsc":
        kb(0x2C, 0, EXT, 0)
        kb(0x2C, 0, EXT | KEYUP, 0)
        return
    kb(0x5B, 0, EXT, 0)          # Win
    kb(0xA0, 0, 0, 0)            # Shift
    kb(0x53, 0, 0, 0)            # S
    kb(0x53, 0, KEYUP, 0)
    kb(0xA0, 0, KEYUP, 0)
    kb(0x5B, 0, EXT | KEYUP, 0)


# --------------------------------------------------------------------------- start with Windows
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_NAME = "GOCR"


def _startup_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimized'
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        exe = exe[:-10] + "pythonw.exe"
    return f'"{exe}" -m gocr --minimized'


def set_start_with_windows(enabled: bool) -> bool:
    if not IS_WIN:
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, _RUN_NAME, 0, winreg.REG_SZ, _startup_command())
            else:
                try:
                    winreg.DeleteValue(key, _RUN_NAME)
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        log.exception("Could not change the start-with-Windows setting")
        return False


def is_start_with_windows() -> bool:
    if not IS_WIN:
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, _RUN_NAME)
            return True
    except Exception:
        return False


def set_dark_title_bar(widget, dark: bool) -> None:
    """Dark title bar for native dialogs (Windows 10 1809+/11)."""
    if not IS_WIN:
        return
    try:
        dwm = ctypes.WinDLL("dwmapi")
        value = ctypes.c_int(1 if dark else 0)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (new and old values)
            if dwm.DwmSetWindowAttribute(wintypes.HWND(int(widget.winId())), attr,
                                         ctypes.byref(value), ctypes.sizeof(value)) == 0:
                break
    except Exception:
        pass
