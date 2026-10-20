"""Translation through the free Google Translate endpoint (no API key)."""
from __future__ import annotations

import json
import logging
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

_URL = "https://translate.googleapis.com/translate_a/single"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/129.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
}


class TranslateError(Exception):
    pass


def _request(text: str, target: str, source: str, timeout: float) -> tuple[str, str]:
    params = {"client": "gtx", "sl": source or "auto", "tl": target, "dt": "t", "q": text}
    data = urllib.parse.urlencode(params)
    try:
        if len(data) < 6000:
            req = urllib.request.Request(f"{_URL}?{data}", headers=_HEADERS)
        else:  # long texts go by POST
            req = urllib.request.Request(_URL, data=data.encode("utf-8"), headers={
                **_HEADERS, "Content-Type": "application/x-www-form-urlencoded;charset=utf-8"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise TranslateError(tr("err.rate_limited")) from exc
        raise TranslateError(tr("err.http", code=exc.code)) from exc
    except Exception as exc:
        raise TranslateError(tr("err.offline")) from exc
    return parse_response(payload)


def parse_response(payload: str) -> tuple[str, str]:
    """Returns (translated text, detected language)."""
    data = json.loads(payload)
    segments = data[0] or []
    out = "".join(seg[0] for seg in segments if seg and isinstance(seg[0], str))
    detected = data[2] if len(data) > 2 and isinstance(data[2], str) else ""
    return out, detected


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
