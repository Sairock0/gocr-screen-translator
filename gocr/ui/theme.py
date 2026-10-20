"""Light and dark palettes and the settings window stylesheet."""
from __future__ import annotations

from PySide6.QtGui import QColor

from gocr.config import resource_path

PALETTES = {
    "dark": {
        "bg": "#14161b", "surface": "#1c1f26", "surface2": "#252a33", "hover": "#2d333e",
        "border": "#2f3541", "text": "#e9ecf2", "muted": "#9199a8", "accent": "#3ed1b8",
        "accent_hover": "#5fe0ca", "on_accent": "#06231e", "danger": "#ff6b6b", "warn": "#f5b94a",
        "ok": "#3ed1b8", "shadow": "#000000",
    },
    "light": {
        "bg": "#eef1f5", "surface": "#ffffff", "surface2": "#f1f3f7", "hover": "#e6eaf0",
        "border": "#dbe0e8", "text": "#181b21", "muted": "#5d6574", "accent": "#0b9f87",
        "accent_hover": "#0a8a75", "on_accent": "#ffffff", "danger": "#d64545", "warn": "#b97a0a",
        "ok": "#0b9f87", "shadow": "#8a94a6",
    },
}


def color(theme: str, key: str) -> QColor:
    return QColor(PALETTES[theme][key])


def stylesheet(theme: str) -> str:
    p = PALETTES[theme]
    chevron = resource_path("assets", f"chevron_{theme}.png").as_posix()
    return f"""
    * {{ font-family: "Segoe UI Variable Text", "Segoe UI", "Inter", sans-serif; font-size: 13px; color: {p['text']}; }}
    #Root {{ background: {p['bg']}; border: 1px solid {p['border']}; border-radius: 12px; }}
    #TitleBar {{ background: transparent; }}
    #AppName {{ font-size: 15px; font-weight: 700; }}
    #AppSub {{ color: {p['muted']}; font-size: 12px; }}
    QScrollArea, #ScrollBody {{ background: transparent; border: none; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px 4px 0; }}
    QScrollBar::handle:vertical {{ background: {p['border']}; border-radius: 4px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {p['muted']}; }}
    QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ height: 0; background: none; }}

    #Card {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 10px; }}
    #CardTitle {{ font-size: 14px; font-weight: 650; }}
    #CardIcon {{ color: {p['accent']}; font-family: "Segoe Fluent Icons", "Segoe MDL2 Assets"; font-size: 16px; }}
    #Muted, QLabel[muted="true"] {{ color: {p['muted']}; font-size: 12px; }}
    #Status {{ font-size: 12px; }}

    QPushButton {{ background: {p['surface2']}; border: 1px solid {p['border']}; border-radius: 7px; padding: 6px 12px; }}
    QPushButton:hover {{ background: {p['hover']}; }}
    QPushButton:pressed {{ background: {p['border']}; }}
    QPushButton#Primary {{ background: {p['accent']}; color: {p['on_accent']}; border: none; font-weight: 600; }}
    QPushButton#Primary:hover {{ background: {p['accent_hover']}; }}
    QPushButton#Hotkey {{ font-size: 15px; font-weight: 700; min-width: 130px; padding: 8px 14px;
                          border: 1px solid {p['accent']}; color: {p['accent']}; background: {p['surface2']}; }}
    QPushButton#Hotkey[capturing="true"] {{ background: {p['accent']}; color: {p['on_accent']}; }}
    QPushButton#TitleBtn {{ background: transparent; border: none; border-radius: 7px; min-width: 34px; max-width: 34px;
                            min-height: 30px; max-height: 30px; padding: 0;
                            font-family: "Segoe Fluent Icons", "Segoe MDL2 Assets"; font-size: 12px; }}
    QPushButton#TitleBtn:hover {{ background: {p['hover']}; }}
    QPushButton#CloseBtn {{ background: transparent; border: none; border-radius: 7px; min-width: 34px; max-width: 34px;
                            min-height: 30px; max-height: 30px; padding: 0;
                            font-family: "Segoe Fluent Icons", "Segoe MDL2 Assets"; font-size: 12px; }}
    QPushButton#CloseBtn:hover {{ background: #e5484d; color: white; }}
    QPushButton#ThemeBtn {{ background: {p['surface2']}; border: 1px solid {p['border']}; border-radius: 15px;
                            min-height: 28px; max-height: 28px; padding: 0 12px 0 10px; font-size: 12px; font-weight: 600; }}
    QPushButton#ThemeBtn:hover {{ background: {p['hover']}; }}
    QPushButton#Seg {{ background: transparent; border: none; border-radius: 6px; padding: 6px 14px; color: {p['muted']}; font-weight: 600; }}
    QPushButton#Seg:checked {{ background: {p['surface']}; color: {p['text']}; border: 1px solid {p['border']}; }}
    #SegWrap {{ background: {p['surface2']}; border: 1px solid {p['border']}; border-radius: 8px; }}

    QComboBox, QSpinBox {{ background: {p['surface2']}; border: 1px solid {p['border']}; border-radius: 7px; padding: 5px 10px; min-height: 20px; }}
    QComboBox:hover, QSpinBox:hover {{ border-color: {p['accent']}; }}
    QComboBox::drop-down {{ border: none; width: 26px; }}
    QComboBox::down-arrow {{ image: url("{chevron}"); width: 10px; height: 10px; }}
    QComboBox QAbstractItemView {{ background: {p['surface']}; border: 1px solid {p['border']}; selection-background-color: {p['accent']};
                                   selection-color: {p['on_accent']}; outline: none; padding: 4px; }}
    QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}

    QSlider::groove:horizontal {{ height: 4px; background: {p['border']}; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {p['accent']}; border-radius: 2px; }}
    QSlider::handle:horizontal {{ background: {p['accent']}; width: 16px; height: 16px; margin: -6px 0; border-radius: 8px;
                                  border: 3px solid {p['surface']}; }}

    #Chip {{ background: {p['surface2']}; border: 1px solid {p['border']}; border-radius: 6px; padding: 3px 8px; font-size: 12px; }}
    #Kbd {{ color: {p['accent']}; font-weight: 700; font-size: 12px; }}
    QToolTip {{ background: {p['surface']}; color: {p['text']}; border: 1px solid {p['border']}; padding: 6px; border-radius: 6px; }}
    QMenu {{ background: {p['surface']}; border: 1px solid {p['border']}; padding: 6px; border-radius: 8px; }}
    QMenu::item {{ padding: 7px 22px 7px 14px; border-radius: 5px; }}
    QMenu::item:selected {{ background: {p['hover']}; }}
    QMenu::separator {{ height: 1px; background: {p['border']}; margin: 5px 8px; }}
    """
