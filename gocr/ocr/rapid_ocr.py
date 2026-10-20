"""RapidOCR engine (PaddleOCR PP-OCRv4 models in ONNX format).

Lightweight implementation (onnxruntime + OpenCV only) of the DBNet detection and the
CRNN/CTC recognition used by RapidOCR. The models ship inside the app.
Reads stylized fonts, low-contrast text, English and Chinese very well.
"""
from __future__ import annotations

import logging
import math
import os

import cv2
import numpy as np

from gocr.config import resource_path
from gocr.i18n import tr
from gocr.ocr import OcrError, OcrLine, upscale_factor

log = logging.getLogger(__name__)


def _session(path):
    import onnxruntime as ort

    opts = ort.SessionOptions()
    opts.intra_op_num_threads = max(1, min(4, (os.cpu_count() or 2)))
    opts.inter_op_num_threads = 1
    opts.log_severity_level = 3
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(str(path), sess_options=opts, providers=["CPUExecutionProvider"])


class RapidOcr:
    name = "rapid"

    # RapidOCR parameters (config.yaml)
    det_limit_min = 736
    det_limit_max = 2000
    det_thresh = 0.3
    box_thresh = 0.5
    unclip_ratio = 1.6
    text_score = 0.5
    rec_h = 48
    rec_w = 320

    def __init__(self):
        det_path = resource_path("gocr", "models", "det.onnx")
        rec_path = resource_path("gocr", "models", "rec.onnx")
        if not det_path.exists() or not rec_path.exists():
            raise OcrError(tr("err.rapid_models"))
        try:
            self.det = _session(det_path)
            self.rec = _session(rec_path)
        except Exception as exc:
            raise OcrError(tr("err.rapid_load", error=exc)) from exc
        meta = self.rec.get_modelmeta().custom_metadata_map
        chars = meta.get("character", "").splitlines()
        if not chars:
            raise OcrError(tr("err.rapid_dict"))
        self.chars = ["blank"] + chars + [" "]
        self.det_input = self.det.get_inputs()[0].name
        self.rec_input = self.rec.get_inputs()[0].name

    # ------------------------------------------------------------------ API
    def recognize(self, img_bgra: np.ndarray) -> list[OcrLine]:
        img = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
        h, w = img.shape[:2]
        # small text: upscale before detecting (the boxes are scaled back later)
        scale = upscale_factor(w, h, 1200) if max(w, h) < 600 else 1.0
        if scale > 1.0:
            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)
        boxes = self._detect(img)
        if not boxes:
            return []
        crops = [self._crop(img, b) for b in boxes]
        texts = self._recognize_crops(crops)
        lines = []
        for box, (text, score, xs) in zip(boxes, texts):
            if score < self.text_score or not text.strip():
                continue
            x0, y0 = box[:, 0].min(), box[:, 1].min()
            x1, y1 = box[:, 0].max(), box[:, 1].max()
            words = self._words(text, xs, float(box[0, 0]), float(y0), float(y1 - y0), (x1 - x0) / max(len(text), 1))
            words = [(t, int(wx / scale), int(wy / scale), max(1, int(ww / scale)), max(1, int(wh / scale)))
                     for t, wx, wy, ww, wh in words]
            lines.append(OcrLine(text=text.strip(),
                                 x=int(x0 / scale), y=int(y0 / scale),
                                 w=max(1, int((x1 - x0) / scale)), h=max(1, int((y1 - y0) / scale)),
                                 words=words or None))
        return lines

    @staticmethod
    def _words(text: str, xs: list, left: float, top: float, height: float, char_w: float) -> list:
        """Groups letters into words with their approximate horizontal position."""
        words, cur, cx = [], "", []
        for ch, x in zip(text, xs):
            if ch == " ":
                if cur:
                    words.append((cur, cx))
                cur, cx = "", []
            else:
                cur += ch
                cx.append(x)
        if cur:
            words.append((cur, cx))
        out = []
        for w, cx in words:
            a = left + min(cx) - char_w * 0.5
            b = left + max(cx) + char_w * 0.5
            out.append((w, a, top, max(1.0, b - a), height))
        return out

    # ------------------------------------------------------------------ detection
    def _detect(self, img: np.ndarray) -> list[np.ndarray]:
        h, w = img.shape[:2]
        ratio = 1.0
        if min(h, w) < self.det_limit_min:
            ratio = self.det_limit_min / min(h, w)
        if max(h, w) * ratio > self.det_limit_max:
            ratio = self.det_limit_max / max(h, w)
        rh = max(32, int(round(h * ratio / 32) * 32))
        rw = max(32, int(round(w * ratio / 32) * 32))
        resized = cv2.resize(img, (rw, rh))
        x = (resized.astype(np.float32) / 255.0 - 0.5) / 0.5
        x = x.transpose(2, 0, 1)[None].astype(np.float32)
        pred = self.det.run(None, {self.det_input: x})[0][0, 0]

        mask = (pred > self.det_thresh).astype(np.uint8)
        mask = cv2.dilate(mask, np.ones((2, 2), np.uint8))
        contours, _ = cv2.findContours(mask * 255, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        boxes = []
        for contour in contours[:1000]:
            rect = cv2.minAreaRect(contour)
            if min(rect[1]) < 3:
                continue
            score = self._box_score(pred, cv2.boxPoints(rect))
            if score < self.box_thresh:
                continue
            (cx, cy), (bw, bh), angle = rect
            area, perim = bw * bh, 2 * (bw + bh)
            d = area * self.unclip_ratio / max(perim, 1e-6)
            rect = ((cx, cy), (bw + 2 * d, bh + 2 * d), angle)
            if min(rect[1]) < 5:
                continue
            pts = cv2.boxPoints(rect)
            pts[:, 0] = np.clip(np.round(pts[:, 0] / rw * w), 0, w - 1)
            pts[:, 1] = np.clip(np.round(pts[:, 1] / rh * h), 0, h - 1)
            pts = self._order(pts)
            if np.linalg.norm(pts[0] - pts[1]) <= 3 or np.linalg.norm(pts[0] - pts[3]) <= 3:
                continue
            boxes.append(pts)
        boxes.sort(key=lambda b: (b[0, 1], b[0, 0]))
        return boxes

    @staticmethod
    def _box_score(pred: np.ndarray, pts: np.ndarray) -> float:
        h, w = pred.shape
        xmin = int(np.clip(np.floor(pts[:, 0].min()), 0, w - 1))
        xmax = int(np.clip(np.ceil(pts[:, 0].max()), 0, w - 1))
        ymin = int(np.clip(np.floor(pts[:, 1].min()), 0, h - 1))
        ymax = int(np.clip(np.ceil(pts[:, 1].max()), 0, h - 1))
        mask = np.zeros((ymax - ymin + 1, xmax - xmin + 1), dtype=np.uint8)
        shifted = pts.copy()
        shifted[:, 0] -= xmin
        shifted[:, 1] -= ymin
        cv2.fillPoly(mask, shifted.reshape(1, -1, 2).astype(np.int32), 1)
        return float(cv2.mean(pred[ymin:ymax + 1, xmin:xmax + 1], mask)[0])

    @staticmethod
    def _order(pts: np.ndarray) -> np.ndarray:
        xs = pts[np.argsort(pts[:, 0])]
        left = xs[:2][np.argsort(xs[:2, 1])]
        right = xs[2:][np.argsort(xs[2:, 1])]
        return np.array([left[0], right[0], right[1], left[1]], dtype=np.float32)

    @staticmethod
    def _crop(img: np.ndarray, pts: np.ndarray) -> np.ndarray:
        cw = int(max(np.linalg.norm(pts[0] - pts[1]), np.linalg.norm(pts[2] - pts[3])))
        ch = int(max(np.linalg.norm(pts[0] - pts[3]), np.linalg.norm(pts[1] - pts[2])))
        dst = np.float32([[0, 0], [cw, 0], [cw, ch], [0, ch]])
        m = cv2.getPerspectiveTransform(pts.astype(np.float32), dst)
        crop = cv2.warpPerspective(img, m, (cw, ch), borderMode=cv2.BORDER_REPLICATE, flags=cv2.INTER_CUBIC)
        if ch * 1.0 / max(cw, 1) >= 1.5:
            crop = np.rot90(crop)
        return crop

    # ------------------------------------------------------------------ reconocimiento
    def _recognize_crops(self, crops: list[np.ndarray]) -> list[tuple[str, float]]:
        results: list[tuple[str, float]] = [("", 0.0)] * len(crops)
        order = np.argsort([c.shape[1] / max(c.shape[0], 1) for c in crops])
        batch = 6
        for start in range(0, len(crops), batch):
            idx = order[start:start + batch]
            max_ratio = max([self.rec_w / self.rec_h] + [crops[i].shape[1] / max(crops[i].shape[0], 1) for i in idx])
            width = int(self.rec_h * max_ratio)
            tensor = np.zeros((len(idx), 3, self.rec_h, width), dtype=np.float32)
            for j, i in enumerate(idx):
                c = crops[i]
                ratio = c.shape[1] / max(c.shape[0], 1)
                rw = min(width, int(math.ceil(self.rec_h * ratio)))
                resized = cv2.resize(c, (max(1, rw), self.rec_h)).astype(np.float32)
                resized = (resized.transpose(2, 0, 1) / 255.0 - 0.5) / 0.5
                tensor[j, :, :, :rw] = resized
            preds = self.rec.run(None, {self.rec_input: tensor})[0]
            T = preds.shape[1]
            for j, i in enumerate(idx):
                c = crops[i]
                rw = min(width, int(math.ceil(self.rec_h * c.shape[1] / max(c.shape[0], 1))))
                # CTC column -> x inside the original crop
                col_to_x = (width / T) * (c.shape[1] / max(rw, 1))
                results[i] = self._ctc_decode(preds[j], col_to_x)
        return results

    def _ctc_decode(self, pred: np.ndarray, col_to_x: float = 1.0):
        ids = pred.argmax(axis=1)
        probs = pred.max(axis=1)
        keep = np.ones(len(ids), dtype=bool)
        keep[1:] = ids[1:] != ids[:-1]
        keep &= ids != 0
        cols = np.nonzero(keep)[0]
        chars, xs = [], []
        for col in cols:
            if ids[col] < len(self.chars):
                chars.append(self.chars[ids[col]])
                xs.append((col + 0.5) * col_to_x)
        conf = float(np.mean(probs[keep])) if keep.any() else 0.0
        return "".join(chars), conf, xs
