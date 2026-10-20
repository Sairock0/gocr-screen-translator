# -*- mode: python ; coding: utf-8 -*-
# PyInstaller recipe: builds dist\GOCR\GOCR.exe (portable folder, fast startup).
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules("winrt") + ["gocr.ocr.windows_ocr", "gocr.ocr.rapid_ocr"]

a = Analysis(
    ["run.py"],
    pathex=["."],
    datas=[
        ("gocr/models/det.onnx", "gocr/models"),
        ("gocr/models/rec.onnx", "gocr/models"),
        ("gocr/data/english_words.txt.gz", "gocr/data"),
        ("assets/icon.png", "assets"),
        ("assets/icon.ico", "assets"),
        ("assets/chevron_dark.png", "assets"),
        ("assets/chevron_light.png", "assets"),
        ("LICENSE", "."),
        ("THIRD_PARTY_NOTICES.md", "."),
    ],
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtPdf",
              "PySide6.QtWebEngineCore", "PySide6.QtMultimedia", "PySide6.Qt3DCore"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GOCR",
    icon="assets/icon.ico",
    console=False,
    upx=False,
    version=None,
)

coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="GOCR")
