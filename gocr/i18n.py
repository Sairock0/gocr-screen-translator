"""User interface translations (English / Spanish).

`tr("string.id", **kwargs)` returns the text in the current language. The language is "auto" by
default (Spanish if Windows is in Spanish, English otherwise) and can be changed in Settings.
To add a language, add its code to LANGUAGES and a column to every entry of STRINGS.
"""
from __future__ import annotations

LANGUAGES = ("en", "es")
_lang = "en"


def detect_system_language() -> str:
    try:
        from PySide6.QtCore import QLocale
        name = QLocale.system().name().lower()   # e.g. "es_mx", "en_us"
    except Exception:
        name = ""
    return "es" if name.startswith("es") else "en"


def set_language(code: str) -> None:
    global _lang
    _lang = code if code in LANGUAGES else detect_system_language()


def current_language() -> str:
    return _lang


def tr(string_id: str, /, **kwargs) -> str:
    entry = STRINGS.get(string_id)
    if entry is None:
        return string_id
    text = entry.get(_lang) or entry["en"]
    return text.format(**kwargs) if kwargs else text


def lang_name(code: str) -> str:
    """Display name of a translation language code (Google Translate codes)."""
    entry = LANG_NAMES.get(code)
    if entry is None:
        return code
    return entry[1] if _lang == "es" else entry[0]


LANG_NAMES: dict[str, tuple[str, str]] = {
    "auto": ("Detect automatically", "Detectar automáticamente"),
    "es": ("Spanish", "Español"), "en": ("English", "Inglés"), "pt": ("Portuguese", "Portugués"),
    "fr": ("French", "Francés"), "de": ("German", "Alemán"), "it": ("Italian", "Italiano"),
    "ca": ("Catalan", "Catalán"), "ja": ("Japanese", "Japonés"), "ko": ("Korean", "Coreano"),
    "zh-CN": ("Chinese (Simplified)", "Chino (simplificado)"),
    "zh-TW": ("Chinese (Traditional)", "Chino (tradicional)"),
    "ru": ("Russian", "Ruso"), "uk": ("Ukrainian", "Ucraniano"), "pl": ("Polish", "Polaco"),
    "nl": ("Dutch", "Neerlandés"), "tr": ("Turkish", "Turco"), "ar": ("Arabic", "Árabe"),
    "hi": ("Hindi", "Hindi"), "id": ("Indonesian", "Indonesio"), "vi": ("Vietnamese", "Vietnamita"),
    "th": ("Thai", "Tailandés"),
}

STRINGS: dict[str, dict[str, str]] = {
    # --- app / window
    "app.subtitle": {"en": "On-screen translator", "es": "Traductor en pantalla"},
    "win.minimize": {"en": "Minimize to tray", "es": "Minimizar a la bandeja"},
    "win.close": {"en": "Close (GOCR keeps running in the tray)", "es": "Cerrar (GOCR sigue funcionando en la bandeja)"},
    "win.footer": {"en": "{app} {version} · Changes are saved automatically",
                   "es": "{app} {version} · Los cambios se guardan solos"},
    "theme.dark": {"en": "Dark", "es": "Oscuro"},
    "theme.light": {"en": "Light", "es": "Claro"},
    "theme.tooltip": {"en": "Switch between light and dark mode", "es": "Cambiar entre modo claro y oscuro"},

    # --- tray
    "tray.open": {"en": "Open GOCR", "es": "Abrir GOCR"},
    "tray.pause": {"en": "Pause hotkey", "es": "Pausar atajo"},
    "tray.theme": {"en": "Toggle light/dark mode", "es": "Cambiar modo claro/oscuro"},
    "tray.quit": {"en": "Quit", "es": "Salir"},
    "tray.hint_title": {"en": "GOCR is still running", "es": "GOCR sigue funcionando"},
    "tray.hint_body": {"en": "It is in the system tray (next to the clock). Hold {key} to translate.",
                       "es": "Está en la bandeja del sistema (junto al reloj). Mantén {key} para traducir."},

    # --- status line
    "status.hook_failed": {"en": "Could not enable the global hotkey. Try running GOCR as administrator.",
                           "es": "No se pudo activar el atajo global. Prueba a ejecutar GOCR como administrador."},
    "status.paused": {"en": "Hotkey paused", "es": "Atajo en pausa"},
    "status.release": {"en": "Active — hold «{key}» and release to translate",
                       "es": "Activo — mantén «{key}» y suelta para traducir"},
    "status.live_hold": {"en": "Active — hold «{key}» to translate live",
                         "es": "Activo — mantén «{key}» para traducir en vivo"},
    "status.live_toggle": {"en": "Active — tap «{key}» to turn live translation on/off",
                           "es": "Activo — toca «{key}» para encender/apagar la traducción en vivo"},
    "status.live_on_hold": {"en": "Live mode on — release «{key}» or press Esc to turn it off",
                            "es": "Modo en vivo encendido — suelta «{key}» o pulsa Esc para apagarlo"},
    "status.live_on_toggle": {"en": "Live mode on — tap «{key}» or press Esc to turn it off",
                              "es": "Modo en vivo encendido — toca «{key}» o pulsa Esc para apagarlo"},

    # --- capture area
    "area.reading": {"en": "Reading text…", "es": "Leyendo texto…"},
    "area.translating": {"en": "Translating…", "es": "Traduciendo…"},
    "area.live": {"en": "● Live", "es": "● En vivo"},
    "area.live_offline": {"en": "● Live · can't reach the translator", "es": "● En vivo · no conecta con el traductor"},
    "area.live_rate": {"en": "● Live · Google is limiting requests, wait a moment",
                       "es": "● En vivo · Google limitó las peticiones, espera un momento"},
    "area.live_error": {"en": "● Live · translation error (see the log)", "es": "● En vivo · error al traducir (mira el registro)"},
    "area.ocr_error": {"en": "⚠ OCR error: check the settings", "es": "⚠ Error de OCR: mira los ajustes"},
    "area.preview_screen": {"en": "1920×1080 screen", "es": "pantalla 1920×1080"},

    # --- messages
    "msg.capture_failed": {"en": "Could not capture the screen.", "es": "No se pudo capturar la pantalla."},
    "msg.ocr_error": {"en": "Error reading the text: {error}", "es": "Error al leer el texto: {error}"},
    "msg.no_text": {"en": "No text found in the area", "es": "No se encontró texto en el área"},
    "overlay.original": {"en": "Original: {text}", "es": "Original: {text}"},
    "overlay.copied": {"en": "Translation copied", "es": "Traducción copiada"},

    # --- errors
    "err.rate_limited": {"en": "Google is limiting requests for a moment. Wait a few seconds.",
                         "es": "Google ha limitado las peticiones por un momento. Espera unos segundos."},
    "err.http": {"en": "The translator returned an error ({code}).",
                 "es": "El traductor respondió con un error ({code})."},
    "err.offline": {"en": "Could not reach the translator. Check your internet connection.",
                    "es": "No se pudo conectar con el traductor. Revisa tu conexión a internet."},
    "err.rapid_models": {"en": "The RapidOCR models were not found inside the app.",
                         "es": "No se encuentran los modelos de RapidOCR dentro de la aplicación."},
    "err.rapid_load": {"en": "Could not load RapidOCR: {error}", "es": "No se pudo cargar RapidOCR: {error}"},
    "err.rapid_dict": {"en": "The RapidOCR recognition model has no dictionary.",
                       "es": "El modelo de reconocimiento de RapidOCR no trae diccionario."},
    "err.winocr_missing": {"en": "Windows OCR is not available on this computer. Try the RapidOCR engine in the settings.",
                           "es": "Windows OCR no está disponible en este equipo. Prueba con el motor RapidOCR en los ajustes."},
    "err.winocr_no_lang": {"en": "Windows has no OCR language installed.\nTo add one, open PowerShell as administrator and run:\n{cmd}",
                           "es": "Windows no tiene ningún idioma de OCR instalado.\nPara añadir uno, abre PowerShell como administrador y ejecuta:\n{cmd}"},

    # --- translation mode card
    "mode.title": {"en": "Translation mode", "es": "Modo de traducción"},
    "mode.when": {"en": "When to translate", "es": "Cuándo traducir"},
    "mode.release": {"en": "On release", "es": "Al soltar"},
    "mode.live": {"en": "Live", "es": "En vivo"},
    "mode.activation": {"en": "Live mode activation", "es": "Activación del modo en vivo"},
    "mode.hold": {"en": "Hold", "es": "Mantener"},
    "mode.toggle": {"en": "Tap on/off", "es": "Tocar on/off"},
    "mode.info_release": {
        "en": "Hold the hotkey, aim and release: the text is translated once and the translation stays "
              "until you click it or press Esc.",
        "es": "Mantén el atajo, apunta y suelta: se traduce una vez y la traducción se queda "
              "hasta que hagas clic o pulses Esc."},
    "mode.info_hold": {
        "en": "Like a phone camera translator: while you hold the hotkey, the text inside the area is "
              "translated as you move the mouse. When you release it, the translation disappears.",
        "es": "Como la cámara del traductor del móvil: mientras mantienes el atajo, el texto dentro del área "
              "se va traduciendo solo mientras mueves el mouse. Al soltar, la traducción desaparece."},
    "mode.info_toggle": {
        "en": "Tap the hotkey once to turn live translation on and again (or Esc) to turn it off; turning it "
              "off clears everything. While it is on you can resize the area without holding the hotkey: "
              "wheel = width and height, Alt + wheel = width, Ctrl + wheel = height (while it is on, the "
              "wheel does not reach the game).",
        "es": "Toca el atajo una vez para encender la traducción en vivo y otra vez (o Esc) para apagarla; al "
              "apagarla desaparece todo. Con el modo encendido puedes cambiar el área sin mantener el atajo: "
              "rueda = ancho y alto, Alt + rueda = ancho, Ctrl + rueda = alto (mientras está encendido, la "
              "rueda no llega al juego)."},

    # --- hotkey card
    "hotkey.title": {"en": "Hotkey", "es": "Atajo"},
    "hotkey.subtitle": {"en": "While you hold the hotkey, the area appears around the mouse and you can resize it with the wheel.",
                        "es": "Mientras mantienes el atajo aparece el área alrededor del mouse y puedes cambiarla con la rueda."},
    "hotkey.label": {"en": "Key or mouse button", "es": "Tecla o botón del mouse"},
    "hotkey.hint": {"en": "Click and press a key (F1–F12, letters…) or a side mouse button.",
                    "es": "Haz clic y pulsa una tecla (F1–F12, letras…) o un botón lateral del mouse."},
    "hotkey.enabled": {"en": "Hotkey enabled", "es": "Atajo activado"},
    "hotkey.waiting": {"en": "Press a key…", "es": "Pulsa una tecla…"},
    "hotkey.no_modifiers": {"en": "Not Shift/Ctrl/Alt (used with the wheel)", "es": "Shift/Ctrl/Alt no (sirven para la rueda)"},
    "hotkey.mouse_x1": {"en": "Side mouse button 1 (back)", "es": "Botón lateral 1 (atrás)"},
    "hotkey.mouse_x2": {"en": "Side mouse button 2 (forward)", "es": "Botón lateral 2 (adelante)"},
    "hotkey.mouse_middle": {"en": "Middle mouse button", "es": "Botón central"},
    "tip.wheel": {"en": "Wheel", "es": "Rueda"},
    "tip.wheel_desc": {"en": "width and height", "es": "ancho y alto a la vez"},
    "tip.alt_wheel": {"en": "Alt + wheel", "es": "Alt + rueda"},
    "tip.alt_wheel_desc": {"en": "width", "es": "ancho"},
    "tip.ctrl_wheel": {"en": "Ctrl + wheel", "es": "Ctrl + rueda"},
    "tip.ctrl_wheel_desc": {"en": "height", "es": "alto"},
    "tip.shift_wheel": {"en": "Shift + wheel", "es": "Shift + rueda"},
    "tip.shift_wheel_desc": {"en": "fine adjustment", "es": "ajuste fino"},
    "tip.esc": {"en": "Esc", "es": "Esc"},
    "tip.esc_desc": {"en": "cancel / close", "es": "cancelar / cerrar"},
    "tip.right_click": {"en": "Right-click", "es": "Clic derecho"},
    "tip.right_click_desc": {"en": "copy translation", "es": "copiar traducción"},

    # --- area card
    "area.title": {"en": "Area around the mouse", "es": "Área alrededor del mouse"},
    "area.subtitle": {"en": "Default size. You can also change it with the wheel while aiming.",
                      "es": "Tamaño por defecto. También puedes cambiarlo con la rueda mientras apuntas."},
    "area.width": {"en": "Width", "es": "Ancho"},
    "area.height": {"en": "Height", "es": "Alto"},
    "area.remember": {"en": "Remember the size changed with the wheel", "es": "Recordar el tamaño cambiado con la rueda"},
    "area.remember_hint": {"en": "If off, it always starts with the size above.",
                           "es": "Si está apagado, cada vez empieza con el tamaño de arriba."},

    # --- OCR card
    "ocr.title": {"en": "Text recognition (OCR)", "es": "Reconocimiento de texto (OCR)"},
    "ocr.engine": {"en": "Engine", "es": "Motor"},
    "ocr.engine_hint": {"en": "Windows OCR: very fast. RapidOCR: much better with decorated game fonts (shadows, glow, fiery backgrounds).",
                        "es": "Windows OCR: muy rápido. RapidOCR: lee mucho mejor las letras decoradas de los juegos (con sombra, brillo o fondo con fuego)."},
    "ocr.lang": {"en": "Text language", "es": "Idioma del texto"},
    "ocr.lang_hint": {"en": "OCR languages installed in Windows.", "es": "Idiomas de OCR instalados en Windows."},
    "ocr.info_rapid": {"en": "RapidOCR ships with the app. It reads the Latin alphabet (English, Spanish, French...), "
                             "Cyrillic (Russian, Ukrainian...) and Chinese. "
                             "The first pass takes a bit longer while the models load.",
                       "es": "RapidOCR viene incluido en la app. Lee el alfabeto latino (inglés, español, francés…), "
                             "el cirílico (ruso, ucraniano…) y el chino. "
                             "La primera lectura tarda un poco más mientras se cargan los modelos."},
    "ocr.script": {"en": "Alphabet", "es": "Alfabeto"},
    "ocr.script_hint": {"en": "Automatic recognizes them all. Pick one only if it ever mixes them up.",
                        "es": "Automático los reconoce todos. Elige uno solo si alguna vez los confunde."},
    "ocr.script_auto": {"en": "Automatic", "es": "Automático"},
    "ocr.script_latin": {"en": "Latin and Cyrillic (English, Russian...)", "es": "Latino y cirílico (inglés, ruso…)"},
    "ocr.script_chinese": {"en": "Chinese", "es": "Chino"},
    "ocr.info_none": {"en": "No Windows OCR languages were found. To add English, open PowerShell as administrator "
                            "and run:\n{cmd}\n…or use RapidOCR.",
                      "es": "No se encontraron idiomas de OCR de Windows. Para añadir inglés, abre PowerShell "
                            "como administrador y ejecuta:\n{cmd}\n…o usa RapidOCR."},
    "ocr.info_missing": {"en": "⚠ The selected language is not installed. For English, run in PowerShell (admin):\n{cmd}",
                         "es": "⚠ El idioma elegido no está instalado. Para inglés ejecuta en PowerShell (admin):\n{cmd}"},
    "ocr.info_windows": {"en": "Missing a language? Windows Settings › Time & language › Language › Add a language (includes OCR).",
                         "es": "¿Falta un idioma? Configuración de Windows › Hora e idioma › Idioma › Agregar un idioma (incluye el OCR)."},

    # --- translation card
    "tr.title": {"en": "Translation", "es": "Traducción"},
    "tr.subtitle": {"en": "Free Google Translate. Requires an internet connection.",
                    "es": "Google Translate gratuito. Necesita conexión a internet."},
    "tr.target": {"en": "Translate to", "es": "Traducir a"},
    "tr.source": {"en": "Original language", "es": "Idioma original"},
    "tr.test_label": {"en": "Check that translation works", "es": "Comprobar que la traducción funciona"},
    "tr.test": {"en": "Test", "es": "Probar"},
    "tr.testing": {"en": "Testing…", "es": "Probando…"},
    "tr.test_ok": {"en": "It works: «{text}»", "es": "Funciona: «{text}»"},
    "tr.test_log": {"en": "Details in %APPDATA%\\GOCR\\gocr.log", "es": "Detalles en %APPDATA%\\GOCR\\gocr.log"},

    # --- overlay card
    "ov.title": {"en": "On-screen translation", "es": "Traducción en pantalla"},
    "ov.subtitle": {"en": "Drawn on top of the original text. Click it to close it.",
                    "es": "Se dibuja encima del texto original. Clic para cerrarla."},
    "ov.style": {"en": "Style", "es": "Estilo"},
    "ov.style_auto": {"en": "Game colors", "es": "Colores del juego"},
    "ov.style_theme": {"en": "App colors", "es": "Colores de la app"},
    "ov.style_hint": {"en": "«Game colors» imitates the background of the original text.",
                      "es": "«Colores del juego» imita el fondo del texto original."},
    "ov.opacity": {"en": "Background opacity", "es": "Opacidad del fondo"},
    "ov.autohide": {"en": "Hide automatically", "es": "Ocultar automáticamente"},
    "ov.never": {"en": "Never (click or Esc)", "es": "Nunca (clic o Esc)"},
    "ov.seconds": {"en": "{n} seconds", "es": "{n} segundos"},
    "ov.tooltip": {"en": "Show the original text on hover", "es": "Ver el texto original al pasar el mouse"},

    # --- general card
    "gen.title": {"en": "General", "es": "General"},
    "gen.lang": {"en": "Interface language", "es": "Idioma de la interfaz"},
    "gen.lang_auto": {"en": "Automatic (Windows)", "es": "Automático (Windows)"},
    "gen.startup": {"en": "Start with Windows", "es": "Iniciar con Windows"},
    "gen.minimized": {"en": "Start minimized to the tray", "es": "Abrir minimizado en la bandeja"},
    "gen.minimized_hint": {"en": "The app sits next to the clock, like Discord or Steam.",
                           "es": "La app queda junto al reloj, como Discord o Steam."},
}
