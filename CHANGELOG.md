# Changelog

## 1.6.0
- License changed to GNU GPL v3.0 or later.
- RapidOCR now reads Cyrillic (Russian, Ukrainian, Belarusian, Bulgarian, Serbian...) with a bundled PP-OCRv5 model.
- The same model reads the Latin alphabet with correct spaces between words (`EXITGAME` now comes out as `EXIT GAME` directly).
- New "Alphabet" option for RapidOCR: Automatic (default), Latin and Cyrillic, or Chinese. In Automatic mode, lines that the Latin/Cyrillic model cannot read are read again with the Chinese model.

## 1.5.2
- Translation is more robust: if one Google endpoint fails, two others are tried, and the one that works is remembered.
- After all endpoints fail, requests pause for a few seconds so a temporary block can lift.
- The real cause of every translation failure is written to the log.
- Clearer live-mode messages (can't reach the translator / Google is limiting requests).
- New "Test" button in Settings › Translation.

## 1.5.1
- Only the text inside the area is translated: lines outside the frame are no longer added to complete the paragraph.
- A line counts when at least half of its height is inside the area.

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
