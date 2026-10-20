"""Reusable UI controls."""
from __future__ import annotations

import math
import sys

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal, Property, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractButton, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget, QButtonGroup)

from gocr.hooks import FORBIDDEN_HOTKEY_VKS
from gocr.i18n import tr
from gocr.ui import theme as th


class ThemeAware:
    theme_name = "dark"

    def c(self, key: str) -> QColor:
        return th.color(self.theme_name, key)


# --------------------------------------------------------------------------- interruptor
class ToggleSwitch(QAbstractButton, ThemeAware):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self._pos = 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animate)

    def sizeHint(self):
        return QSize(42, 24)

    def _animate(self, on: bool):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def setChecked(self, on: bool):  # no animation when loading values
        super().setChecked(on)
        self._anim.stop()
        self._pos = 1.0 if on else 0.0
        self.update()

    def _get_knob(self):
        return self._pos

    def _set_knob(self, v):
        self._pos = v
        self.update()

    knob = Property(float, _get_knob, _set_knob)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(1, 2, 40, 20)
        off, on = self.c("border"), self.c("accent")
        track = QColor(
            int(off.red() + (on.red() - off.red()) * self._pos),
            int(off.green() + (on.green() - off.green()) * self._pos),
            int(off.blue() + (on.blue() - off.blue()) * self._pos))
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(r, 10, 10)
        x = r.left() + 3 + (r.width() - 20) * self._pos
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(x, r.top() + 3, 14, 14))


# --------------------------------------------------------------------------- buttons with painted icons
class IconButton(QPushButton, ThemeAware):
    """Title bar button with vector icons (does not depend on icon fonts)."""

    def __init__(self, icon: str, object_name: str = "TitleBtn", parent=None):
        super().__init__(parent)
        self.icon_name = icon
        self.setObjectName(object_name)
        self.setCursor(Qt.PointingHandCursor)
        self._hover = False

    def enterEvent(self, e):
        self._hover = True
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        super().leaveEvent(e)

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        col = QColor("#ffffff") if (self.icon_name == "close" and self._hover) else self.c("text")
        pen = QPen(col, 1.4)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        cx, cy = self.width() / 2, self.height() / 2
        if self.icon_name == "min":
            p.drawLine(QPointF(cx - 5, cy), QPointF(cx + 5, cy))
        elif self.icon_name == "close":
            p.drawLine(QPointF(cx - 5, cy - 5), QPointF(cx + 5, cy + 5))
            p.drawLine(QPointF(cx + 5, cy - 5), QPointF(cx - 5, cy + 5))


def draw_sun(p: QPainter, cx: float, cy: float, col: QColor):
    pen = QPen(col, 1.6)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QPointF(cx, cy), 3.6, 3.6)
    for i in range(8):
        a = i * math.pi / 4
        p.drawLine(QPointF(cx + math.cos(a) * 5.8, cy + math.sin(a) * 5.8),
                   QPointF(cx + math.cos(a) * 7.6, cy + math.sin(a) * 7.6))


def draw_moon(p: QPainter, cx: float, cy: float, col: QColor):
    path = QPainterPath()
    path.addEllipse(QPointF(cx, cy), 7, 7)
    cut = QPainterPath()
    cut.addEllipse(QPointF(cx + 4.2, cy - 3.2), 6, 6)
    p.setPen(Qt.NoPen)
    p.setBrush(col)
    p.drawPath(path.subtracted(cut))


class ThemeButton(QPushButton, ThemeAware):
    """Top button to switch between light and dark mode."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ThemeBtn")
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tr("theme.tooltip"))
        self._refresh_text()

    def _refresh_text(self):
        self.setText("      " + tr("theme.dark" if self.theme_name == "dark" else "theme.light"))

    def set_theme(self, name: str):
        self.theme_name = name
        self._refresh_text()
        self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy = 19, self.height() / 2
        if self.theme_name == "dark":
            draw_moon(p, cx, cy, self.c("accent"))
        else:
            draw_sun(p, cx, cy, self.c("accent"))


# --------------------------------------------------------------------------- tarjeta
class Card(QFrame):
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 16)
        lay.setSpacing(10)
        head = QVBoxLayout()
        head.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("CardTitle")
        head.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("Muted")
            s.setWordWrap(True)
            head.addWidget(s)
        lay.addLayout(head)
        self.body = lay


def row(label: str, widget: QWidget, hint: str = "") -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(12)
    col = QVBoxLayout()
    col.setSpacing(1)
    lab = QLabel(label)
    col.addWidget(lab)
    if hint:
        h = QLabel(hint)
        h.setObjectName("Muted")
        h.setWordWrap(True)
        col.addWidget(h)
    lay.addLayout(col, 1)
    lay.addWidget(widget, 0, Qt.AlignRight | Qt.AlignVCenter)
    return w


# --------------------------------------------------------------------------- control segmentado
class Segmented(QFrame):
    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        self.setObjectName("SegWrap")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: dict[str, QPushButton] = {}
        for key, text in options:
            b = QPushButton(text)
            b.setObjectName("Seg")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
            self.group.addButton(b)
            lay.addWidget(b)
            self.buttons[key] = b

    def set_value(self, key: str):
        if key in self.buttons:
            self.buttons[key].setChecked(True)


# --------------------------------------------------------------------------- hotkey capture
def mouse_button_name(code: int) -> str:
    return tr({1: "hotkey.mouse_x1", 2: "hotkey.mouse_x2", 3: "hotkey.mouse_middle"}.get(code, "hotkey.mouse_x1"))


def hotkey_display_name(hk: dict) -> str:
    """Name shown in the UI (mouse buttons are translated; keys use their key name)."""
    if hk.get("kind") == "mouse":
        return mouse_button_name(int(hk.get("code", 1)))
    return hk.get("name", "?")


class HotkeyButton(QPushButton):
    """When clicked, waits for the next key or side mouse button."""
    hotkey_changed = Signal(dict)
    capture_state = Signal(bool)

    def __init__(self, hotkey: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("Hotkey")
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.hotkey = hotkey
        self.capturing = False
        self.clicked.connect(self._start)
        self._refresh()

    def _refresh(self):
        self.setProperty("capturing", self.capturing)
        self.style().unpolish(self)
        self.style().polish(self)
        self.setText(tr("hotkey.waiting") if self.capturing else hotkey_display_name(self.hotkey))

    def set_hotkey(self, hk: dict):
        self.hotkey = hk
        self._refresh()

    def _start(self):
        if self.capturing:
            return
        self.capturing = True
        self.capture_state.emit(True)
        self.grabKeyboard()
        self._refresh()

    def _finish(self, hk: dict | None):
        self.capturing = False
        self.releaseKeyboard()
        self.capture_state.emit(False)
        if hk:
            self.hotkey = hk
            self.hotkey_changed.emit(hk)
        self._refresh()

    def keyPressEvent(self, e):
        if not self.capturing:
            return super().keyPressEvent(e)
        if e.key() == Qt.Key_Escape:
            self._finish(None)
            return
        vk = e.nativeVirtualKey() if sys.platform == "win32" else e.key()
        if e.key() in (Qt.Key_Shift, Qt.Key_Control, Qt.Key_Alt, Qt.Key_Meta, Qt.Key_AltGr) or \
                (sys.platform == "win32" and vk in FORBIDDEN_HOTKEY_VKS):
            self.setText(tr("hotkey.no_modifiers"))
            return
        name = QKeySequence(e.key()).toString(QKeySequence.NativeText) or f"Tecla {vk}"
        if e.modifiers() & Qt.KeypadModifier:
            name = "Num " + name
        self._finish({"kind": "key", "code": int(vk), "name": name})

    def mousePressEvent(self, e):
        if self.capturing:
            mapping = {Qt.XButton1: 1, Qt.XButton2: 2, Qt.MiddleButton: 3}
            code = mapping.get(e.button())
            if code:
                self._finish({"kind": "mouse", "code": code, "name": mouse_button_name(code)})
            elif e.button() == Qt.RightButton:
                self._finish(None)
            return
        super().mousePressEvent(e)

    def focusOutEvent(self, e):
        if self.capturing:
            self._finish(None)
        super().focusOutEvent(e)


# --------------------------------------------------------------------------- area preview
class AreaPreview(QWidget, ThemeAware):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.w_px, self.h_px = 460, 150
        self.setMinimumHeight(110)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_size(self, w: int, h: int):
        self.w_px, self.h_px = w, h
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(self.c("border"), 1))
        p.setBrush(self.c("surface2"))
        p.drawRoundedRect(r, 8, 8)
        # simulates a 1920x1080 screen
        sw, sh = 1920, 1080
        scale = min((r.width() - 20) / sw, (r.height() - 20) / sh)
        scr = QRectF(0, 0, sw * scale, sh * scale)
        scr.moveCenter(r.center())
        p.setPen(QPen(self.c("muted"), 1, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(scr, 4, 4)
        aw, ah = min(self.w_px, sw) * scale, min(self.h_px, sh) * scale
        area = QRectF(0, 0, aw, ah)
        area.moveCenter(scr.center())
        acc = self.c("accent")
        fill = QColor(acc)
        fill.setAlpha(40)
        p.setBrush(fill)
        p.setPen(QPen(acc, 1.6))
        p.drawRoundedRect(area, 3, 3)
        # cursor
        c = scr.center()
        path = QPainterPath()
        path.moveTo(c)
        path.lineTo(c + QPointF(0, 11))
        path.lineTo(c + QPointF(3, 8.5))
        path.lineTo(c + QPointF(5.5, 13))
        path.lineTo(c + QPointF(7, 12))
        path.lineTo(c + QPointF(4.8, 7.8))
        path.lineTo(c + QPointF(8.5, 7.6))
        path.closeSubpath()
        p.setPen(QPen(QColor("#000000"), 1))
        p.setBrush(QColor("#ffffff"))
        p.drawPath(path)
        p.setPen(self.c("muted"))
        p.drawText(scr.adjusted(6, 4, -6, -4), Qt.AlignRight | Qt.AlignBottom, tr("area.preview_screen"))
