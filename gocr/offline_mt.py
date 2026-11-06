"""Offline translation with OPUS-MT models (CTranslate2 + SentencePiece).

The models (about 75-80 MB each, one per language pair) are published as assets of the
"models-v1" release of the GOCR repository. They are downloaded the first time a pair is
needed and kept in %APPDATA%\\GOCR\\translation-models. When there is no direct model for a
pair (for example Chinese -> Spanish), the text goes through English with two models.

Models: OPUS-MT by Helsinki-NLP (University of Helsinki), CC-BY 4.0.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

from gocr.config import app_data_dir

log = logging.getLogger(__name__)

RELEASE_URL = "https://github.com/Sairock0/gocr-screen-translator/releases/download/models-v1/"

# Language pairs published in models-v1 (pair -> zip size in bytes). Copied from manifest.json.
PAIRS: dict[str, int] = {
    "ar-en": 67346568, "de-en": 66515681, "de-es": 67101923, "en-de": 62909658, "en-es": 68612252,
    "en-fr": 62398609, "en-it": 69747083, "en-ru": 69621359, "es-en": 67781008, "fr-en": 63479063,
    "fr-es": 64463438, "id-en": 68146990, "it-en": 69535233, "it-es": 65138186, "ja-en": 64737593,
    "ja-es": 65854592, "ko-en": 68211181, "ko-es": 68220766, "nl-en": 66882919, "pl-en": 69714551,
    "ru-en": 67524408, "ru-es": 70132076, "th-en": 68158299, "tr-en": 69602515, "uk-en": 65903013,
    "vi-en": 62188240, "zh-en": 70735085,
}

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…。！？])\s+")
_CYRILLIC = re.compile(r"[Ѐ-ӿ]")
_UKRAINIAN = re.compile(r"[іїєґІЇЄҐ]")
_KANA = re.compile(r"[぀-ヿ]")
_HANGUL = re.compile(r"[가-힯]")
_HAN = re.compile(r"[㐀-鿿]")
_ARABIC = re.compile(r"[؀-ۿ]")
_THAI = re.compile(r"[฀-๿]")
_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)

# The most frequent short words of each Latin-alphabet language (to tell them apart).
_STOPWORDS = {
    "en": "the of and to a in is you that it for on with are be this your have not was can at or as all by from will we an they my",
    "es": "el la de que y en los se del las un por con una para es su al lo como más pero sus le ya o este sí porque esta entre cuando muy sin sobre hola cómo qué está estás eres soy",
    "pt": "o a de que e do da em um para é com não uma os no se na por mais as dos como mas foi ao ele das tem à seu sua ou",
    "fr": "le la de et les des en un du une est que pour qui dans pas au sur ne se plus par avec ce il vous nous je",
    "de": "der die und in den von zu das mit sich des auf für ist im dem nicht ein eine als auch es an werden aus er hat dass sie",
    "it": "il di che la e un a per non in una sono mi ho lo ma se gli le con del della ti si da io questo",
    "nl": "de het een en van ik te dat die in is niet je zijn op aan met als voor er maar om",
    "pl": "nie i w się na że z do to jest jak co ale po tak za od już mnie jego",
    "tr": "bir ve bu da de için ne ile çok ben o mi daha gibi var değil",
    "id": "yang dan di itu dengan untuk tidak ini dari dalam akan pada juga saya ke",
    "vi": "của và các có là được trong cho một những không với người này đã",
}
_STOP_SETS = {lang: set(words.split()) for lang, words in _STOPWORDS.items()}


class Unavailable(Exception):
    """The pair has no offline model, or its model is still downloading."""


# --------------------------------------------------------------------------- languages
def detect_language(text: str) -> str:
    """Cheap language guess from the alphabet (and frequent words for the Latin alphabet)."""
    if _KANA.search(text):
        return "ja"
    if _HANGUL.search(text):
        return "ko"
    if _HAN.search(text):
        return "zh"
    if _CYRILLIC.search(text):
        return "uk" if _UKRAINIAN.search(text) else "ru"
    if _ARABIC.search(text):
        return "ar"
    if _THAI.search(text):
        return "th"
    words = [w.lower() for w in _WORD.findall(text)]
    best, best_hits = "en", 0
    for lang, stop in _STOP_SETS.items():
        hits = sum(1 for w in words if w in stop)
        if hits > best_hits:
            best, best_hits = lang, hits
    if best_hits == 0:
        return "en"   # games are mostly in English; menus rarely contain frequent words
    return best


def _base(code: str) -> str:
    return (code or "").split("-")[0].lower()


def route(source: str, target: str) -> list[str] | None:
    """Models to chain for source -> target ([] = nothing to do, None = not possible offline)."""
    s, t = _base(source), _base(target)
    if s == t:
        return []
    if f"{s}-{t}" in PAIRS:
        return [f"{s}-{t}"]
    if f"{s}-en" in PAIRS and f"en-{t}" in PAIRS:
        return [f"{s}-en", f"en-{t}"]
    return None


def target_supported(target: str) -> bool:
    t = _base(target)
    return t == "en" or f"en-{t}" in PAIRS


# --------------------------------------------------------------------------- storage
def models_dir() -> Path:
    path = app_data_dir() / "translation-models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _model_path(pair: str) -> Path:
    return models_dir() / f"opus-mt-{pair}"


def is_installed(pair: str) -> bool:
    p = _model_path(pair)
    return (p / "model.bin").exists() and (p / "source.spm").exists() and (p / "target.spm").exists()


def installed_pairs() -> list[str]:
    return sorted(p for p in PAIRS if is_installed(p))


def installed_size() -> int:
    total = 0
    for root, _dirs, files in os.walk(models_dir()):
        total += sum(os.path.getsize(os.path.join(root, f)) for f in files)
    return total


# --------------------------------------------------------------------------- downloads
class _Downloads:
    """Downloads models one at a time in a background thread."""

    def __init__(self):
        self.lock = threading.Lock()
        self.queue: list[str] = []
        self.current: str | None = None
        self.progress = 0.0           # 0..1 of the current download
        self.failed: dict[str, float] = {}   # pair -> time of the last failure
        self.listener = None          # callable(pair | None, progress, error | None)
        self.thread: threading.Thread | None = None

    def request(self, pairs: list[str]) -> None:
        with self.lock:
            now = time.monotonic()
            for p in pairs:
                if p in PAIRS and not is_installed(p) and p != self.current and p not in self.queue \
                        and now - self.failed.get(p, -1e9) > 60:
                    self.queue.append(p)
            if self.queue and (self.thread is None or not self.thread.is_alive()):
                self.thread = threading.Thread(target=self._run, name="gocr-model-download", daemon=True)
                self.thread.start()

    def busy(self) -> bool:
        with self.lock:
            return self.current is not None or bool(self.queue)

    def _notify(self, pair, progress, error=None):
        fn = self.listener
        if fn:
            try:
                fn(pair, progress, error)
            except Exception:  # noqa: BLE001 - never break a download because of the UI
                log.exception("Download listener failed")

    def _run(self):
        while True:
            with self.lock:
                if not self.queue:
                    self.current = None
                    break
                pair = self.current = self.queue.pop(0)
                self.progress = 0.0
            try:
                self._download(pair)
                log.info("Offline model %s installed", pair)
                self._notify(pair, 1.0)
            except Exception as exc:  # noqa: BLE001
                log.warning("Could not download offline model %s: %r", pair, exc)
                with self.lock:
                    self.failed[pair] = time.monotonic()
                self._notify(pair, 0.0, str(exc))
        self._notify(None, 1.0)

    def _download(self, pair: str) -> None:
        name = f"opus-mt-{pair}"
        url = RELEASE_URL + name + ".zip"
        tmp_zip = models_dir() / f"{name}.zip.part"
        tmp_dir = models_dir() / f"{name}.tmp"
        req = urllib.request.Request(url, headers={"User-Agent": "GOCR"})
        with urllib.request.urlopen(req, timeout=30) as resp, open(tmp_zip, "wb") as fh:
            total = int(resp.headers.get("Content-Length") or PAIRS.get(pair) or 0)
            done, last = 0, 0.0
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
                if total:
                    self.progress = min(done / total, 1.0)
                    if self.progress - last >= 0.02:
                        last = self.progress
                        self._notify(pair, self.progress)
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
        with zipfile.ZipFile(tmp_zip) as zf:
            for member in zf.namelist():   # flat archive: refuse anything with a path
                if "/" in member or "\\" in member or member.startswith("."):
                    raise ValueError(f"unexpected file in archive: {member}")
            zf.extractall(tmp_dir)
        tmp_zip.unlink(missing_ok=True)
        final = _model_path(pair)
        if final.exists():
            shutil.rmtree(final, ignore_errors=True)
        tmp_dir.rename(final)


downloads = _Downloads()


# --------------------------------------------------------------------------- translation
class _Model:
    def __init__(self, pair: str):
        import ctranslate2
        import sentencepiece as spm

        path = _model_path(pair)
        t0 = time.perf_counter()
        threads = max(1, min(4, (os.cpu_count() or 2) // 2))
        self.translator = ctranslate2.Translator(str(path), device="cpu", compute_type="int8",
                                                 inter_threads=1, intra_threads=threads)
        self.src = spm.SentencePieceProcessor(model_file=str(path / "source.spm"))
        self.tgt = spm.SentencePieceProcessor(model_file=str(path / "target.spm"))
        log.info("Offline model %s loaded in %.0f ms (%d threads)", pair, (time.perf_counter() - t0) * 1000, threads)

    def translate(self, sentences: list[str]) -> list[str]:
        # Marian models need the end-of-sentence token, otherwise they repeat themselves
        tokens = [self.src.encode(s, out_type=str) + ["</s>"] for s in sentences]
        longest = max((len(t) for t in tokens), default=1)
        results = self.translator.translate_batch(
            tokens, beam_size=2, max_batch_size=16,
            max_decoding_length=min(512, int(longest * 2.2) + 10))
        return [self.tgt.decode(r.hypotheses[0]) for r in results]


_models: dict[str, _Model] = {}
_models_lock = threading.Lock()


def _get_model(pair: str) -> _Model:
    with _models_lock:
        m = _models.get(pair)
        if m is None:
            m = _models[pair] = _Model(pair)
        return m


def _shout(text: str) -> bool:
    letters = _LETTER.findall(text)
    return len(letters) >= 4 and sum(1 for c in letters if c.isupper()) / len(letters) > 0.8


def _sentence_case(text: str) -> str:
    low = text.lower()
    out, cap = [], True
    for ch in low:
        if cap and ch.isalpha():
            out.append(ch.upper())
            cap = False
        else:
            out.append(ch)
        if ch in ".!?…":
            cap = True
    return "".join(out)


def _translate_one_lang(texts: list[str], chain: list[str]) -> list[str]:
    """Translates texts of one source language through a chain of models."""
    shout = [_shout(t) for t in texts]
    current = [_sentence_case(t) if s else t for t, s in zip(texts, shout)]
    for pair in chain:
        model = _get_model(pair)
        pieces, owners = [], []
        for i, t in enumerate(current):
            for sentence in _SENTENCE_SPLIT.split(t.strip()) if t.strip() else []:
                pieces.append(sentence)
                owners.append(i)
        out = model.translate(pieces) if pieces else []
        joined = [[] for _ in current]
        for i, s in zip(owners, out):
            joined[i].append(s.strip())
        current = [" ".join(parts) for parts in joined]
    return [c.upper() if s else c for c, s in zip(current, shout)]


def translate_texts(texts: list[str], target: str, source: str = "auto") -> list[str]:
    """Translates offline. Raises Unavailable when a needed model is missing (and starts
    downloading it) or when the pair cannot be translated offline."""
    langs = [(_base(source) if source and source != "auto" else detect_language(t)) for t in texts]
    plans: dict[str, list[str] | None] = {lang: route(lang, target) for lang in set(langs)}
    impossible = [lang for lang, chain in plans.items() if chain is None]
    if impossible:
        raise Unavailable(f"no offline model for {','.join(sorted(impossible))} -> {target}")
    missing = sorted({p for chain in plans.values() for p in chain if not is_installed(p)})
    if missing:
        downloads.request(missing)
        raise Unavailable(f"downloading {', '.join(missing)}")
    result = list(texts)
    for lang, chain in plans.items():
        idx = [i for i, l in enumerate(langs) if l == lang and texts[i].strip()]
        if not idx or not chain:
            continue
        out = _translate_one_lang([texts[i] for i in idx], chain)
        for i, t in zip(idx, out):
            result[i] = t
    return result
