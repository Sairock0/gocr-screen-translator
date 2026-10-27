"""Settings window: simple, with its own title bar and a light/dark mode button."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import (QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QSlider, QSpinBox, QVBoxLayout, QWidget)

from gocr import APP_TITLE, VERSION
from gocr.config import AREA_MAX_H, AREA_MAX_W, AREA_MIN_H, AREA_MIN_W, Settings
from gocr.i18n import lang_name, tr
from gocr.ocr import ENGINES
from gocr.translate import SOURCE_LANGS, TARGET_LANGS
from gocr.ui import theme as th
from gocr.ui.widgets import (AreaPreview, Card, HotkeyButton, IconButton, Segmented, ThemeAware, ThemeButton,
                             ToggleSwitch, row)

AUTO_HIDE_SECONDS = [0, 3, 5, 8, 15, 30]
INSTALL_EN_CMD = 'Add-WindowsCapability -Online -Name "Language.OCR~~~en-US~0.0.1.0"'


class _WheelGuard(QObject):
    """Keeps the mouse wheel from changing combo boxes, sliders or spin boxes while scrolling
    the window over them (that is how the target language once changed by itself). The wheel
    scrolls the window; to change a value, click the control first."""

    def __init__(self, scroll):
        super().__init__(scroll)
        self.scroll = scroll

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel and not obj.hasFocus():
            bar = self.scroll.verticalScrollBar()
            bar.setValue(bar.value() - int(event.angleDelta().y() / 120 * 48))
            return True
        return False


class TitleBar(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.setObjectName("TitleBar")
        self._win = window

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            handle = self._win.windowHandle()
            if handle is not None:
                handle.startSystemMove()


class SettingsWindow(QWidget):
    """Emits signals when something changes; the controller applies and saves the changes."""
    theme_toggled = Signal()
    hotkey_changed = Signal(dict)
    hotkey_capture = Signal(bool)
    setting_changed = Signal(str, object)
    hide_requested = Signal()
    test_translation = Signal()

    def __init__(self, settings: Settings, icon_pixmap: QPixmap | None = None):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Window)
        self.settings = settings
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle(f"{APP_TITLE} — {tr('app.subtitle')}")
        self.allow_close = False
        avail = QGuiApplication.primaryScreen().availableGeometry() if QGuiApplication.primaryScreen() else None
        self.resize(560, min(760, avail.height() - 60) if avail else 760)
        self.setMinimumSize(500, 420)
        self._loading = True
        self._build(icon_pixmap)
        self.load_values()
        self._loading = False

    # ------------------------------------------------------------------ layout
    def _build(self, icon_pixmap):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.root = QFrame()
        self.root.setObjectName("Root")
        outer.addWidget(self.root)
        lay = QVBoxLayout(self.root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # --- title bar
        bar = TitleBar(self)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(16, 12, 10, 8)
        bl.setSpacing(10)
        if icon_pixmap is not None:
            ic = QLabel()
            ic.setPixmap(icon_pixmap.scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            bl.addWidget(ic)
        names = QVBoxLayout()
        names.setSpacing(0)
        n1 = QLabel(APP_TITLE)
        n1.setObjectName("AppName")
        n2 = QLabel(tr("app.subtitle"))
        n2.setObjectName("AppSub")
        names.addWidget(n1)
        names.addWidget(n2)
        bl.addLayout(names)
        bl.addStretch(1)
        self.theme_btn = ThemeButton()
        self.theme_btn.clicked.connect(self.theme_toggled.emit)
        bl.addWidget(self.theme_btn)
        self.min_btn = IconButton("min")
        self.min_btn.setToolTip(tr("win.minimize"))
        self.min_btn.clicked.connect(self.hide_requested.emit)
        self.close_btn = IconButton("close", "CloseBtn")
        self.close_btn.setToolTip(tr("win.close"))
        self.close_btn.clicked.connect(self.hide_requested.emit)
        bl.addWidget(self.min_btn)
        bl.addWidget(self.close_btn)
        lay.addWidget(bar)

        # --- status line
        self.status = QLabel()
        self.status.setObjectName("Status")
        self.status.setContentsMargins(18, 0, 18, 8)
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        # --- scrollable body
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        body.setObjectName("ScrollBody")
        bodyl = QVBoxLayout(body)
        bodyl.setContentsMargins(14, 4, 14, 14)
        bodyl.setSpacing(12)
        scroll.setWidget(body)
        lay.addWidget(scroll, 1)

        bodyl.addWidget(self._card_mode())
        bodyl.addWidget(self._card_hotkey())
        bodyl.addWidget(self._card_area())
        bodyl.addWidget(self._card_ocr())
        bodyl.addWidget(self._card_translate())
        bodyl.addWidget(self._card_overlay())
        bodyl.addWidget(self._card_general())
        foot = QLabel(tr("win.footer", app=APP_TITLE, version=VERSION))
        foot.setObjectName("Muted")
        foot.setAlignment(Qt.AlignCenter)
        bodyl.addWidget(foot)
        bodyl.addStretch(1)

        guard = _WheelGuard(scroll)
        for w in body.findChildren(QWidget):
            if isinstance(w, (QComboBox, QSpinBox, QSlider)):
                w.setFocusPolicy(Qt.StrongFocus)
                w.installEventFilter(guard)

    def _card_mode(self):
        card = Card(tr("mode.title"))
        self.mode_seg = Segmented([("release", tr("mode.release")), ("live", tr("mode.live"))])
        self.mode_seg.changed.connect(lambda k: self._emit("translate_mode", k))
        card.body.addWidget(row(tr("mode.when"), self.mode_seg))
        self.activation_seg = Segmented([("hold", tr("mode.hold")), ("toggle", tr("mode.toggle"))])
        self.activation_seg.changed.connect(lambda k: self._emit("live_activation", k))
        self.activation_row = row(tr("mode.activation"), self.activation_seg)
        card.body.addWidget(self.activation_row)
        self.mode_info = QLabel()
        self.mode_info.setObjectName("Muted")
        self.mode_info.setWordWrap(True)
        card.body.addWidget(self.mode_info)
        return card

    def update_mode_ui(self):
        mode, act = self.settings["translate_mode"], self.settings["live_activation"]
        self.mode_seg.set_value(mode)
        self.activation_seg.set_value(act)
        self.activation_row.setVisible(mode == "live")
        if mode == "release":
            text = tr("mode.info_release")
        elif act == "hold":
            text = tr("mode.info_hold")
        else:
            text = tr("mode.info_toggle")
        self.mode_info.setText(text)

    def _card_hotkey(self):
        card = Card(tr("hotkey.title"), tr("hotkey.subtitle"))
        self.hotkey_btn = HotkeyButton(self.settings["hotkey"])
        self.hotkey_btn.hotkey_changed.connect(self.hotkey_changed.emit)
        self.hotkey_btn.capture_state.connect(self.hotkey_capture.emit)
        card.body.addWidget(row(tr("hotkey.label"), self.hotkey_btn, tr("hotkey.hint")))
        self.hotkey_enabled = ToggleSwitch()
        self.hotkey_enabled.toggled.connect(lambda v: self._emit("hotkey_enabled", v))
        card.body.addWidget(row(tr("hotkey.enabled"), self.hotkey_enabled))

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        tips = [("tip.wheel", "tip.wheel_desc"), ("tip.alt_wheel", "tip.alt_wheel_desc"),
                ("tip.ctrl_wheel", "tip.ctrl_wheel_desc"), ("tip.shift_wheel", "tip.shift_wheel_desc"),
                ("tip.esc", "tip.esc_desc"), ("tip.right_click", "tip.right_click_desc")]
        for i, (k, v) in enumerate(tips):
            chip = QFrame()
            chip.setObjectName("Chip")
            cl = QHBoxLayout(chip)
            cl.setContentsMargins(8, 4, 8, 4)
            cl.setSpacing(6)
            kl = QLabel(tr(k))
            kl.setObjectName("Kbd")
            vl = QLabel(tr(v))
            vl.setObjectName("Muted")
            cl.addWidget(kl)
            cl.addWidget(vl)
            cl.addStretch(1)
            grid.addWidget(chip, i // 2, i % 2)
        card.body.addLayout(grid)
        return card

    def _size_control(self, lo, hi, key):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        slider = QSlider(Qt.Horizontal)
        slider.setRange(lo, hi)
        slider.setMinimumWidth(180)
        spin = QSpinBox()
        spin.setRange(lo, hi)
        spin.setSuffix(" px")
        spin.setFixedWidth(84)
        spin.setAlignment(Qt.AlignCenter)
        slider.valueChanged.connect(spin.setValue)
        spin.valueChanged.connect(slider.setValue)
        spin.valueChanged.connect(lambda v: self._emit(key, int(v)))
        lay.addWidget(slider)
        lay.addWidget(spin)
        return w, spin

    def _card_area(self):
        card = Card(tr("area.title"), tr("area.subtitle"))
        self.preview = AreaPreview()
        card.body.addWidget(self.preview)
        wctl, self.w_spin = self._size_control(AREA_MIN_W, AREA_MAX_W, "area_w")
        hctl, self.h_spin = self._size_control(AREA_MIN_H, AREA_MAX_H, "area_h")
        card.body.addWidget(row(tr("area.width"), wctl))
        card.body.addWidget(row(tr("area.height"), hctl))
        self.remember = ToggleSwitch()
        self.remember.toggled.connect(lambda v: self._emit("remember_size", v))
        card.body.addWidget(row(tr("area.remember"), self.remember, tr("area.remember_hint")))
        return card

    def _card_ocr(self):
        card = Card(tr("ocr.title"))
        self.engine_seg = Segmented([(k, v) for k, v in ENGINES.items()])
        self.engine_seg.changed.connect(lambda k: self._emit("ocr_engine", k))
        card.body.addWidget(row(tr("ocr.engine"), self.engine_seg, tr("ocr.engine_hint")))
        self.lang_combo = QComboBox()
        self.lang_combo.setMinimumWidth(200)
        self.lang_combo.currentIndexChanged.connect(self._lang_changed)
        self.lang_row = row(tr("ocr.lang"), self.lang_combo, tr("ocr.lang_hint"))
        card.body.addWidget(self.lang_row)
        self.script_combo = QComboBox()
        self.script_combo.setMinimumWidth(200)
        for key in ("auto", "latin", "chinese"):
            self.script_combo.addItem(tr(f"ocr.script_{key}"), key)
        self.script_combo.currentIndexChanged.connect(
            lambda _i: self._emit("rapid_script", self.script_combo.currentData()))
        self.script_row = row(tr("ocr.script"), self.script_combo, tr("ocr.script_hint"))
        card.body.addWidget(self.script_row)
        self.ocr_info = QLabel()
        self.ocr_info.setObjectName("Muted")
        self.ocr_info.setWordWrap(True)
        self.ocr_info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        card.body.addWidget(self.ocr_info)
        return card

    def _card_translate(self):
        card = Card(tr("tr.title"), tr("tr.subtitle"))
        self.target_combo = QComboBox()
        self.target_combo.setMinimumWidth(200)
        for code in TARGET_LANGS:
            self.target_combo.addItem(lang_name(code), code)
        self.target_combo.currentIndexChanged.connect(
            lambda _i: self._emit("target_lang", self.target_combo.currentData()))
        card.body.addWidget(row(tr("tr.target"), self.target_combo))
        self.source_combo = QComboBox()
        self.source_combo.setMinimumWidth(200)
        for code in SOURCE_LANGS:
            self.source_combo.addItem(lang_name(code), code)
        self.source_combo.currentIndexChanged.connect(
            lambda _i: self._emit("source_lang", self.source_combo.currentData()))
        card.body.addWidget(row(tr("tr.source"), self.source_combo))
        test_btn = QPushButton(tr("tr.test"))
        test_btn.clicked.connect(lambda: (self.test_result.setText(tr("tr.testing")), self.test_translation.emit()))
        self.test_result = QLabel()
        self.test_result.setObjectName("Muted")
        self.test_result.setWordWrap(True)
        self.test_result.setTextInteractionFlags(Qt.TextSelectableByMouse)
        card.body.addWidget(row(tr("tr.test_label"), test_btn))
        card.body.addWidget(self.test_result)
        return card

    def show_test_result(self, ok: bool, text: str):
        mark = "✓" if ok else "⚠"
        self.test_result.setText(f"{mark} {text}")

    def _card_overlay(self):
        card = Card(tr("ov.title"), tr("ov.subtitle"))
        self.style_combo = QComboBox()
        self.style_combo.addItem(tr("ov.style_auto"), "auto")
        self.style_combo.addItem(tr("ov.style_theme"), "theme")
        self.style_combo.currentIndexChanged.connect(lambda _i: self._emit("overlay_style", self.style_combo.currentData()))
        card.body.addWidget(row(tr("ov.style"), self.style_combo, tr("ov.style_hint")))
        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(50, 100)
        self.opacity.setMinimumWidth(180)
        self.opacity_lbl = QLabel()
        self.opacity_lbl.setFixedWidth(40)
        self.opacity.valueChanged.connect(lambda v: (self.opacity_lbl.setText(f"{v}%"),
                                                     self._emit("overlay_opacity", v / 100)))
        ow = QWidget()
        ol = QHBoxLayout(ow)
        ol.setContentsMargins(0, 0, 0, 0)
        ol.addWidget(self.opacity)
        ol.addWidget(self.opacity_lbl)
        card.body.addWidget(row(tr("ov.opacity"), ow))
        self.autohide = QComboBox()
        for secs in AUTO_HIDE_SECONDS:
            self.autohide.addItem(tr("ov.never") if secs == 0 else tr("ov.seconds", n=secs), secs)
        self.autohide.currentIndexChanged.connect(lambda _i: self._emit("overlay_auto_hide", self.autohide.currentData()))
        card.body.addWidget(row(tr("ov.autohide"), self.autohide))
        self.tooltip_sw = ToggleSwitch()
        self.tooltip_sw.toggled.connect(lambda v: self._emit("show_original_tooltip", v))
        card.body.addWidget(row(tr("ov.tooltip"), self.tooltip_sw))
        return card

    def _card_general(self):
        card = Card(tr("gen.title"))
        self.ui_lang_combo = QComboBox()
        self.ui_lang_combo.setMinimumWidth(200)
        self.ui_lang_combo.addItem(tr("gen.lang_auto"), "auto")
        self.ui_lang_combo.addItem("English", "en")
        self.ui_lang_combo.addItem("Español", "es")
        self.ui_lang_combo.currentIndexChanged.connect(lambda _i: self._emit("ui_lang", self.ui_lang_combo.currentData()))
        card.body.addWidget(row(tr("gen.lang"), self.ui_lang_combo))
        self.startup_sw = ToggleSwitch()
        self.startup_sw.toggled.connect(lambda v: self._emit("start_with_windows", v))
        card.body.addWidget(row(tr("gen.startup"), self.startup_sw))
        self.minimized_sw = ToggleSwitch()
        self.minimized_sw.toggled.connect(lambda v: self._emit("start_minimized", v))
        card.body.addWidget(row(tr("gen.minimized"), self.minimized_sw, tr("gen.minimized_hint")))
        return card

    # ------------------------------------------------------------------ values
    def _emit(self, key, value):
        if key in ("area_w", "area_h"):
            self.preview.set_size(self.w_spin.value(), self.h_spin.value())
        if not self._loading:
            self.setting_changed.emit(key, value)

    def _lang_changed(self, _i):
        tag = self.lang_combo.currentData()
        if tag:
            self._emit("ocr_lang", tag)

    @staticmethod
    def _select(combo: QComboBox, value):
        i = combo.findData(value)
        if i >= 0:
            combo.setCurrentIndex(i)

    def load_values(self):
        s = self.settings
        was = self._loading
        self._loading = True
        self.hotkey_btn.set_hotkey(s["hotkey"])
        self.hotkey_enabled.setChecked(bool(s["hotkey_enabled"]))
        self.w_spin.setValue(int(s["area_w"]))
        self.h_spin.setValue(int(s["area_h"]))
        self.preview.set_size(int(s["area_w"]), int(s["area_h"]))
        self.remember.setChecked(bool(s["remember_size"]))
        self.engine_seg.set_value(s["ocr_engine"])
        self._select(self.script_combo, s["rapid_script"])
        self._select(self.target_combo, s["target_lang"])
        self._select(self.source_combo, s["source_lang"])
        self._select(self.style_combo, s["overlay_style"])
        self.opacity.setValue(int(round(float(s["overlay_opacity"]) * 100)))
        self.opacity_lbl.setText(f"{self.opacity.value()}%")
        self._select(self.autohide, int(s["overlay_auto_hide"]))
        self.tooltip_sw.setChecked(bool(s["show_original_tooltip"]))
        self._select(self.ui_lang_combo, s["ui_lang"])
        self.startup_sw.setChecked(bool(s["start_with_windows"]))
        self.minimized_sw.setChecked(bool(s["start_minimized"]))
        self.update_engine_ui()
        self.update_mode_ui()
        self._loading = was

    def set_area_size(self, w: int, h: int):
        was = self._loading
        self._loading = True
        self.w_spin.setValue(w)
        self.h_spin.setValue(h)
        self.preview.set_size(w, h)
        self._loading = was

    def set_ocr_languages(self, langs: list[tuple[str, str]]):
        was = self._loading
        self._loading = True
        self.lang_combo.clear()
        for tag, name in langs:
            self.lang_combo.addItem(f"{name} ({tag})", tag)
        current = self.settings["ocr_lang"]
        i = self.lang_combo.findData(current)
        if i < 0:  # match by base language (en-US ~ en-GB)
            base = current.split("-")[0].lower()
            for j in range(self.lang_combo.count()):
                if str(self.lang_combo.itemData(j)).lower().startswith(base):
                    i = j
                    break
        if i >= 0:
            self.lang_combo.setCurrentIndex(i)
        self._loading = was
        self.update_engine_ui()

    def update_engine_ui(self):
        engine = self.settings["ocr_engine"]
        self.engine_seg.set_value(engine)
        self.lang_row.setVisible(engine == "windows")
        self.script_row.setVisible(engine == "rapid")
        if engine == "rapid":
            self.ocr_info.setText(tr("ocr.info_rapid"))
        elif self.lang_combo.count() == 0:
            self.ocr_info.setText(tr("ocr.info_none", cmd=INSTALL_EN_CMD))
        else:
            cur = self.settings["ocr_lang"].split("-")[0].lower()
            has = any(str(self.lang_combo.itemData(j)).lower().startswith(cur) for j in range(self.lang_combo.count()))
            extra = "" if has else "\n" + tr("ocr.info_missing", cmd=INSTALL_EN_CMD)
            self.ocr_info.setText(tr("ocr.info_windows") + extra)

    def set_status(self, text: str, kind: str = "ok"):
        col = th.PALETTES[self.theme_btn.theme_name]["ok" if kind == "ok" else ("warn" if kind == "warn" else "danger")]
        self.status.setText(f"<span style='color:{col}; font-size:14px'>●</span>&nbsp; {text}")

    def apply_theme(self, name: str):
        ThemeAware.theme_name = name
        self.theme_btn.set_theme(name)
        self.setStyleSheet(th.stylesheet(name))
        for w in self.findChildren(QWidget):
            if isinstance(w, ThemeAware):
                w.update()
        self.update()

    # ------------------------------------------------------------------ window
    def closeEvent(self, e):
        if self.allow_close:
            e.accept()
            return
        e.ignore()
        self.hide_requested.emit()

    def show_and_raise(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
