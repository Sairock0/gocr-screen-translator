"""Translation through free Google Translate endpoints (no API key).

Google sometimes refuses one endpoint for a while (too many requests, network filters, etc.),
so several endpoints are tried in order and the one that works is remembered. After every
endpoint fails, requests pause for a few seconds so the block can lift instead of being
extended by live mode. Every failure is written to the log with its real cause.
"""
from __future__ import annotations

import html
import json
import logging
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from gocr.i18n import tr

log = logging.getLogger(__name__)

# Target languages offered in the UI (names come from gocr.i18n.lang_name)
TARGET_LANGS: list[str] = [
    "es", "en", "pt", "fr", "de", "it", "ca", "ja", "ko", "zh-CN", "zh-TW",
    "ru", "uk", "pl", "nl", "tr", "ar", "hi", "id", "vi", "th",
]
SOURCE_LANGS: list[str] = ["auto"] + TARGET_LANGS

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/129.0 Safari/537.36",
    "Accept": "*/*",
}
COOLDOWN_SECONDS = 4.0


class TranslateError(Exception):
    def __init__(self, message: str, kind: str = "offline"):
        super().__init__(message)
        self.kind = kind          # "offline" | "rate" | "http" | "parse"


# --------------------------------------------------------------------------- endpoints
def _fetch(url: str, params: dict, timeout: float) -> str:
    data = urllib.parse.urlencode(params)
    if len(data) < 6000:
        req = urllib.request.Request(f"{url}?{data}", headers=_HEADERS)
    else:  # long texts go by POST
        req = urllib.request.Request(url, data=data.encode("utf-8"), headers={
            **_HEADERS, "Content-Type": "application/x-www-form-urlencoded;charset=utf-8"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_response(payload: str) -> tuple[str, str]:
    """gtx endpoint: returns (translated text, detected language)."""
    data = json.loads(payload)
    segments = data[0] or []
    out = "".join(seg[0] for seg in segments if seg and isinstance(seg[0], str))
    detected = data[2] if len(data) > 2 and isinstance(data[2], str) else ""
    return out, detected


def _gtx(text, target, source, timeout):
    payload = _fetch("https://translate.googleapis.com/translate_a/single",
                     {"client": "gtx", "sl": source or "auto", "tl": target, "dt": "t", "q": text}, timeout)
    return parse_response(payload)


def parse_clients5(payload: str) -> tuple[str, str]:
    """dict-chrome-ex endpoint: [["Hola","en"]] (auto) or ["Hola"] (fixed source)."""
    data = json.loads(payload)
    first = data[0] if isinstance(data, list) and data else data
    if isinstance(first, list):
        return str(first[0]), str(first[1]) if len(first) > 1 else ""
    return str(first), ""


def _clients5(text, target, source, timeout):
    payload = _fetch("https://clients5.google.com/translate_a/t",
                     {"client": "dict-chrome-ex", "sl": source or "auto", "tl": target, "q": text}, timeout)
    return parse_clients5(payload)


_RESULT_RE = re.compile(r'<div[^>]*class="result-container"[^>]*>(.*?)</div>', re.S)


def parse_mobile(payload: str) -> tuple[str, str]:
    """translate.google.com/m HTML page."""
    m = _RESULT_RE.search(payload)
    if not m:
        raise ValueError("result-container not found")
    text = re.sub(r"<br\s*/?>", "\n", m.group(1))
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text), ""


def _mobile(text, target, source, timeout):
    payload = _fetch("https://translate.google.com/m",
                     {"sl": source or "auto", "tl": target, "hl": target, "q": text}, timeout)
    return parse_mobile(payload)


ENDPOINTS = [("gtx", _gtx), ("clients5", _clients5), ("mobile", _mobile)]
_lock = threading.Lock()
_preferred = 0                 # index of the endpoint that worked last
_cooldown_until = 0.0
_last_error: TranslateError | None = None


def _classify(exc: Exception) -> TranslateError:
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 429:
            return TranslateError(tr("err.rate_limited"), "rate")
        return TranslateError(tr("err.http", code=exc.code), "http")
    if isinstance(exc, (ValueError, KeyError, IndexError, TypeError)):
        return TranslateError(tr("err.http", code="parse"), "parse")
    return TranslateError(tr("err.offline"), "offline")


def _request(text: str, target: str, source: str, timeout: float) -> tuple[str, str]:
    """Tries every endpoint, starting with the one that worked last."""
    global _preferred, _cooldown_until, _last_error
    with _lock:
        if time.monotonic() < _cooldown_until and _last_error is not None:
            raise _last_error
        start = _preferred
    error: TranslateError | None = None
    for i in range(len(ENDPOINTS)):
        idx = (start + i) % len(ENDPOINTS)
        name, fn = ENDPOINTS[idx]
        try:
            result = fn(text, target, source, timeout)
            with _lock:
                if _preferred != idx:
                    log.info("Translation endpoint switched to %s", name)
                _preferred = idx
                _last_error = None
            return result
        except Exception as exc:  # noqa: BLE001 - every failure is logged and classified
            log.warning("Translation endpoint %s failed: %r", name, exc)
            error = _classify(exc)
    with _lock:
        _cooldown_until = time.monotonic() + COOLDOWN_SECONDS
        _last_error = error
    raise error


def translate_texts(texts: list[str], target: str = "es", source: str = "auto",
                    timeout: float = 8.0) -> list[str]:
    """Translates several texts in a single request (separated by newlines)."""
    clean = [" ".join(t.split()) for t in texts]
    if not any(clean):
        return clean
    joined = "\n".join(clean)
    translated, detected = _request(joined, target, source, timeout)
    if detected and detected.split("-")[0].lower() == target.split("-")[0].lower():
        return clean  # already in the target language
    parts = [p.strip() for p in translated.split("\n")]
    if len(parts) == len(clean):
        return parts
    log.info("Batch translation did not line up (%d vs %d); translating one by one", len(parts), len(clean))
    return [_request(t, target, source, timeout)[0].strip() if t else "" for t in clean]


def test_translation(target: str = "es") -> str:
    """Used by the settings window: translates a sample sentence, raises TranslateError."""
    global _cooldown_until
    with _lock:
        _cooldown_until = 0.0
    return translate_texts(["The translation is working."], target, "en")[0]
