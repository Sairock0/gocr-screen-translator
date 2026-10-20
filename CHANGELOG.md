# Changelog

## 1.5.0
- Everything in English: code, comments, logs, docs and scripts.
- Bilingual interface (English / Spanish) with a language selector; "Automatic" follows the Windows language.
- MIT license, third-party notices and a GitHub Actions build that publishes releases.

## 1.4.0
- Word-level selection: a small area translates only the words inside it; an area covering a whole line translates the whole paragraph.
- Fixed the area drifting away from the mouse on a second monitor (mixed scaling).

## 1.3.x
- Splits words glued together by OCR ("EXITGAME" -> "EXIT GAME"), tolerating unknown names and one misread letter.
- Adds the missing space after periods ("US.SURPRISE" -> "US. SURPRISE").
- New wheel controls: wheel = width and height, Alt = width, Ctrl = height, Shift = fine.
- The mouse wheel no longer changes combo boxes while scrolling the settings window.
- Whole paragraphs are translated even if the area only covers one of their lines.

## 1.2.x
- Live mode reuses previous OCR passes and translations: no re-translating when the mouse moves a little.
- Live mode with on/off: resize the area without holding the hotkey.
- Win+Shift+S / Print Screen include the translation; live mode pauses while snipping.
- Turning live mode off clears everything.

## 1.1.0
- Live mode (like a phone camera translator).
- The frame is never captured by the OCR; wider capture so words are not cut at the edges.

## 1.0.0
- First version: hold a hotkey, aim, release, and the translation is drawn over the original text.
