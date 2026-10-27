"""OCR engines and shared helpers (grouping lines into paragraphs, background colors)."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

import numpy as np

log = logging.getLogger(__name__)

ENGINES = {
    "windows": "Windows OCR",
    "rapid": "RapidOCR",
}


class OcrError(Exception):
    """Error whose message is meant to be shown to the user."""


@dataclass
class OcrLine:
    text: str
    x: int
    y: int
    w: int
    h: int
    # words with their position: [(text, x, y, w, h)] (to pick only those the area touches)
    words: list | None = None

    def shifted(self, dx: int, dy: int, text: str | None = None) -> "OcrLine":
        words = [(t, x + dx, y + dy, w, h) for t, x, y, w, h in self.words] if self.words else None
        return OcrLine(self.text if text is None else text, self.x + dx, self.y + dy, self.w, self.h, words)

    def word_boxes(self) -> list:
        """Words with positions; if the engine gave none, they are spread by letter count."""
        if self.words:
            return self.words
        parts = self.text.split()
        total = sum(len(p) for p in parts) + max(0, len(parts) - 1)
        out, pos = [], 0
        for p in parts:
            x0 = self.x + self.w * pos / max(total, 1)
            x1 = self.x + self.w * (pos + len(p)) / max(total, 1)
            out.append((p, int(x0), self.y, max(1, int(x1 - x0)), self.h))
            pos += len(p) + 1
        return out


@dataclass
class TextBlock:
    text: str
    x: int
    y: int
    w: int
    h: int
    line_h: float
    lines: list[OcrLine] = field(default_factory=list)
    translation: str = ""
    bg: tuple[int, int, int] = (20, 20, 20)
    fg: tuple[int, int, int] = (255, 255, 255)


_engine_lock = threading.Lock()
_engine_cache: dict[tuple, object] = {}


def engine_variant(opts: dict) -> str:
    """Windows OCR uses a language; RapidOCR uses an alphabet (auto / latin / chinese)."""
    return opts.get("ocr_lang", "en-US") if opts.get("ocr_engine") == "windows" else opts.get("rapid_script", "auto")


def get_engine(name: str, lang: str):
    """Returns (and caches) an engine instance. Always call it from the OCR thread.
    `lang` is the Windows OCR language, or the RapidOCR alphabet."""
    key = (name, lang)
    with _engine_lock:
        eng = _engine_cache.get(key)
        if eng is None:
            if name == "rapid":
                from gocr.ocr.rapid_ocr import RapidOcr
                eng = RapidOcr(lang)
            else:
                from gocr.ocr.windows_ocr import WindowsOcr
                eng = WindowsOcr(lang)
            _engine_cache[key] = eng
        return eng


def upscale_factor(w: int, h: int, max_side: int) -> float:
    """OCR engines fail on small text: the capture is upscaled (up to 3x)."""
    longest = max(w, h, 1)
    return float(max(1.0, min(3.0, max_side / longest)))


# --------------------------------------------------------------------------- grouping
def _join_text(parts: list[str]) -> str:
    out = ""
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if out.endswith("-") and p[:1].islower():
            out = out[:-1] + p
        elif out:
            out += " " + p
        else:
            out = p
    return out


def group_lines(lines: list[OcrLine]) -> list[TextBlock]:
    """Joins consecutive lines of the same paragraph so the translation has context."""
    lines = [ln for ln in lines if ln.text.strip()]
    if not lines:
        return []
    lines.sort(key=lambda ln: (ln.y, ln.x))
    blocks: list[list[OcrLine]] = []
    for ln in lines:
        target = None
        for blk in reversed(blocks[-4:]):
            last = blk[-1]
            avg_h = sum(b.h for b in blk) / len(blk)
            gap = ln.y - (last.y + last.h)
            similar = 0.6 <= (ln.h / max(avg_h, 1)) <= 1.6
            bx0 = min(b.x for b in blk)
            bx1 = max(b.x + b.w for b in blk)
            overlap = min(bx1, ln.x + ln.w) - max(bx0, ln.x)
            if -0.5 * avg_h <= gap <= 0.9 * avg_h and similar and overlap > 0:
                target = blk
                break
        if target is None:
            blocks.append([ln])
        else:
            target.append(ln)

    result = []
    for blk in blocks:
        x0 = min(b.x for b in blk)
        y0 = min(b.y for b in blk)
        x1 = max(b.x + b.w for b in blk)
        y1 = max(b.y + b.h for b in blk)
        result.append(TextBlock(
            text=_join_text([b.text for b in blk]),
            x=x0, y=y0, w=x1 - x0, h=y1 - y0,
            line_h=sum(b.h for b in blk) / len(blk),
            lines=blk,
        ))
    return result


def sample_colors(img_bgra: np.ndarray, blocks: list[TextBlock], offset: tuple[int, int] = (0, 0)) -> None:
    """Estimates each block's background color (rectangle border) and picks a contrasting
    text color, so the translation looks like it belongs in place."""
    H, W = img_bgra.shape[:2]
    ox, oy = offset
    for b in blocks:
        pad = 3
        bx, by = b.x - ox, b.y - oy
        x0, y0 = max(0, bx - pad), max(0, by - pad)
        x1, y1 = min(W, bx + b.w + pad), min(H, by + b.h + pad)
        region = img_bgra[y0:y1, x0:x1, :3]
        if region.size == 0:
            continue
        border = np.concatenate([
            region[0, :], region[-1, :], region[:, 0], region[:, -1],
        ]).reshape(-1, 3)
        bgr = np.median(border, axis=0)
        r, g, bl = int(bgr[2]), int(bgr[1]), int(bgr[0])
        b.bg = (r, g, bl)
        lum = 0.2126 * r + 0.7152 * g + 0.0722 * bl
        b.fg = (20, 20, 20) if lum > 150 else (250, 250, 250)
