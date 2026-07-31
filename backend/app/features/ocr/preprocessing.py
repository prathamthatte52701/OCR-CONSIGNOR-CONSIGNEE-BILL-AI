"""Quality-gated preprocessing — only touches the image where a real defect is detected,
never degrades an already-good capture. Handles the skew/shadow/crease issues confirmed
on real Part1/Part2 sample photographs (not flatbed scans).

`prepare_for_ocr` is the single entry point both parts call. It is part-aware: Part 1 gets
the full gated step set, Part 2 gets only the steps that were measured not to disturb
PP-Structure's cell geometry (see PART_ALLOWED_STEPS)."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, NamedTuple

import cv2
import fitz  # PyMuPDF
import numpy as np

logger = logging.getLogger(__name__)

BLUR_VARIANCE_THRESHOLD = 100.0
# Real Part 1 captures sit at 0.0-0.6 degrees of residual tilt; rotating (and therefore
# resampling) the whole page to chase under a degree costs more than it recovers.
SKEW_MIN_DEGREES = 1.5
SKEW_MAX_DEGREES = 30.0
LIGHTING_QUADRANT_DELTA_THRESHOLD = 25.0
LOW_CONTRAST_GAP_THRESHOLD = 80.0
# Below this longest side the mobile detector starts dropping small print (measured: a real
# 1012px sample still reads clean at 700px and collapses by ~500px - see the resolution sweep
# in the feature notes). text_det_limit_type="max" only ever shrinks, so nothing upsizes
# these without us. Deliberately well under the ~930px floor of the real sample set so a
# normal capture is never resampled.
MIN_SIDE_FOR_OCR = 700
# Upscale target. Matches text_det_limit_side_len in paddle_runner/ppstructure_runner -
# anything larger is just shrunk straight back down by the detector.
OCR_TARGET_SIDE = 960


def load_image_bytes(data: bytes) -> np.ndarray:
    arr = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Could not decode image data.")
    return image


def render_pdf_first_page(data: bytes, scale: float = 2.5) -> np.ndarray:
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        page = doc[0]
        matrix = fitz.Matrix(scale, scale)
        pixmap = page.get_pixmap(matrix=matrix)
        img_bytes = pixmap.tobytes("png")
    finally:
        doc.close()
    return load_image_bytes(img_bytes)


def _blur_variance(gray: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _sharpen(image: np.ndarray) -> np.ndarray:
    blurred = cv2.GaussianBlur(image, (0, 0), sigmaX=3)
    return cv2.addWeighted(image, 1.5, blurred, -0.5, 0)


def _estimate_skew_degrees(gray: np.ndarray) -> float:
    """Median tilt of the long straight edges on the page - table rules and text baselines.

    The obvious minAreaRect-over-all-dark-pixels trick does not work on these documents:
    they are phone photos, the desk shows in the frame, so the dark set touches all four
    frame edges and the minimum-area box is just the frame - it measured 0.00 degrees on
    real samples tilted a known 5 degrees. Long-line voting ignores the frame entirely.
    """
    edges = cv2.Canny(gray, 60, 180)
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 360,
        threshold=120,
        minLineLength=max(gray.shape) // 5,
        maxLineGap=12,
    )
    if lines is None:
        return 0.0
    angles = []
    for x1, y1, x2, y2 in lines[:, 0]:
        angle = float(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
        # Fold vertical rules onto the horizontal frame; a page's verticals and horizontals
        # carry the same tilt, so both are evidence for the same angle.
        if angle > 45:
            angle -= 90
        elif angle < -45:
            angle += 90
        if abs(angle) <= SKEW_MAX_DEGREES:
            angles.append(angle)
    return float(np.median(angles)) if angles else 0.0


def _deskew(image: np.ndarray, angle: float) -> np.ndarray:
    h, w = image.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(
        image, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )


def _quadrant_brightness_delta(gray: np.ndarray) -> float:
    h, w = gray.shape
    quads = [
        gray[: h // 2, : w // 2],
        gray[: h // 2, w // 2 :],
        gray[h // 2 :, : w // 2],
        gray[h // 2 :, w // 2 :],
    ]
    means = [float(q.mean()) for q in quads]
    return max(means) - min(means)


def _normalize_lighting(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    background = cv2.GaussianBlur(gray, (0, 0), sigmaX=31)
    normalized = cv2.divide(gray, background, scale=255)
    return cv2.cvtColor(normalized, cv2.COLOR_GRAY2BGR)


def _foreground_background_gap(gray: np.ndarray) -> float:
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256]).flatten()
    nonzero = np.nonzero(hist)[0]
    if len(nonzero) < 2:
        return 255.0
    return float(nonzero[-1] - nonzero[0])


def _apply_clahe(image: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l_channel = clahe.apply(l_channel)
    merged = cv2.merge((l_channel, a_channel, b_channel))
    return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)


def _upscale_to_min_side(image: np.ndarray) -> np.ndarray:
    h, w = image.shape[:2]
    factor = OCR_TARGET_SIDE / max(h, w)
    return cv2.resize(image, (round(w * factor), round(h * factor)), interpolation=cv2.INTER_CUBIC)


class _Step(NamedTuple):
    """One defect: the number that describes it, the gate on that number, the fix."""

    metric: str
    measure: Callable[[np.ndarray], float]
    fires: Callable[[float], bool]
    fix: Callable[[np.ndarray, float], np.ndarray]


_STEPS: dict[str, _Step] = {
    "upscale": _Step(
        "max_side",
        lambda gray: float(max(gray.shape)),
        lambda v: v < MIN_SIDE_FOR_OCR,
        lambda image, _v: _upscale_to_min_side(image),
    ),
    "sharpen": _Step(
        "blur_variance",
        lambda gray: round(_blur_variance(gray), 1),
        lambda v: v < BLUR_VARIANCE_THRESHOLD,
        lambda image, _v: _sharpen(image),
    ),
    "deskew": _Step(
        "skew_degrees",
        lambda gray: round(_estimate_skew_degrees(gray), 2),
        lambda v: SKEW_MIN_DEGREES <= abs(v) <= SKEW_MAX_DEGREES,
        _deskew,
    ),
    "normalize_lighting": _Step(
        "quadrant_delta",
        lambda gray: round(_quadrant_brightness_delta(gray), 1),
        lambda v: v > LIGHTING_QUADRANT_DELTA_THRESHOLD,
        lambda image, _v: _normalize_lighting(image),
    ),
    "clahe": _Step(
        "fg_bg_gap",
        lambda gray: round(_foreground_background_gap(gray), 1),
        lambda v: v < LOW_CONTRAST_GAP_THRESHOLD,
        lambda image, _v: _apply_clahe(image),
    ),
}

# Which steps each part lets *through*. Every metric is measured for both parts either way,
# so a failed Part 2 extraction still logs whether the page was blurred, tilted or tiny.
#
# Part 2 applies nothing. deskew/CLAHE/lighting-normalize shift empty-cell positions and
# corrupt PP-Structure's column alignment (see table_extraction.process_part2), and the two
# steps that looked geometry-safe were measured and did not pay: on 3 real Part 2 samples
# downscaled to a third, upscaling recovered 0 of 3 table detections and shortened the page
# text on 2 of them; sharpening the blurred variants recovered 0 of 2 table detections.
# Gross 0/90/180/270 rotation is left to PaddleOCR's own doc-orientation classifier, which
# both engines already enable and which was verified to handle all four orientations.
PART_ALLOWED_STEPS: dict[int, tuple[str, ...]] = {
    1: ("upscale", "sharpen", "deskew", "normalize_lighting", "clahe"),
    2: (),
}

# Runtime kill-switch, for bisecting a bad extraction down to a single step without a deploy.
DISABLED_STEPS: set[str] = set()

_LEGACY_STEPS = ("sharpen", "deskew", "normalize_lighting", "clahe")


@dataclass
class PrepReport:
    part: int
    steps: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"part": self.part, "steps": self.steps, "metrics": self.metrics}


def _apply_steps(image: np.ndarray, allowed: tuple[str, ...], report: PrepReport) -> np.ndarray:
    result = image
    for name, step in _STEPS.items():
        # Gray is recomputed per step: each gate must see the output of the previous fix,
        # otherwise e.g. deskew re-measures a skew that lighting normalisation already moved.
        value = step.measure(cv2.cvtColor(result, cv2.COLOR_BGR2GRAY))
        report.metrics[step.metric] = value
        if name not in allowed or name in DISABLED_STEPS or not step.fires(value):
            continue
        result = step.fix(result, value)
        report.steps.append(name)
    return result


def assess_and_preprocess(image: np.ndarray) -> np.ndarray:
    """Each check is independent and only fires when its own defect is detected."""
    return _apply_steps(image, _LEGACY_STEPS, PrepReport(part=1))


def prepare_for_ocr(image: np.ndarray, part: int) -> tuple[np.ndarray, PrepReport]:
    """Single quality gate for both parts. Returns the image to OCR plus what was done to it."""
    report = PrepReport(part=part)
    result = _apply_steps(image, PART_ALLOWED_STEPS[part], report)
    logger.info(
        "ocr_preprocess part=%s shape=%sx%s steps=%s metrics=%s",
        part,
        image.shape[1],
        image.shape[0],
        ",".join(report.steps) or "none",
        report.metrics,
    )
    return result, report
