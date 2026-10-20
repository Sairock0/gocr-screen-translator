"""Persistent settings (JSON in %APPDATA%\\GOCR) and resource paths."""
from __future__ import annotations

import copy
import json
import logging
import os
import sys
from pathlib import Path

from gocr import APP_NAME

log = logging.getLogger(__name__)

# Capture area limits (physical screen pixels)
AREA_MIN_W, AREA_MAX_W = 60, 2400
AREA_MIN_H, AREA_MAX_H = 24, 1400

DEFAULTS: dict = {
    "ui_lang": "auto",                    # "auto" (follows Windows) | "en" | "es"
    "theme": "dark",                      # "dark" | "light"
    "hotkey": {"kind": "key", "code": 0x77, "name": "F8"},  # kind: key | mouse
    "hotkey_enabled": True,
    "area_w": 460,
    "area_h": 150,
    "remember_size": True,                # keep the size changed with the mouse wheel
    "translate_mode": "release",          # "release" | "live"
    "live_activation": "hold",            # live mode: "hold" | "toggle"
    "ocr_engine": "windows",              # "windows" | "rapid"
    "ocr_lang": "en-US",                  # text language for Windows OCR
    "source_lang": "auto",
    "target_lang": "es",
    "overlay_style": "auto",              # "auto" (game colors) | "theme"
    "overlay_opacity": 1.0,
    "overlay_auto_hide": 0,               # seconds, 0 = never
    "show_original_tooltip": True,
    "start_with_windows": False,
    "start_minimized": True,
    "tray_hint_shown": False,
}


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def resource_path(*parts: str) -> Path:
    """Path to a bundled resource (works from source and from a PyInstaller build)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).resolve().parent.parent
    return base.joinpath(*parts)


class Settings:
    def __init__(self, path: Path | None = None):
        self.path = path or (app_data_dir() / "settings.json")
        self.data: dict = copy.deepcopy(DEFAULTS)
        self.is_first_run = not self.path.exists()
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            stored = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(stored, dict):
                for key, value in stored.items():
                    if key in DEFAULTS:
                        self.data[key] = value
        except Exception:  # corrupted file: ignore it and use the defaults
            log.exception("Could not read the settings; using defaults")
        self._sanitize()

    def _sanitize(self) -> None:
        d = self.data
        d["area_w"] = int(min(max(int(d.get("area_w", 460)), AREA_MIN_W), AREA_MAX_W))
        d["area_h"] = int(min(max(int(d.get("area_h", 150)), AREA_MIN_H), AREA_MAX_H))
        choices = {
            "ui_lang": ("auto", "en", "es"),
            "theme": ("dark", "light"),
            "translate_mode": ("release", "live"),
            "live_activation": ("hold", "toggle"),
            "ocr_engine": ("windows", "rapid"),
        }
        for key, allowed in choices.items():
            if d.get(key) not in allowed:
                d[key] = DEFAULTS[key]
        hk = d.get("hotkey")
        if not isinstance(hk, dict) or hk.get("kind") not in ("key", "mouse") or not hk.get("code"):
            d["hotkey"] = copy.deepcopy(DEFAULTS["hotkey"])

    def save(self) -> None:
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)
        except Exception:
            log.exception("Could not save the settings")

    def __getitem__(self, key: str):
        return self.data[key]

    def __setitem__(self, key: str, value) -> None:
        self.data[key] = value

    def get(self, key: str, default=None):
        return self.data.get(key, default)
