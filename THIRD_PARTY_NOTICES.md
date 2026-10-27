# Third-party notices

GOCR is released under the MIT license (see `LICENSE`). It bundles or depends on the following
third-party components, each under its own license:

| Component | Used for | License |
|---|---|---|
| [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) PP-OCRv4 models (`gocr/models/det.onnx`, `gocr/models/rec.onnx`) and PP-OCRv5 Cyrillic model (`gocr/models/rec_latin_cyrillic.onnx`), ONNX versions distributed by [RapidOCR](https://github.com/RapidAI/RapidOCR) | RapidOCR engine | Apache-2.0 |
| [wordninja](https://github.com/keredson/wordninja) word list (`gocr/data/english_words.txt.gz`) and splitting algorithm | Splitting glued words | MIT |
| [Qt for Python / PySide6](https://doc.qt.io/qtforpython/) | User interface | LGPL-3.0 |
| [ONNX Runtime](https://github.com/microsoft/onnxruntime) | RapidOCR inference | MIT |
| [OpenCV](https://opencv.org/) (`opencv-python-headless`) | Image processing | Apache-2.0 |
| [NumPy](https://numpy.org/) | Arrays | BSD-3-Clause |
| [python-mss](https://github.com/BoboTiG/python-mss) | Screen capture | MIT |
| [PyWinRT](https://github.com/pywinrt/pywinrt) (`winrt-*` packages) | Windows OCR access | MIT |

Translations are provided by Google Translate through its public web endpoint; GOCR is not
affiliated with or endorsed by Google.

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
