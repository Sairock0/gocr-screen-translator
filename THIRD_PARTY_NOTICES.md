# Third-party notices

GOCR is released under the GNU General Public License v3.0 or later (see `LICENSE`). It bundles or depends on the following
third-party components, each under its own license:

| Component | Used for | License |
|---|---|---|
| [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) PP-OCRv4 models (`gocr/models/det.onnx`, `gocr/models/rec.onnx`) and PP-OCRv5 Cyrillic model (`gocr/models/rec_latin_cyrillic.onnx`), ONNX versions distributed by [RapidOCR](https://github.com/RapidAI/RapidOCR) | RapidOCR engine | Apache-2.0 |
| [wordninja](https://github.com/keredson/wordninja) word list (`gocr/data/english_words.txt.gz`) and splitting algorithm | Splitting glued words | MIT |
| [Qt for Python / PySide6](https://doc.qt.io/qtforpython/) | User interface | LGPL-3.0 |
| [ONNX Runtime](https://github.com/microsoft/onnxruntime) (`onnxruntime-directml` on Windows, includes [DirectML](https://github.com/microsoft/DirectML)) | RapidOCR inference on the processor or the graphics card | MIT |
| [OPUS-MT](https://github.com/Helsinki-NLP/Opus-MT) translation models by Helsinki-NLP (University of Helsinki), converted to CTranslate2 and downloaded on demand from the `models-v1` release | Offline translator | CC-BY-4.0 |
| [CTranslate2](https://github.com/OpenNMT/CTranslate2) | Offline translator inference | MIT |
| [SentencePiece](https://github.com/google/sentencepiece) | Offline translator tokenization | Apache-2.0 |
| [py3langid](https://github.com/adbar/py3langid) (fork of langid.py) | Detecting the language of the text | BSD-3-Clause |
| [OpenCV](https://opencv.org/) (`opencv-python-headless`) | Image processing | Apache-2.0 |
| [NumPy](https://numpy.org/) | Arrays | BSD-3-Clause |
| [python-mss](https://github.com/BoboTiG/python-mss) | Screen capture | MIT |
| [PyWinRT](https://github.com/pywinrt/pywinrt) (`winrt-*` packages) | Windows OCR access | MIT |

Online translations are provided by Google Translate through its public web endpoint; GOCR is not
affiliated with or endorsed by Google. Offline translations use OPUS-MT: Jörg Tiedemann and
Santhosh Thottingal, "OPUS-MT — Building open translation services for the World" (EAMT 2020).

---

### wordninja — MIT License

Copyright (c) 2017 Derek Anderson

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
associated documentation files (the "Software"), to deal in the Software without restriction,
including without limitation the rights to use, copy, modify, merge, publish, distribute,
sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or
substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT
NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT
OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

### PaddleOCR models — Apache License 2.0

The PP-OCRv4 detection and recognition models are © PaddlePaddle Authors, licensed under the
Apache License, Version 2.0 (https://www.apache.org/licenses/LICENSE-2.0). They are redistributed
unmodified in ONNX format as published by the RapidOCR project.
