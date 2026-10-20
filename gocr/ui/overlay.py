"""Overlay that paints the translation on top of the original text.

Blocks arrive in physical screen coordinates (where the game text is), so the translation
stays on top of the text even when the area moves (live mode)."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QToolTip, QWidget

from gocr import winapi
from gocr.i18n import tr
from gocr.ocr import TextBlock
from gocr.ui import theme as th

PAD_X, PAD_Y = 6, 3
MIN_FONT, MAX_FONT = 11, 30


class ResultOverlay(QWidget):
    closed = Signal()

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool |
                         Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.theme = "dark"
        self.style_mode = "auto"
        self.opacity = 1.0
        self.show_tooltip = True
        self.interactive = True
        self.excluded = False          # invisible to screen captures
        self.items: list[tuple[QRectF, QFont, TextBlock]] = []   # coordenadas locales
        self.view: QRectF | None = None                          # live mode: only what touches the area
        self.message = ""
        self.message_kind = "info"
        self.msg_anchor = QRectF()
        self.flash = ""
        self._created = False
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.dismiss)
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._clear_flash)

    # ------------------------------------------------------------------ native window
    def ensure_native(self) -> None:
        if not self._created:
            self.winId()
            self._created = True

    def set_excluded(self, exclude: bool) -> bool:
        """In live mode the translation is invisible to captures (so it is never read again).
        In release mode / while snipping it becomes visible again so it shows up in the snip."""
        self.ensure_native()
        ok = winapi.exclude_from_capture(self, exclude)
        self.excluded = exclude and ok
        return self.excluded

    def set_interactive(self, on: bool):
        self.interactive = on
        self.setCursor(Qt.PointingHandCursor if on else Qt.ArrowCursor)
        if self.isVisible():
            winapi.make_overlay_window(self, click_through=not on)

    def _show(self, auto_hide: int):
        self.ensure_native()
        if not self.isVisible():
            self.show()
        self.raise_()
        winapi.make_overlay_window(self, click_through=not self.interactive)
        self._hide_timer.stop()
        if auto_hide > 0:
            self._hide_timer.start(int(auto_hide * 1000))
        self.update()

    def start_auto_hide(self, seconds: int):
        self._hide_timer.stop()
        if seconds > 0:
            self._hide_timer.start(int(seconds * 1000))

    # ------------------------------------------------------------------ mostrar
    def show_blocks(self, blocks: list[TextBlock], area_phys: tuple[int, int, int, int],
                    auto_hide: int = 0, interactive: bool = True):
        self.message = ""
        self.interactive = interactive
        ax, ay, aw, ah = area_phys
        bounds = QRectF(winapi.logical_screen_rect_at_phys(ax + aw // 2, ay + ah // 2))
        placed = []
        for b in blocks:
            dpr = winapi.dpr_at_phys(b.x + b.w // 2, b.y + b.h // 2)
            r = QRectF(winapi.phys_rect_to_logical(b.x, b.y, b.w, b.h)).adjusted(-PAD_X, -PAD_Y, PAD_X, PAD_Y)
            font, r = self._fit(b.translation or b.text, r, b.line_h / dpr, bounds)
            placed.append((r, font, b))
        if not placed:
            self.items = []
            self.hide()
            return
        union = QRectF(placed[0][0])
        for r, _f, _b in placed[1:]:
            union = union.united(r)
        geo = union.adjusted(-4, -4, 4, 8).toAlignedRect().intersected(bounds.toAlignedRect())
        self.setGeometry(geo)
        off = QRectF(geo).topLeft()
        self.items = [(r.translated(-off), f, b) for r, f, b in placed]
        self._show(auto_hide)

    def show_message(self, area_phys: tuple[int, int, int, int], text: str, kind: str = "info", seconds: float = 3.0):
        self.items = []
        self.message = text
        self.message_kind = kind
        self.interactive = True
        x, y, w, h = area_phys
        anchor = QRectF(winapi.phys_rect_to_logical(x, y, w, h))
        bounds = winapi.logical_screen_rect_at_phys(x + w // 2, y + h // 2)
        geo = anchor.adjusted(-170, -20, 170, 90).toAlignedRect().intersected(bounds)
        self.setGeometry(geo)
        self.msg_anchor = anchor.translated(-QRectF(geo).topLeft())
        self._show(int(seconds) if seconds else 0)

    def set_view(self, area_phys: tuple[int, int, int, int] | None):
        """Live mode: hides the blocks that no longer touch the area (like a camera translator)."""
        if area_phys is None:
            view = None
        else:
            view = QRectF(winapi.phys_rect_to_logical(*area_phys)).translated(-QRectF(self.geometry()).topLeft())
        old_vis = self._visible_ids()
        self.view = view
        if self._visible_ids() != old_vis:
            self.update()

    def _visible_ids(self):
        if self.view is None:
            return tuple(range(len(self.items)))
        return tuple(i for i, (r, _f, _b) in enumerate(self.items) if r.intersects(self.view))

    def dismiss(self):
        self._hide_timer.stop()
        if self.isVisible():
            self.hide()
            QToolTip.hideText()
        self.items = []
        self.message = ""
        self.closed.emit()

    # ------------------------------------------------------------------ text fitting
    @staticmethod
    def _font(px: float) -> QFont:
        f = QFont("Segoe UI")
        f.setPixelSize(max(MIN_FONT, int(px)))
        f.setWeight(QFont.DemiBold)
        return f

    @staticmethod
    def _text_rect(font: QFont, text: str, width: float) -> QRectF:
        fm = QFontMetricsF(font)
        return fm.boundingRect(QRectF(0, 0, max(10.0, width - 2 * PAD_X), 10000),
                               int(Qt.TextWordWrap | Qt.AlignLeft), text)

    def _fit(self, text: str, r: QRectF, line_h: float, bounds: QRectF) -> tuple[QFont, QRectF]:
        size = max(MIN_FONT, min(MAX_FONT, line_h * 0.85))
        while True:
            font = self._font(size)
            tr = self._text_rect(font, text, r.width())
            if tr.height() <= r.height() - 2 * PAD_Y + 1 and tr.width() <= r.width() - 2 * PAD_X + 1:
                return font, r
            if size <= MIN_FONT:
                break
            size -= 1
        font = self._font(MIN_FONT)
        if r.width() < 220:  # does not fit: widen, then grow downwards
            grow = min(220, bounds.width()) - r.width()
            r = r.adjusted(-grow / 2, 0, grow / 2, 0)
        tr = self._text_rect(font, text, r.width())
        r.setHeight(max(r.height(), tr.height() + 2 * PAD_Y + 2))
        if r.left() < bounds.left():
            r.moveLeft(bounds.left())
        if r.right() > bounds.right():
            r.moveRight(bounds.right())
        if r.bottom() > bounds.bottom():
            r.moveBottom(bounds.bottom())
        return font, r

    # ------------------------------------------------------------------ pintar
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        if self.message:
            key = {"error": "danger", "warn": "warn"}.get(self.message_kind, "accent")
            self._pill(p, self.message, self.msg_anchor.center().x(), self.msg_anchor.center().y() - 18, key)
            return
        alpha = int(255 * max(0.3, min(1.0, self.opacity)))
        visible = set(self._visible_ids())
        for i, (r, font, b) in enumerate(self.items):
            if i not in visible:
                continue
            if self.style_mode == "auto":
                bg, fg = QColor(*b.bg), QColor(*b.fg)
            else:
                bg, fg = th.color(self.theme, "surface"), th.color(self.theme, "text")
            bg.setAlpha(alpha)
            path = QPainterPath()
            path.addRoundedRect(r, 5, 5)
            p.fillPath(path.translated(0, 2), QColor(0, 0, 0, 70))
            p.fillPath(path, bg)
            if self.style_mode == "auto":
                edge = QColor(fg)
                edge.setAlpha(45)
                p.setPen(QPen(edge, 1))
            else:
                p.setPen(QPen(th.color(self.theme, "accent"), 1.2))
            p.drawPath(path)
            p.setPen(fg)
            p.setFont(font)
            p.drawText(r.adjusted(PAD_X, PAD_Y, -PAD_X, -PAD_Y), int(Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignVCenter),
                       b.translation or b.text)
        if self.flash:
            first = self.items[0][0] if self.items else QRectF(0, 0, self.width(), 0)
            self._pill(p, self.flash, first.center().x(), first.top() - 36, "accent")

    def _pill(self, p: QPainter, text: str, center_x: float, top: float, color_key: str):
        font = QFont("Segoe UI")
        font.setPixelSize(13)
        font.setWeight(QFont.DemiBold)
        p.setFont(font)
        fm = QFontMetricsF(font)
        maxw = min(self.width() - 10, 460)
        tr = fm.boundingRect(QRectF(0, 0, max(40, maxw - 28), 1000), int(Qt.TextWordWrap), text)
        r = QRectF(0, 0, tr.width() + 28, tr.height() + 16)
        r.moveLeft(max(4, min(center_x - r.width() / 2, self.width() - r.width() - 4)))
        r.moveTop(max(4, min(top, self.height() - r.height() - 4)))
        path = QPainterPath()
        path.addRoundedRect(r, 10, 10)
        p.fillPath(path.translated(0, 2), QColor(0, 0, 0, 80))
        p.fillPath(path, th.color(self.theme, "surface"))
        p.setPen(QPen(th.color(self.theme, color_key), 1.5))
        p.drawPath(path)
        p.setPen(th.color(self.theme, "text"))
        p.drawText(r.adjusted(14, 8, -14, -8), int(Qt.TextWordWrap | Qt.AlignCenter), text)

    def _clear_flash(self):
        self.flash = ""
        self.update()

    # ------------------------------------------------------------------ mouse
    def _item_at(self, pos) -> TextBlock | None:
        for r, _f, b in self.items:
            if r.contains(pos):
                return b
        return None

    def mouseMoveEvent(self, e):
        if not (self.show_tooltip and self.interactive):
            return
        b = self._item_at(e.position())
        if b and b.translation and b.translation != b.text:
            QToolTip.showText(e.globalPosition().toPoint() + QPoint(12, 16), tr("overlay.original", text=b.text), self)
        else:
            QToolTip.hideText()

    def mousePressEvent(self, e):
        if not self.interactive:
            return
        if e.button() == Qt.RightButton:
            b = self._item_at(e.position())
            text = "\n".join((x.translation or x.text) for _r, _f, x in self.items) if b is None else (b.translation or b.text)
            if text:
                QGuiApplication.clipboard().setText(text)
                self.flash = tr("overlay.copied")
                self._flash_timer.start(1200)
                self.update()
            return
        self.dismiss()
