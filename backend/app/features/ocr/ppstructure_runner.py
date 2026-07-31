"""Lazy PP-StructureV3 singleton for Part 2 table detection - chosen over manual OpenCV
grid-detection (the old Node.js approach) since it is purpose-built for table structure
recognition. Uses the same PP-OCRv4 mobile text models as Part 1 and disables every
sub-pipeline we don't need (seal/formula/chart/region) to keep it lightweight."""

import threading
from typing import Any

from paddleocr import PPStructureV3

_instance: PPStructureV3 | None = None
_init_lock = threading.Lock()


def get_structure_engine() -> PPStructureV3:
    global _instance
    if _instance is None:
        with _init_lock:
            if _instance is None:
                _instance = PPStructureV3(
                    text_detection_model_name="PP-OCRv4_mobile_det",
                    text_recognition_model_name="en_PP-OCRv4_mobile_rec",
                    use_doc_orientation_classify=True,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                    use_seal_recognition=False,
                    use_formula_recognition=False,
                    use_chart_recognition=False,
                    use_region_detection=False,
                    use_table_recognition=True,
                    enable_mkldnn=False,
                )
    return _instance


def analyze_page(image: Any) -> tuple[list[str], str]:
    """Returns (table HTML per detected table region, full-page OCR text).

    The full-page text matters beyond the table region: on some real samples the tax-summary
    totals sit right at the table's visual edge and get excluded from the detected table
    bounding box entirely, even though PP-Structure's own full-page OCR pass still captures
    them as plain text.
    """
    engine = get_structure_engine()
    results = engine.predict(image)
    html_tables: list[str] = []
    page_texts: list[str] = []
    for page in results:
        for table in page.get("table_res_list", []):
            html = table.get("pred_html")
            if html:
                html_tables.append(html)
        overall_ocr = page.get("overall_ocr_res") or {}
        page_texts.append(" ".join(overall_ocr.get("rec_texts", [])))
    return html_tables, " ".join(page_texts)
