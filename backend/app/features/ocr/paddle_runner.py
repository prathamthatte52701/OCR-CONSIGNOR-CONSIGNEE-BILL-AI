"""Lazy PaddleOCR singleton — PP-OCRv4 MOBILE models (server models OOM on CPU-only low-RAM
machines). Loaded once and reused; never re-instantiated per request."""

import threading
from typing import Any

from paddleocr import PaddleOCR

_instance: PaddleOCR | None = None
_init_lock = threading.Lock()

OCR_TIMEOUT_SECONDS_PDF = 180
OCR_TIMEOUT_SECONDS_IMAGE = 60


def get_ocr_engine() -> PaddleOCR:
    global _instance
    if _instance is None:
        with _init_lock:
            if _instance is None:
                _instance = PaddleOCR(
                    text_detection_model_name="PP-OCRv4_mobile_det",
                    text_recognition_model_name="en_PP-OCRv4_mobile_rec",
                    use_doc_orientation_classify=True,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                    text_det_limit_side_len=960,
                    text_det_limit_type="max",
                    enable_mkldnn=False,  # oneDNN build is incompatible with this CPU wheel's ops
                )
    return _instance


def run_ocr(image: str | Any) -> list[dict[str, Any]]:
    """Returns a list of {text, confidence, box} in reading order.

    box is [x1, y1, x2, y2] in pixel coordinates - needed to reconstruct which
    table column (e.g. Consignee vs Consignor) a line belongs to, since flat
    reading-order text loses that structure on multi-column forms.
    """
    engine = get_ocr_engine()
    results = engine.predict(image)
    lines: list[dict[str, Any]] = []
    for page in results:
        texts = page.get("rec_texts", [])
        scores = page.get("rec_scores", [])
        boxes = page.get("rec_boxes", [])
        for text, score, box in zip(texts, scores, boxes, strict=False):
            lines.append(
                {
                    "text": text,
                    "confidence": float(score),
                    "box": [int(v) for v in box],
                }
            )
    return lines
