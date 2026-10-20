"""Frame that follows the mouse while the hotkey is held."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from gocr import winapi
from gocr.ui import theme as th

MARGIN = 6        # room for the border, outside the captured region
LABEL_H = 30      # room for the size label


class AreaWidget(QWidget):
    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool |
                         Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.theme = "dark"
        self.phys = (0, 0, 100, 50)
        self.box = QRect()
        self.busy_text = ""
        self.label = ""          # p. ej. "En vivo"
        self.excluded = False
        self._dash = 0
        self._anim = QTimer(self)
        self._anim.setInterval(40)
        self._anim.timeout.connect(self._tick)
        self._styled = False
        self._native = False

    def _tick(self):
        self._dash = (self._dash + 1) % 16
        self.update()

    def set_phys_rect(self, x: int, y: int, w: int, h: int):
        self.phys = (x, y, w, h)
        logical = winapi.phys_rect_to_logical(x, y, w, h)
        self.box = QRect(MARGIN, MARGIN, logical.width(), logical.height())
        self.setGeometry(logical.x() - MARGIN, logical.y() - MARGIN,
                         logical.width() + 2 * MARGIN, logical.height() + 2 * MARGIN + LABEL_H)
        self.update()

    def ensure_native(self) -> bool:
        if not self._native:
            self.winId()
            self.excluded = winapi.exclude_from_capture(self)
            self._native = True
        return self.excluded

    def show_aiming(self, label: str = ""):
        self.busy_text = ""
        self.label = label
        self._anim.stop()
        self.ensure_native()
        if not self.isVisible():
            self.show()
            if not self._styled:
                winapi.make_overlay_window(self, click_through=True)
                self._styled = True
        self.update()

    def set_label(self, label: str):
        if label != self.label:
            self.label = label
            self.update()

    def show_busy(self, text: str):
        self.busy_text = text
        self._anim.start()
        self.update()

    def hide_area(self):
        self._anim.stop()
        self.busy_text = ""
        self.hide()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        acc = th.color(self.theme, "accent")
        box = QRectF(self.box).adjusted(-2, -2, 2, 2)  # the border stays outside the capture

        # soft shadow so it is visible on both light and dark backgrounds
        p.setPen(QPen(QColor(0, 0, 0, 110), 4))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(box.adjusted(-1, -1, 1, 1), 6, 6)

        pen = QPen(acc, 2)
        if self.busy_text:
            pen.setDashPattern([5, 3])
            pen.setDashOffset(-self._dash)
        p.setPen(pen)
        p.drawRoundedRect(box, 5, 5)

        # esquinas marcadas
        p.setPen(QPen(acc, 3.2, Qt.SolidLine, Qt.RoundCap))
        L = min(16, box.width() / 4, box.height() / 3)
        for (x, y, dx, dy) in ((box.left(), box.top(), 1, 1), (box.right(), box.top(), -1, 1),
                               (box.left(), box.bottom(), 1, -1), (box.right(), box.bottom(), -1, -1)):
            p.drawLine(QPointF(x, y + dy * 5), QPointF(x, y + dy * L))
            p.drawLine(QPointF(x + dx * 5, y), QPointF(x + dx * L, y))

        # label below the area
        w, h = self.phys[2], self.phys[3]
        size = f"{w} × {h}"
        text = self.busy_text or (f"{self.label}  ·  {size}" if self.label else size)
        font = QFont("Segoe UI", 9)
        font.setBold(True)
        p.setFont(font)
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(text) + 18
        pill = QRectF(box.center().x() - tw / 2, box.bottom() + 6, tw, 20)
        if pill.left() < 0:
            pill.moveLeft(0)
        path = QPainterPath()
        path.addRoundedRect(pill, 10, 10)
        p.fillPath(path, acc)
        p.setPen(th.color(self.theme, "on_accent"))
        p.drawText(pill, Qt.AlignCenter, text)
