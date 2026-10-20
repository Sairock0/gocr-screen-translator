"""Global keyboard and mouse hooks (WH_KEYBOARD_LL / WH_MOUSE_LL).

They run on their own thread with their own message loop, so they keep responding even when
the UI is busy. While the hotkey is held:
  * the mouse wheel is swallowed (the game does not zoom/scroll) and resizes the area,
  * Shift / Ctrl / Alt are swallowed too so they never reach the game,
  * Esc cancels.
"""
from __future__ import annotations

import logging
import sys
import threading

from PySide6.QtCore import QObject, Signal

log = logging.getLogger(__name__)

IS_WIN = sys.platform == "win32"

MOD_SHIFT, MOD_CTRL, MOD_ALT = 1, 2, 4
MOD_FREE = 16      # wheel used without holding the hotkey (live mode with on/off)

# Keys that cannot be used as the hotkey (they are used to resize the area)
VK_SHIFT, VK_CONTROL, VK_MENU = 0x10, 0x11, 0x12
VK_LSHIFT, VK_RSHIFT, VK_LCONTROL, VK_RCONTROL, VK_LMENU, VK_RMENU = 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5
VK_LWIN, VK_RWIN, VK_ESCAPE = 0x5B, 0x5C, 0x1B
VK_SNAPSHOT, VK_S = 0x2C, 0x53
MOD_VKS = {
    VK_SHIFT: MOD_SHIFT, VK_LSHIFT: MOD_SHIFT, VK_RSHIFT: MOD_SHIFT,
    VK_CONTROL: MOD_CTRL, VK_LCONTROL: MOD_CTRL, VK_RCONTROL: MOD_CTRL,
    VK_MENU: MOD_ALT, VK_LMENU: MOD_ALT, VK_RMENU: MOD_ALT,
}
FORBIDDEN_HOTKEY_VKS = set(MOD_VKS) | {VK_LWIN, VK_RWIN, VK_ESCAPE}


class HookSignals(QObject):
    pressed = Signal()             # hotkey pressed -> show the area
    released = Signal()            # hotkey released -> translate
    cancelled = Signal()           # Esc while aiming
    wheel = Signal(int, int)       # wheel delta, modifiers (MOD_*)
    dismiss = Signal()             # Esc while a translation is on screen
    snip = Signal(str)             # Win+Shift+S or Print Screen while live mode is on


if IS_WIN:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    LRESULT = ctypes.c_ssize_t
    ULONG_PTR = ctypes.c_size_t
    HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                    ("flags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class MSLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [("pt", wintypes.POINT), ("mouseData", wintypes.DWORD),
                    ("flags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
    user32.SetWindowsHookExW.restype = wintypes.HHOOK
    user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
    user32.CallNextHookEx.restype = LRESULT
    user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
    user32.UnhookWindowsHookEx.restype = wintypes.BOOL
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.GetMessageW.restype = wintypes.BOOL
    user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostThreadMessageW.restype = wintypes.BOOL
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD

    WH_KEYBOARD_LL, WH_MOUSE_LL = 13, 14
    HC_ACTION = 0
    WM_QUIT = 0x0012
    WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0100, 0x0101, 0x0104, 0x0105
    WM_MOUSEWHEEL, WM_XBUTTONDOWN, WM_XBUTTONUP = 0x020A, 0x020B, 0x020C
    WM_MBUTTONDOWN, WM_MBUTTONUP = 0x0207, 0x0208
    LLKHF_INJECTED = 0x10
    LLMHF_INJECTED = 0x01


class InputHook:
    """Manages the hooks. Signals are emitted from the hook thread and Qt delivers them on
    the main thread (queued connection)."""

    def __init__(self, signals: HookSignals):
        self.signals = signals
        self.hotkey: dict = {"kind": "key", "code": 0x77}
        self.enabled = True          # paused from the tray
        self.capturing = False       # the settings window is waiting for a new key
        self.overlay_visible = False
        self.free_wheel = False      # live mode (on/off): the wheel resizes the area without the hotkey
        self.snip_intercept = False  # live mode: prepare the screen before the Windows snip
        self._win = False
        self._active = False         # the hotkey is held
        self._wait_release = False   # cancelled with Esc; ignore until the hotkey is released
        self._mods = 0
        self._swallowed: set[int] = set()
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._kb_hook = None
        self._ms_hook = None
        self._kb_proc = None
        self._ms_proc = None
        self.ok = False
        self.attempted = False

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        if not IS_WIN:
            log.warning("Global hooks only work on Windows")
            return
        self._thread = threading.Thread(target=self._run, name="GOCR-hooks", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if IS_WIN and self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            if self._thread:
                self._thread.join(timeout=1.5)

    def reset(self) -> None:
        self._active = False
        self._wait_release = False

    @property
    def active(self) -> bool:
        return self._active

    def _run(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        self._kb_proc = HOOKPROC(self._keyboard_proc)
        self._ms_proc = HOOKPROC(self._mouse_proc)
        hmod = kernel32.GetModuleHandleW(None)
        self._kb_hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._kb_proc, hmod, 0)
        self._ms_hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._ms_proc, hmod, 0)
        if not self._kb_hook or not self._ms_hook:
            log.error("Could not install the hooks (error %s)", ctypes.get_last_error())
        else:
            self.ok = True
            log.info("Keyboard and mouse hooks installed")
        self.attempted = True
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        if self._kb_hook:
            user32.UnhookWindowsHookEx(self._kb_hook)
        if self._ms_hook:
            user32.UnhookWindowsHookEx(self._ms_hook)
        log.info("Hooks removed")

    # ------------------------------------------------------------------ shared logic
    def _hotkey_down(self) -> None:
        if not self._active and not self._wait_release:
            self._active = True
            self.signals.pressed.emit()

    def _hotkey_up(self) -> None:
        if self._active:
            self._active = False
            self.signals.released.emit()
        self._wait_release = False

    def _listening(self) -> bool:
        return self.enabled and not self.capturing

    # ------------------------------------------------------------------ keyboard
    def _keyboard_proc(self, n_code, w_param, l_param):
        try:
            if n_code == HC_ACTION:
                kb = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                vk = kb.vkCode
                down = w_param in (WM_KEYDOWN, WM_SYSKEYDOWN)
                up = w_param in (WM_KEYUP, WM_SYSKEYUP)

                if vk in (VK_LWIN, VK_RWIN):
                    self._win = down if (down or up) else self._win
                if vk in MOD_VKS:  # tracked even when the keys are swallowed
                    if down:
                        self._mods |= MOD_VKS[vk]
                    elif up:
                        self._mods &= ~MOD_VKS[vk]

                if not (kb.flags & LLKHF_INJECTED) and self._listening():
                    hk = self.hotkey
                    if hk.get("kind") == "key" and vk == hk.get("code"):
                        if down:
                            self._hotkey_down()
                        elif up:
                            self._hotkey_up()
                        return 1

                    if self.snip_intercept and down and (
                            vk == VK_SNAPSHOT or (vk == VK_S and self._win and self._mods & MOD_SHIFT)):
                        self._swallowed.add(vk)
                        self.signals.snip.emit("prtsc" if vk == VK_SNAPSHOT else "winshifts")
                        return 1

                    if self._active and down:
                        if vk == VK_ESCAPE:
                            self._active = False
                            self._wait_release = True
                            self._swallowed.add(vk)
                            self.signals.cancelled.emit()
                            return 1
                        if vk in MOD_VKS:
                            self._swallowed.add(vk)
                            return 1

                    if down and vk == VK_ESCAPE and self.overlay_visible:
                        self._swallowed.add(vk)
                        self.signals.dismiss.emit()
                        return 1

                if up and vk in self._swallowed:
                    self._swallowed.discard(vk)
                    return 1
        except Exception:  # never let an exception block the keyboard
            log.exception("Keyboard hook error")
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    # ------------------------------------------------------------------ mouse
    def _mouse_proc(self, n_code, w_param, l_param):
        try:
            if n_code == HC_ACTION and w_param != 0x0200:  # skip WM_MOUSEMOVE quickly
                ms = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                if not (ms.flags & LLMHF_INJECTED) and self._listening():
                    if w_param == WM_MOUSEWHEEL:
                        delta = ctypes.c_short((ms.mouseData >> 16) & 0xFFFF).value
                        if self._active:
                            self.signals.wheel.emit(delta, self._mods)
                            return 1
                        if self.free_wheel:  # live mode with on/off: the wheel resizes without the hotkey
                            self.signals.wheel.emit(delta, self._mods | MOD_FREE)
                            return 1
                    hk = self.hotkey
                    if hk.get("kind") == "mouse":
                        code = hk.get("code")
                        if w_param in (WM_XBUTTONDOWN, WM_XBUTTONUP):
                            button = (ms.mouseData >> 16) & 0xFFFF  # 1 = XButton1, 2 = XButton2
                            if button == code:
                                (self._hotkey_down if w_param == WM_XBUTTONDOWN else self._hotkey_up)()
                                return 1
                        elif code == 3 and w_param in (WM_MBUTTONDOWN, WM_MBUTTONUP):
                            (self._hotkey_down if w_param == WM_MBUTTONDOWN else self._hotkey_up)()
                            return 1
        except Exception:
            log.exception("Mouse hook error")
        return user32.CallNextHookEx(None, n_code, w_param, l_param)
