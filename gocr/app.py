"""Entry point and main controller of GOCR."""
from __future__ import annotations

import concurrent.futures
import getpass
import logging
import sys
import time
import traceback
from logging.handlers import RotatingFileHandler

import cv2
import numpy as np
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from gocr import APP_NAME, APP_TITLE, VERSION, capture, i18n, pipeline, winapi
from gocr.config import AREA_MAX_H, AREA_MAX_W, AREA_MIN_H, AREA_MIN_W, Settings, app_data_dir, resource_path
from gocr.hooks import MOD_ALT, MOD_CTRL, MOD_SHIFT, HookSignals, InputHook
from gocr.i18n import tr
from gocr.ocr import OcrError, get_engine
from gocr.ui import theme as th
from gocr.ui.area import AreaWidget
from gocr.ui.overlay import ResultOverlay
from gocr.ui.settings_window import SettingsWindow
from gocr.ui.widgets import ThemeAware, hotkey_display_name

log = logging.getLogger("gocr")
LIVE_INTERVAL = 0.45        # minimum time between full OCR passes in live mode (seconds)
LIVE_FAST_INTERVAL = 0.12   # quick check: did the area move / did the screen change?
_APP_MUTEX = None


def setup_logging() -> None:
    handler = RotatingFileHandler(app_data_dir() / "gocr.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    if sys.stderr is not None:
        root.addHandler(logging.StreamHandler())

    def excepthook(etype, value, tb):
        log.error("Unhandled exception:\n%s", "".join(traceback.format_exception(etype, value, tb)))
    sys.excepthook = excepthook


def _init_worker() -> None:
    if winapi.IS_WIN:
        from gocr.ocr.windows_ocr import init_thread
        init_thread()


class Controller(QObject):
    result_ready = Signal(int, object)
    stage = Signal(int, str)
    languages_ready = Signal(object)
    test_done = Signal(bool, str)
    live_ready = Signal(int, object, object)

    def __init__(self, app: QApplication, settings: Settings, start_hidden: bool):
        super().__init__()
        self.app = app
        self.settings = settings
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="GOCR-ocr",
                                                              initializer=_init_worker)
        self.job = 0
        self.busy_rect: tuple[int, int, int, int] | None = None
        self.cur_w, self.cur_h = int(settings["area_w"]), int(settings["area_h"])
        self.cache = pipeline.TranslationCache()
        self.ocr_languages: list[tuple[str, str]] = []
        self.live = False
        self.live_inflight = False
        self.scene = None
        self.shown_blocks = []
        self.live_last = self.live_last_full = 0.0
        self.live_last_area = None
        self.snip_started = None
        self.press_time = 0.0
        self.press_was_live = False
        self.wheel_used = False

        i18n.set_language(settings["ui_lang"])
        self.icon = QIcon(str(resource_path("assets", "icon.png")))
        app.setWindowIcon(self.icon)

        # --- windows
        self.area = AreaWidget()
        self.overlay = ResultOverlay()
        self.overlay.closed.connect(self._overlay_closed)
        self.window: SettingsWindow | None = None
        self._create_window()
        app.commitDataRequest.connect(lambda *_: setattr(self.window, "allow_close", True))  # Windows shutdown

        # --- global hooks
        self.signals = HookSignals()
        self.signals.pressed.connect(self.on_pressed)
        self.signals.released.connect(self.on_released)
        self.signals.cancelled.connect(self.on_cancelled)
        self.signals.wheel.connect(self.on_wheel)
        self.signals.dismiss.connect(self.on_dismiss)
        self.signals.snip.connect(self.on_snip)
        self.hook = InputHook(self.signals)
        self.hook.hotkey = dict(settings["hotkey"])
        self.hook.enabled = bool(settings["hotkey_enabled"])
        self.hook.start()

        self.follow = QTimer(self)
        self.follow.setInterval(12)
        self.follow.timeout.connect(self._follow_mouse)
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(500)
        self.save_timer.timeout.connect(self.settings.save)

        self.live_timer = QTimer(self)
        self.live_timer.setInterval(60)
        self.live_timer.timeout.connect(self._live_tick)

        self.result_ready.connect(self.on_result)
        self.live_ready.connect(self.on_live_result)
        self.stage.connect(self._on_stage)
        self.languages_ready.connect(self._languages_loaded)
        self.test_done.connect(lambda ok, text: self.window.show_test_result(ok, text))

        self._build_tray()
        self.apply_theme()
        self.apply_overlay_settings()
        self.refresh_status()
        QTimer.singleShot(1500, self.refresh_status)  # check that the hooks were installed

        # Windows OCR languages and engine warm-up (on the OCR thread)
        if winapi.IS_WIN:
            self.executor.submit(self._load_languages)
        else:
            self.window.set_ocr_languages([])
        self.prewarm()

        if winapi.IS_WIN:  # the registry is the source of truth (the installer can enable it too)
            settings["start_with_windows"] = winapi.is_start_with_windows()
            self.window.load_values()

        if start_hidden:
            log.info("Started in the system tray")
        else:
            self.window.show_and_raise()

    # ------------------------------------------------------------------ settings window
    def _create_window(self):
        """(Re)creates the settings window, e.g. after the UI language changes."""
        old = self.window
        win = SettingsWindow(self.settings, QPixmap(str(resource_path("assets", "icon.png"))))
        win.setWindowIcon(self.icon)
        win.theme_toggled.connect(self.toggle_theme)
        win.hotkey_changed.connect(self.set_hotkey)
        win.hotkey_capture.connect(self._capturing)
        win.setting_changed.connect(self.on_setting)
        win.hide_requested.connect(self.hide_window)
        win.test_translation.connect(self.run_translation_test)
        self.window = win
        if old is not None:
            win.set_ocr_languages(self.ocr_languages)
            win.apply_theme(self.settings["theme"])
            win.setGeometry(old.geometry())
            visible = old.isVisible()
            old.allow_close = True
            old.close()
            old.deleteLater()
            if visible:
                win.show_and_raise()

    def _languages_loaded(self, langs):
        self.ocr_languages = langs
        self.window.set_ocr_languages(langs)

    # ------------------------------------------------------------------ tray
    def _build_tray(self):
        self.tray = QSystemTrayIcon(self.icon, self)
        self.menu = QMenu()
        self.act_open = QAction(self.menu)
        self.act_open.triggered.connect(lambda: self.window.show_and_raise())
        self.act_pause = QAction(self.menu)
        self.act_pause.setCheckable(True)
        self.act_pause.setChecked(not self.settings["hotkey_enabled"])
        self.act_pause.toggled.connect(lambda paused: self.on_setting("hotkey_enabled", not paused, from_tray=True))
        self.act_theme = QAction(self.menu)
        self.act_theme.triggered.connect(self.toggle_theme)
        self.act_quit = QAction(self.menu)
        self.act_quit.triggered.connect(self.quit)
        self.menu.addAction(self.act_open)
        self.menu.addAction(self.act_pause)
        self.menu.addAction(self.act_theme)
        self.menu.addSeparator()
        self.menu.addAction(self.act_quit)
        self._retranslate_tray()
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _retranslate_tray(self):
        self.act_open.setText(tr("tray.open"))
        self.act_pause.setText(tr("tray.pause"))
        self.act_theme.setText(tr("tray.theme"))
        self.act_quit.setText(tr("tray.quit"))

    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if self.window.isVisible() and not self.window.isMinimized():
                self.hide_window()
            else:
                self.window.show_and_raise()

    def hide_window(self):
        self.window.hide()
        if not self.settings["tray_hint_shown"] and QSystemTrayIcon.supportsMessages():
            self.tray.showMessage(tr("tray.hint_title"), tr("tray.hint_body", key=hotkey_display_name(self.settings["hotkey"])),
                                  self.icon, 5000)
            self.settings["tray_hint_shown"] = True
            self.save_timer.start()

    def quit(self):
        log.info("Quitting")
        self.settings.save()
        self.hook.stop()
        self.tray.hide()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.window.allow_close = True
        self.app.exit(0)

    # ------------------------------------------------------------------ status / theme
    def refresh_status(self):
        name = hotkey_display_name(self.settings["hotkey"])
        toggle = self.settings["live_activation"] == "toggle"
        if winapi.IS_WIN and self.hook.attempted and not self.hook.ok:
            text, kind = tr("status.hook_failed"), "error"
        elif not self.settings["hotkey_enabled"]:
            text, kind = tr("status.paused"), "warn"
        elif self.live:
            text, kind = tr("status.live_on_toggle" if toggle else "status.live_on_hold", key=name), "ok"
        elif self.settings["translate_mode"] == "live":
            text, kind = tr("status.live_toggle" if toggle else "status.live_hold", key=name), "ok"
        else:
            text, kind = tr("status.release", key=name), "ok"
        self.window.set_status(text, kind)
        self.tray.setToolTip(f"{APP_TITLE} — {text}")

    def apply_theme(self):
        name = self.settings["theme"]
        ThemeAware.theme_name = name
        self.window.apply_theme(name)
        self.menu.setStyleSheet(th.stylesheet(name))
        self.area.theme = name
        self.overlay.theme = name
        self.refresh_status()

    def toggle_theme(self):
        self.settings["theme"] = "light" if self.settings["theme"] == "dark" else "dark"
        self.apply_theme()
        self.save_timer.start()

    def apply_overlay_settings(self):
        s = self.settings
        self.overlay.style_mode = s["overlay_style"]
        self.overlay.opacity = float(s["overlay_opacity"])
        self.overlay.show_tooltip = bool(s["show_original_tooltip"])

    def set_ui_language(self, code: str):
        i18n.set_language(code)
        self._retranslate_tray()
        self._create_window()
        self.refresh_status()

    # ------------------------------------------------------------------ settings
    def set_hotkey(self, hk: dict):
        self.settings["hotkey"] = hk
        self.hook.hotkey = dict(hk)
        self.hook.reset()
        self.refresh_status()
        self.save_timer.start()

    def _capturing(self, on: bool):
        self.hook.capturing = on

    def on_setting(self, key: str, value, from_tray: bool = False):
        self.settings[key] = value
        if key == "area_w":
            self.cur_w = int(value)
        elif key == "area_h":
            self.cur_h = int(value)
        elif key == "hotkey_enabled":
            self.hook.enabled = bool(value)
            self.hook.reset()
            if from_tray:
                self.window.load_values()
            else:
                self.act_pause.blockSignals(True)
                self.act_pause.setChecked(not value)
                self.act_pause.blockSignals(False)
            self.refresh_status()
        elif key in ("ocr_engine", "ocr_lang"):
            self.window.update_engine_ui()
            self.prewarm()
        elif key in ("translate_mode", "live_activation"):
            if self.live and self.settings["translate_mode"] != "live":
                self.stop_live(keep=False)
            self.window.update_mode_ui()
            self.refresh_status()
        elif key == "start_with_windows":
            winapi.set_start_with_windows(bool(value))
        elif key.startswith("overlay_") or key == "show_original_tooltip":
            self.apply_overlay_settings()
        elif key == "ui_lang":
            QTimer.singleShot(0, lambda: self.set_ui_language(value))
        self.save_timer.start()

    def run_translation_test(self):
        target = self.settings["target_lang"]

        def work():
            from gocr.translate import TranslateError, test_translation
            try:
                self.test_done.emit(True, tr("tr.test_ok", text=test_translation(target)))
            except TranslateError as exc:
                self.test_done.emit(False, str(exc) + "\n" + tr("tr.test_log"))
            except Exception as exc:  # noqa: BLE001
                log.exception("Translation test failed")
                self.test_done.emit(False, repr(exc))
        self.executor.submit(work)

    def _load_languages(self):
        from gocr.ocr.windows_ocr import available_languages
        langs = available_languages()
        log.info("Windows OCR languages: %s", langs)
        self.languages_ready.emit(langs)

    def prewarm(self):
        engine, lang = self.settings["ocr_engine"], self.settings["ocr_lang"]

        def warm():
            try:
                from gocr.wordsplit import fix_spacing
                fix_spacing("warmupwords")  # loads the word list
                get_engine(engine, lang)
            except Exception as exc:
                log.warning("Could not preload the %s engine: %s", engine, exc)
        self.executor.submit(warm)

    # ------------------------------------------------------------------ capture area
    def _area_rect(self) -> tuple[int, int, int, int]:
        x, y = winapi.cursor_pos()
        return capture.clamp_rect(x - self.cur_w // 2, y - self.cur_h // 2, self.cur_w, self.cur_h)

    def _follow_mouse(self):
        rect = self._area_rect()
        if rect != self.area.phys or not self.area.isVisible():
            self.area.set_phys_rect(*rect)
            if self.live and self.overlay.isVisible():
                self.overlay.set_view(rect)

    def _opts(self) -> dict:
        return {k: self.settings[k] for k in ("ocr_engine", "ocr_lang", "target_lang", "source_lang")}

    def _reset_size_if_needed(self):
        if not self.settings["remember_size"]:
            self.cur_w, self.cur_h = int(self.settings["area_w"]), int(self.settings["area_h"])

    def on_pressed(self):
        self.press_time = time.monotonic()
        self.wheel_used = False
        self.press_was_live = self.live
        if self.settings["translate_mode"] == "live":
            if not self.live:
                self.start_live()
            return
        self.overlay.dismiss()
        self.job += 1  # discard pending results
        self._reset_size_if_needed()
        self.area.theme = self.settings["theme"]
        self.area.set_phys_rect(*self._area_rect())
        self.area.show_aiming()
        self.follow.start()

    def on_wheel(self, delta: int, mods: int):
        self.wheel_used = True
        steps = delta / 120.0
        w, h = float(self.cur_w), float(self.cur_h)
        if mods & MOD_CTRL and not mods & MOD_ALT:
            h += 15 * steps                       # Ctrl + wheel: height
        elif mods & MOD_ALT and not mods & MOD_CTRL:
            w += 30 * steps                       # Alt + wheel: width
        elif mods & MOD_SHIFT:
            f = 1.03 ** steps                     # Shift + wheel: fine adjustment of both
            w, h = w * f, h * f
        else:
            f = 1.12 ** steps                     # wheel alone: both, keeping the ratio
            w, h = w * f, h * f
        self.cur_w = int(min(max(round(w), AREA_MIN_W), AREA_MAX_W))
        self.cur_h = int(min(max(round(h), AREA_MIN_H), AREA_MAX_H))
        rect = self._area_rect()
        self.area.set_phys_rect(*rect)
        if self.live:
            self.overlay.set_view(rect)
            self.scene = None   # new area: read again instead of reusing the previous pass
        if self.settings["remember_size"]:
            self.settings["area_w"], self.settings["area_h"] = self.cur_w, self.cur_h
            self.window.set_area_size(self.cur_w, self.cur_h)
            self.save_timer.start()

    def on_cancelled(self):
        """Esc while the hotkey is held."""
        if self.live:
            self.stop_live(keep=False)
            return
        self.follow.stop()
        self.area.hide_area()

    def on_dismiss(self):
        """Esc while a translation is on screen or live mode is on."""
        if self.live:
            self.stop_live(keep=False)
        else:
            self.overlay.dismiss()

    def on_released(self):
        if self.live:
            if self.settings["live_activation"] == "toggle":
                quick = (time.monotonic() - self.press_time) < 0.35 and not self.wheel_used
                if self.press_was_live and quick:   # short tap while live mode is on → turn it off
                    self.stop_live(keep=False)       # turning it off restores everything
            else:
                self.stop_live(keep=False)
            return
        if self.settings["translate_mode"] == "live":
            return
        # --- "on release" mode: hide the frame before capturing so the OCR never reads it
        self.follow.stop()
        rect = self._area_rect()
        self.job += 1
        jid = self.job
        self.area.hide_area()
        QTimer.singleShot(60, lambda: self._capture_single(jid, rect))

    def _capture_single(self, jid: int, area: tuple[int, int, int, int]):
        if jid != self.job:
            return
        cap = pipeline.expanded_rect(area)
        try:
            img = capture.grab(*cap)
        except Exception:
            log.exception("Screen capture failed")
            self.overlay.show_message(area, tr("msg.capture_failed"), "error")
            self.hook.overlay_visible = True
            return
        self.busy_rect = area
        self.area.set_phys_rect(*area)
        self.area.show_aiming()
        self.area.show_busy(tr("area.reading"))
        fut = self.executor.submit(pipeline.process, img, cap, area, self._opts(), self.cache,
                                   lambda text, j=jid: self.stage.emit(j, text))
        fut.add_done_callback(lambda f, j=jid: self.result_ready.emit(j, f))

    def _on_stage(self, jid: int, text: str):
        if jid == self.job and self.area.isVisible():
            self.area.show_busy(text)

    def on_result(self, jid: int, fut):
        if jid != self.job:
            return
        rect = self.busy_rect or self.area.phys
        self.area.hide_area()
        try:
            blocks, warning = fut.result()
        except concurrent.futures.CancelledError:
            return
        except OcrError as exc:
            self.overlay.show_message(rect, str(exc), "error", 8)
            self.hook.overlay_visible = True
            return
        except Exception as exc:
            log.exception("OCR error")
            self.overlay.show_message(rect, tr("msg.ocr_error", error=exc), "error", 6)
            self.hook.overlay_visible = True
            return
        log.info("Result: %d blocks", len(blocks))
        if not blocks:
            self.overlay.show_message(rect, tr("msg.no_text"), "warn", 2)
        elif warning:
            self.overlay.show_message(rect, str(warning), "error", 5)
        else:
            self.overlay.set_excluded(False)  # so it shows up in Win+Shift+S
            self.overlay.show_blocks(blocks, rect, int(self.settings["overlay_auto_hide"]), interactive=True)
        self.hook.overlay_visible = True

    def _overlay_closed(self):
        self.hook.overlay_visible = self.live

    # ------------------------------------------------------------------ live mode
    def start_live(self):
        self.overlay.dismiss()
        self.job += 1
        self._reset_size_if_needed()
        self.live = True
        self.live_inflight = False
        self.scene = None
        self.shown_blocks = []
        self.live_last = self.live_last_full = 0.0
        self.live_last_area = None
        self.snip_started = None
        self.hook.overlay_visible = True
        self.hook.free_wheel = self.settings["live_activation"] == "toggle"
        self.hook.snip_intercept = True
        self.area.theme = self.settings["theme"]
        self.area.set_phys_rect(*self._area_rect())
        self.area.show_aiming(tr("area.live"))
        self.overlay.set_excluded(True)
        if not self._capture_safe():
            log.warning("Capture exclusion unavailable: the frame will flicker on every pass")
        self.follow.start()
        self.live_timer.start()
        self.refresh_status()

    def _capture_safe(self) -> bool:
        return self.area.ensure_native() and self.overlay.excluded

    def stop_live(self, keep: bool):
        if not self.live:
            return
        self.live = False
        self.snip_started = None
        self.hook.free_wheel = False
        self.hook.snip_intercept = False
        self.live_timer.stop()
        self.follow.stop()
        self.job += 1
        self.area.hide_area()
        if keep and self.overlay.items and self.overlay.isVisible():
            self.overlay.set_view(None)
            self.overlay.set_interactive(True)
            self.overlay.set_excluded(False)   # visible to Win+Shift+S
            self.overlay.start_auto_hide(int(self.settings["overlay_auto_hide"]))
            self.hook.overlay_visible = True
        else:
            self.overlay.dismiss()
        self.refresh_status()

    # --- Windows snipping (Win+Shift+S / Print Screen) while live mode is on
    def on_snip(self, kind: str):
        if not self.live:
            winapi.send_snip_keys(kind)
            return
        log.info("Screen snip: live mode paused")
        self.snip_started = time.monotonic()
        self.area.hide()                       # the frame must not appear in the snip
        self.overlay.set_excluded(False)       # the translation should
        QTimer.singleShot(120, lambda: winapi.send_snip_keys(kind))

    def _check_snip_done(self) -> bool:
        """True while the snipping tool is still open."""
        elapsed = time.monotonic() - self.snip_started
        if elapsed < 1.0 or (winapi.foreground_process_name() in winapi.SNIP_PROCESSES and elapsed < 90):
            return True
        log.info("Snip finished: live mode resumed")
        self.snip_started = None
        self.overlay.set_excluded(True)
        self.scene = None
        self.area.show()
        return False

    # --- loop
    @staticmethod
    def _gray(img):
        return cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)

    @staticmethod
    def _thumb(gray):
        return cv2.resize(gray, (64, 24), interpolation=cv2.INTER_AREA).astype(np.int16)

    def _scene_changed(self, gray) -> bool:
        """Did the screen content inside the last capture change?
        Checks the whole image (high threshold, for animated backgrounds) and every text line."""
        sc = self.scene
        if float(np.abs(self._thumb(gray) - sc["thumb"]).mean()) > 7.0:
            return True
        for (x, y, w, h), ref in sc["line_crops"]:
            crop = gray[y:y + h, x:x + w].astype(np.int16)
            if crop.shape == ref.shape and float(np.abs(crop - ref).mean()) > 14.0:
                return True
        return False

    def _make_scene(self, img, cap, lines):
        gray = self._gray(img)
        crops = []
        for ln in lines:
            x, y = ln.x - cap[0], ln.y - cap[1]
            x0, y0 = max(0, x), max(0, y)
            x1, y1 = min(gray.shape[1], x + ln.w), min(gray.shape[0], y + ln.h)
            if x1 - x0 > 2 and y1 - y0 > 2:
                crops.append(((x0, y0, x1 - x0, y1 - y0), gray[y0:y1, x0:x1].astype(np.int16)))
        return {"cap": cap, "img": img, "lines": lines, "thumb": self._thumb(gray), "line_crops": crops}

    @staticmethod
    def _inside(area, cap, inset: int = 4) -> bool:
        inset = max(inset, int(area[3] * 0.25), 20)   # margin: a line cut by the capture edge was misread
        ax, ay, aw, ah = area
        cx, cy, cw, ch = cap
        return ax >= cx + inset and ay >= cy + inset and ax + aw <= cx + cw - inset and ay + ah <= cy + ch - inset

    def _live_tick(self):
        if not self.live or self.live_inflight:
            return
        if self.snip_started is not None and self._check_snip_done():
            return
        now = time.monotonic()
        if now - self.live_last < LIVE_FAST_INTERVAL:
            return
        self.live_last = now
        area = self._area_rect()
        safe = self._capture_safe()
        sc = self.scene
        if safe and sc is not None and self._inside(area, sc["cap"]):
            try:
                gray = self._gray(capture.grab(*sc["cap"]))
            except Exception:
                log.exception("Screen capture failed (live)")
                return
            if not self._scene_changed(gray):
                if area == self.live_last_area:
                    return                     # nothing changed: nothing to do
                self._submit_live("reuse", area, sc["img"], sc["cap"], sc["lines"])
                return
        if now - self.live_last_full < LIVE_INTERVAL:
            return
        self.live_last_full = now
        if safe:
            self._live_full_capture(area, restore=False)
        else:  # old Windows: hide our windows for an instant so we never read ourselves
            self.live_inflight = True
            self.area.hide()
            self.overlay.hide()
            QTimer.singleShot(45, lambda: self._live_full_capture(area, restore=True))

    def _live_full_capture(self, area, restore: bool):
        self.live_inflight = False
        if not self.live:
            return
        cap = pipeline.expanded_rect(area)
        try:
            img = capture.grab(*cap)
        except Exception:
            log.exception("Screen capture failed (live)")
            img = None
        if restore:
            self.area.show()
            if self.overlay.items:
                self.overlay.show()
        if img is not None:
            self._submit_live("full", area, img, cap, None)

    def _submit_live(self, kind, area, img, cap, lines):
        jid = self.job
        self.live_inflight = True
        prev = list(self.shown_blocks)
        if kind == "full":
            fut = self.executor.submit(pipeline.live_full, img, cap, area, self._opts(), self.cache, prev)
        else:
            fut = self.executor.submit(pipeline.live_reuse, lines, img, cap, area, self._opts(), self.cache, prev)
        fut.add_done_callback(lambda f, j=jid, a=area, k=kind, i=img, c=cap: self.live_ready.emit(j, f, (a, k, i, c)))

    def on_live_result(self, jid: int, fut, meta):
        area, kind, img, cap = meta
        self.live_inflight = False
        if jid != self.job or not self.live:
            return
        try:
            blocks, warning, lines = fut.result()
        except concurrent.futures.CancelledError:
            return
        except OcrError as exc:
            log.warning("Live OCR: %s", exc)
            self.area.set_label(tr("area.ocr_error"))
            return
        except Exception:
            log.exception("OCR error (live)")
            return
        if kind == "full":
            self.scene = self._make_scene(img, cap, lines)
        self.live_last_area = area
        blocks = [b for b in blocks if b.translation]
        sig = [(b.translation, b.x // 6, b.y // 6, b.w // 6, b.h // 6) for b in blocks]
        old = [(b.translation, b.x // 6, b.y // 6, b.w // 6, b.h // 6) for b in self.shown_blocks]
        if blocks and sig != old:
            self.overlay.show_blocks(blocks, area, 0, interactive=False)
        elif not blocks and self.overlay.isVisible():
            self.overlay.hide()
            self.overlay.items = []
        if blocks or not self.shown_blocks or sig != old:
            self.shown_blocks = blocks
        self.overlay.set_view(self._area_rect())
        if warning is None:
            self.area.set_label(tr("area.live"))
        elif getattr(warning, "kind", "") == "rate":
            self.area.set_label(tr("area.live_rate"))
        elif getattr(warning, "kind", "") == "offline":
            self.area.set_label(tr("area.live_offline"))
        else:
            self.area.set_label(tr("area.live_error"))


# --------------------------------------------------------------------------- single instance
def _single_instance() -> QLocalServer | None:
    name = f"{APP_NAME}-{getpass.getuser()}"
    sock = QLocalSocket()
    sock.connectToServer(name)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        return None
    QLocalServer.removeServer(name)
    server = QLocalServer()
    server.listen(name)
    return server


def main() -> int:
    setup_logging()
    log.info("GOCR %s starting (Python %s)", VERSION, sys.version.split()[0])
    if winapi.IS_WIN:
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Sairock.GOCR")
            # the installer uses this mutex to detect a running GOCR
            global _APP_MUTEX
            _APP_MUTEX = ctypes.windll.kernel32.CreateMutexW(None, False, "GOCR_AppMutex")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_TITLE)
    app.setQuitOnLastWindowClosed(False)

    server = _single_instance()
    if server is None:
        log.info("GOCR was already running; showing the existing window")
        return 0

    settings = Settings()
    start_hidden = ("--minimized" in sys.argv) or (bool(settings["start_minimized"]) and not settings.is_first_run)
    if settings.is_first_run:
        settings.save()
    if not QSystemTrayIcon.isSystemTrayAvailable():
        start_hidden = False

    ctrl = Controller(app, settings, start_hidden)

    def on_connection():
        conn = server.nextPendingConnection()
        if conn:
            conn.readyRead.connect(lambda: (conn.readAll(), ctrl.window.show_and_raise()))
    server.newConnection.connect(on_connection)

    code = app.exec()
    ctrl.hook.stop()
    return code
