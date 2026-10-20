"""OCR engine built into Windows 10/11 (Windows.Media.Ocr) through pywinrt.

Nothing to install: it uses Windows language packs. If the text language is missing
(e.g. English on a Spanish Windows) it can be added from
Settings > Time & language > Language, or with PowerShell (as administrator):
    Add-WindowsCapability -Online -Name "Language.OCR~~~en-US~0.0.1.0"
"""
from __future__ import annotations

import asyncio
import logging

import cv2
import numpy as np

from gocr.i18n import tr
from gocr.ocr import OcrError, OcrLine, upscale_factor

log = logging.getLogger(__name__)

INSTALL_CMD = 'Add-WindowsCapability -Online -Name "Language.OCR~~~{tag}~0.0.1.0"'



def _winrt():
    try:
        from winrt.windows.globalization import Language
        from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.storage.streams import DataWriter
        import winrt.windows.foundation  # noqa: F401  (needed for await)
        import winrt.windows.foundation.collections  # noqa: F401
    except Exception as exc:  # pragma: no cover - Windows only
        raise OcrError(tr("err.winocr_missing")) from exc

    return Language, BitmapPixelFormat, SoftwareBitmap, OcrEngine, DataWriter


def init_thread() -> None:
    """Initializes COM (MTA) on the OCR thread."""
    try:
        from winrt.runtime import ApartmentType, init_apartment
        init_apartment(ApartmentType.MULTI_THREADED)
    except Exception:
        pass  # already initialized or unavailable


def available_languages() -> list[tuple[str, str]]:
    """OCR languages installed in Windows: [(tag, display name)]."""
    try:
        Language, _bpf, _sb, OcrEngine, _dw = _winrt()
        return [(lang.language_tag, lang.display_name) for lang in OcrEngine.available_recognizer_languages]
    except Exception:
        return []


async def _await(op):
    return await op


class WindowsOcr:
    name = "windows"

    def __init__(self, lang_tag: str):
        Language, self._BPF, self._SB, OcrEngine, self._DataWriter = _winrt()
        engine = None
        if lang_tag:
            try:
                lang = Language(lang_tag)
                if OcrEngine.is_language_supported(lang):
                    engine = OcrEngine.try_create_from_language(lang)
            except Exception:
                log.exception("Invalid OCR language: %s", lang_tag)
        if engine is None:
            engine = OcrEngine.try_create_from_user_profile_languages()
            if engine is not None and lang_tag:
                log.warning("Language %s is not installed; using %s", lang_tag,
                            engine.recognizer_language.language_tag)
        if engine is None:
            raise OcrError(tr("err.winocr_no_lang", cmd=INSTALL_CMD.format(tag=lang_tag or "en-US")))

        self._engine = engine
        self.lang = engine.recognizer_language.language_tag
        self._no_spaces = self.lang.lower().startswith(("ja", "zh"))
        try:
            self._max_dim = int(OcrEngine.max_image_dimension)
        except Exception:
            self._max_dim = 2600

    def recognize(self, img_bgra: np.ndarray) -> list[OcrLine]:
        h, w = img_bgra.shape[:2]
        scale = upscale_factor(w, h, min(1800, self._max_dim))
        if scale > 1.0:
            img_bgra = cv2.resize(img_bgra, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)
        rgba = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2RGBA)
        hh, ww = rgba.shape[:2]
        writer = self._DataWriter()
        writer.write_bytes(rgba.tobytes())
        bitmap = self._SB.create_copy_from_buffer(writer.detach_buffer(), self._BPF.RGBA8, ww, hh)
        result = asyncio.run(_await(self._engine.recognize_async(bitmap)))

        lines: list[OcrLine] = []
        for line in result.lines:
            words = list(line.words)
            if not words:
                continue
            rects = [wd.bounding_rect for wd in words]
            x0 = min(r.x for r in rects)
            y0 = min(r.y for r in rects)
            x1 = max(r.x + r.width for r in rects)
            y1 = max(r.y + r.height for r in rects)
            text = "".join(wd.text for wd in words) if self._no_spaces else line.text
            wboxes = [(wd.text, int(r.x / scale), int(r.y / scale), max(1, int(r.width / scale)),
                       max(1, int(r.height / scale))) for wd, r in zip(words, rects)]
            lines.append(OcrLine(text=text,
                                 x=int(x0 / scale), y=int(y0 / scale),
                                 w=max(1, int((x1 - x0) / scale)), h=max(1, int((y1 - y0) / scale)),
                                 words=None if self._no_spaces else wboxes))
        return lines
