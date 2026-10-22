"""Capture -> OCR -> filtering -> translation. Shared by the "on release" and live modes.

Reading improvements:
  * A region LARGER than the area is captured, then the lines touching the area are kept
    whole. This avoids words cut by the area edge ("'oa juego").
  * A plain margin is added around the image: OCR engines fail on text touching the border.
  * If nothing is found, it retries with a grayscale, higher-contrast image.
  * "Lines" made only of stray symbols (frame or icon leftovers) are discarded.
"""
from __future__ import annotations

import logging
import re
import threading
from collections import OrderedDict
from difflib import SequenceMatcher

import cv2
import numpy as np

from gocr import capture
from gocr.ocr import OcrLine, TextBlock, get_engine, group_lines, sample_colors
from gocr.translate import TranslateError, translate_texts
from gocr.i18n import tr
from gocr.wordsplit import fix_spacing

log = logging.getLogger(__name__)

PAD = 16
_ALNUM = re.compile(r"[^\W_]", re.UNICODE)


def expanded_rect(area: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Capture region: the area plus a margin so words are not cut."""
    x, y, w, h = area
    mx = int(max(60, w * 0.4))
    my = int(max(40, h * 0.6))   # tall margin so the other lines of the paragraph fit
    return capture.intersect_monitor(x - mx, y - my, w + 2 * mx, h + 2 * my, center=(x + w // 2, y + h // 2))


def _pad(img: np.ndarray, pad: int = PAD) -> np.ndarray:
    border = np.concatenate([img[0, :, :3], img[-1, :, :3], img[:, 0, :3], img[:, -1, :3]])
    color = [int(c) for c in np.median(border, axis=0)] + [255]
    return cv2.copyMakeBorder(img, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=color)


def _enhance(img: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
    gray = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gray)
    if np.median(gray) < 110:      # light text on a dark background -> invert
        gray = 255 - gray
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGRA)


def _clean(text: str) -> str:
    text = text.strip().strip("|¦").strip()
    return text


def recognize(engine, img: np.ndarray) -> list[OcrLine]:
    """OCR with a margin and a contrast retry. Coordinates are relative to `img`."""
    for attempt, src in enumerate((img, None)):
        if src is None:
            src = _enhance(img)
        lines = engine.recognize(_pad(src))
        out = []
        for ln in lines:
            text = _clean(ln.text)
            if not _ALNUM.search(text):
                continue  # symbols only: noise
            text = fix_spacing(text)  # "EXITGAME" → "EXIT GAME"
            out.append(ln.shifted(-PAD, -PAD, text))
        if out or attempt == 1:
            return out
    return []


def lines_touching_area(lines: list[OcrLine], cap: tuple[int, int, int, int],
                        area: tuple[int, int, int, int]) -> list[OcrLine]:
    """Moves the lines to screen coordinates and keeps the ones touching the area."""
    cx, cy = cap[0], cap[1]
    ax, ay, aw, ah = area
    keep = []
    for ln in lines:
        x, y = ln.x + cx, ln.y + cy
        v_overlap = min(y + ln.h, ay + ah) - max(y, ay)
        h_overlap = min(x + ln.w, ax + aw) - max(x, ax)
        if v_overlap >= 0.5 * ln.h and h_overlap >= min(8, ln.w * 0.5):
            keep.append(ln.shifted(cx, cy))
    return keep


class TranslationCache:
    """Avoids requesting the same sentence twice (key for live mode)."""

    def __init__(self, size: int = 600):
        self.size = size
        self.data: OrderedDict[tuple, str] = OrderedDict()
        self.lock = threading.Lock()

    def get(self, key):
        with self.lock:
            if key in self.data:
                self.data.move_to_end(key)
                return self.data[key]
        return None

    def find_similar(self, text: str, target: str, source: str, min_ratio: float = 0.86):
        """OCR sometimes changes one letter between passes ("Manager"/"Manaqer"): reuse the
        translation of an almost identical sentence instead of requesting it again."""
        if len(text) < 4:
            return None
        with self.lock:
            keys = list(self.data.keys())[-200:]
        best, best_r = None, min_ratio
        for k in reversed(keys):
            if k[1] != target or k[2] != source or abs(len(k[0]) - len(text)) > max(3, len(text) // 5):
                continue
            r = SequenceMatcher(None, k[0].lower(), text.lower()).ratio()
            if r >= best_r:
                best, best_r = k, r
        return self.get(best) if best else None

    def put(self, key, value):
        with self.lock:
            self.data[key] = value
            self.data.move_to_end(key)
            while len(self.data) > self.size:
                self.data.popitem(last=False)


def ocr_screen_lines(img: np.ndarray, cap: tuple[int, int, int, int], opts: dict) -> list[OcrLine]:
    """OCR of the whole capture; returns ALL lines in screen coordinates."""
    engine = get_engine(opts["ocr_engine"], opts["ocr_lang"])
    return [ln.shifted(cap[0], cap[1]) for ln in recognize(engine, img)]


def _filter_area(lines: list[OcrLine], area: tuple[int, int, int, int]) -> list[OcrLine]:
    return lines_touching_area(lines, (0, 0, 0, 0), area)


def _iou(a: TextBlock, b: TextBlock) -> float:
    x0, y0 = max(a.x, b.x), max(a.y, b.y)
    x1, y1 = min(a.x + a.w, b.x + b.w), min(a.y + a.h, b.y + b.h)
    inter = max(0, x1 - x0) * max(0, y1 - y0)
    union = a.w * a.h + b.w * b.h - inter
    return inter / union if union else 0.0


def _select_words(ln: OcrLine, area) -> tuple[list, float]:
    """Words of the line that are at least half inside the area (horizontally).
    Returns (words, fraction of the line's letters that were selected)."""
    ax, aw = area[0], area[2]
    boxes = ln.word_boxes()
    chosen = [wb for wb in boxes if min(wb[1] + wb[3], ax + aw) - max(wb[1], ax) >= 0.5 * wb[3]]
    if not chosen:  # the area is smaller than the word: take the one it touches the most
        best = max(boxes, key=lambda wb: min(wb[1] + wb[3], ax + aw) - max(wb[1], ax), default=None)
        if best is not None and min(best[1] + best[3], ax + aw) - max(best[1], ax) > 0:
            chosen = [best]
    total = sum(len(wb[0]) for wb in boxes) or 1
    return chosen, sum(len(wb[0]) for wb in chosen) / total


def select_blocks(lines: list[OcrLine], area) -> list[TextBlock]:
    """Decides which text gets translated: only what is inside the area.
      * Lines count when at least half of their height is inside the area.
      * Within a line, only the words that are at least half inside the area are kept
        (e.g. a single word). Lines outside the area are never added.
      * Selected lines that belong together are joined so the translation has context.
    """
    touching = lines_touching_area(lines, (0, 0, 0, 0), area)
    selected = []
    for ln in touching:
        words, frac = _select_words(ln, area)
        if frac >= 0.95:
            selected.append(ln)                      # the whole line is inside
        elif words and not (len(words) == 1 and len(words[0][0]) <= 1):  # skip stray cut-off letters
            x0 = min(w[1] for w in words)
            x1 = max(w[1] + w[3] for w in words)
            text = fix_spacing(" ".join(w[0] for w in words))
            selected.append(OcrLine(text, x0, ln.y, max(1, x1 - x0), ln.h, list(words)))
    blocks = group_lines(selected) if selected else []
    blocks.sort(key=lambda b: (b.y, b.x))
    return blocks


def build_blocks(lines: list[OcrLine], img: np.ndarray, cap: tuple[int, int, int, int],
                 area: tuple[int, int, int, int], opts: dict, cache: TranslationCache,
                 prev: list[TextBlock] | None = None, on_stage=None) -> tuple[list[TextBlock], str | None]:
    """Lines (screen) -> translated blocks for the area. Reuses translations whenever possible."""
    blocks = select_blocks(lines, area)
    if not blocks:
        return [], None
    sample_colors(img, blocks, offset=(cap[0], cap[1]))
    target, source = opts["target_lang"], opts["source_lang"]
    missing = []
    for b in blocks:
        t = cache.get((b.text, target, source))
        if t is None and prev:  # same place and almost the same text as what is on screen
            for pb in prev:
                if pb.translation and _iou(b, pb) > 0.35 and \
                        SequenceMatcher(None, pb.text.lower(), b.text.lower()).ratio() >= 0.8:
                    t = pb.translation
                    b.text = pb.text
                    break
        if t is None:
            t = cache.find_similar(b.text, target, source)
        if t is None:
            missing.append(b)
        else:
            b.translation = t
    warning = None
    if missing:
        if on_stage:
            on_stage(tr("area.translating"))
        try:
            results = translate_texts([b.text for b in missing], target, source)
            for b, t in zip(missing, results):
                b.translation = t
                cache.put((b.text, target, source), t)
        except TranslateError as exc:
            warning = str(exc)
    return blocks, warning


def process(img: np.ndarray, cap: tuple[int, int, int, int], area: tuple[int, int, int, int],
            opts: dict, cache: TranslationCache, on_stage=None) -> tuple[list[TextBlock], str | None]:
    """Release mode: full OCR + translation."""
    lines = ocr_screen_lines(img, cap, opts)
    return build_blocks(lines, img, cap, area, opts, cache, None, on_stage)


def live_full(img, cap, area, opts, cache, prev):
    """Live mode, new pass: also returns the lines so they can be reused."""
    lines = ocr_screen_lines(img, cap, opts)
    blocks, warning = build_blocks(lines, img, cap, area, opts, cache, prev)
    return blocks, warning, lines


def live_reuse(lines, img, cap, area, opts, cache, prev):
    """Live mode, the screen did not change and only the area moved: no OCR."""
    blocks, warning = build_blocks(lines, img, cap, area, opts, cache, prev)
    return blocks, warning, lines
