"""Splits words that OCR glued together ("EXITGAME" -> "EXIT GAME").

Many games use capital letters with very little spacing between words and OCR misses the
gap. Google cannot translate "EXITGAME" and returns it unchanged. This finds the best way
to cut the word using a list of ~126,000 English words sorted by frequency
(algorithm and word list from wordninja, MIT license)."""
from __future__ import annotations

import gzip
import logging
import re
import threading
from math import log

from gocr.config import resource_path

log_ = logging.getLogger(__name__)

_lock = threading.Lock()
_cost: dict[str, float] | None = None
_rank: dict[str, int] = {}
_maxword = 0
_CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])")
_TOKEN = re.compile(r"^([^A-Za-z]*)([A-Za-z]+)([^A-Za-z]*)$")
MAX_RANK = 60000      # only cut into reasonably common words


def _load() -> bool:
    global _cost, _maxword
    with _lock:
        if _cost is not None:
            return bool(_cost)
        try:
            with gzip.open(resource_path("gocr", "data", "english_words.txt.gz")) as f:
                words = f.read().decode("utf-8").split()
            n = len(words)
            _cost = {w: log((i + 1) * log(n)) for i, w in enumerate(words)}
            _rank.update({w: i for i, w in enumerate(words)})
            _maxword = max(len(w) for w in words)
        except Exception:
            log_.exception("Could not load the word list")
            _cost = {}
        return bool(_cost)


_ALPHA = "abcdefghijklmnopqrstuvwxyz"
# 1-2 letter words allowed when cutting (avoids splits like "a pro a ch")
_TINY = {"a", "i", "of", "to", "in", "it", "is", "be", "as", "at", "so", "we", "he", "by", "or", "on", "do",
         "if", "me", "my", "up", "an", "go", "no", "us", "am", "ok", "oh", "hi"}
_edit_cache: dict[str, str | None] = {}


def _correct(w: str) -> str | None:
    """Common word one edit away (\"aproach\" -> \"approach\"), or None."""
    if w in _edit_cache:
        return _edit_cache[w]
    best, best_rank = None, MAX_RANK // 2
    splits = [(w[:i], w[i:]) for i in range(len(w) + 1)]
    cands = set()
    for L, R in splits:
        if R:
            cands.add(L + R[1:])                                   # borrar
            for c in _ALPHA:
                cands.add(L + c + R[1:])                           # cambiar
        if len(R) > 1:
            cands.add(L + R[1] + R[0] + R[2:])                     # intercambiar
        for c in _ALPHA:
            cands.add(L + c + R)                                   # insertar
    for c in cands:
        r = _rank.get(c)
        if r is not None and r < best_rank and len(c) >= 4:
            best, best_rank = c, r
    _edit_cache[w] = best
    return best


def _max_rank(k: int) -> int:
    """Short words only count if they are very common (avoids odd splits like \"ka edwin\")."""
    return 3000 if k <= 3 else (20000 if k == 4 else MAX_RANK)


def _segment(s: str, allow_soft: bool = True):
    """Dynamic programming: cuts `s` into words. Allows unknown words (proper names such
    as "Wyrdness") and words with one misread letter, with a penalty.
    Returns [(original_text, correction_or_None, kind)] with kind known|fixed|unknown."""
    low = s.lower()
    n = len(s)
    cost = [0.0] + [9e999] * n
    back: list = [None] * (n + 1)
    for i in range(1, n + 1):
        for k in range(1, min(i, max(_maxword, 16)) + 1):
            seg = low[i - k:i]
            prev = cost[i - k]
            if prev >= 9e999:
                continue
            r = _rank.get(seg)
            if r is not None and r <= _max_rank(k) and (k > 2 or seg in _TINY):
                c, kind, fix = _cost[seg] + 3.0, "known", None
            elif allow_soft and 6 <= k <= 12 and (fix := _correct(seg)):
                c, kind = _cost[fix] + 14.0, "fixed"
            elif allow_soft and 4 <= k <= 14:
                c, kind, fix = 10.0 + 3.0 * k, "unknown", None
            else:
                continue
            if prev + c < cost[i]:
                cost[i] = prev + c
                back[i] = (k, kind, fix)
    if cost[n] >= 9e999:
        return None
    out, i = [], n
    while i > 0:
        k, kind, fix = back[i]
        out.append((s[i - k:i], fix, kind))
        i -= k
    return list(reversed(out))


def _match_case(src: str, word: str) -> str:
    if src.isupper():
        return word.upper()
    if src[:1].isupper():
        return word[:1].upper() + word[1:]
    return word


def _fix_token(tok: str) -> str:
    m = _TOKEN.match(tok)
    if not m:
        return tok
    pre, word, post = m.groups()
    low = word.lower()
    if len(word) < 6 or low in _cost:
        return tok
    # CamelCase: "ModManager" → "Mod Manager"
    parts = _CAMEL.split(word)
    if len(parts) > 1 and all(p.lower() in _cost for p in parts):
        return pre + " ".join(parts) + post
    # short words: only if they split into known words; long ones may contain an unknown name
    # ("Wyrdness") or a word with one misread letter ("aproach")
    seg = _segment(word, allow_soft=len(word) >= 10)
    if not seg or len(seg) < 2:
        return tok
    known = sum(len(t) for t, _f, kind in seg if kind != "unknown")
    unknown = sum(1 for _t, _f, kind in seg if kind == "unknown")
    if known < 0.6 * len(word) or unknown > max(1, len(word) // 12):
        return tok
    words = [_match_case(t, f) if f else t for t, f, _k in seg]
    return pre + " ".join(words) + post


_PUNCT_GLUE = re.compile(r"(?<=[A-Za-z\u00C0-\u00FF]{2})([.!?;:,])(?=[A-Za-z\u00C0-\u00FF]{2})")


def fix_spacing(text: str) -> str:
    """Fixes glued words in Latin-script text. Other text is left untouched."""
    if text and not re.search(r"[\u3040-\u9fff\uac00-\ud7af]|www\.|://|@", text):
        # "US.SURPRISE.MANY" -> "US. SURPRISE. MANY" (OCR drops the space after the period)
        text = _PUNCT_GLUE.sub(r"\1 ", text)
    if not text or not re.search(r"[A-Za-z]{6,}", text) or re.search(r"[\u3040-\u9fff\uac00-\ud7af]", text):
        return text
    if not _load():
        return text
    return " ".join(_fix_token(t) for t in text.split(" "))
