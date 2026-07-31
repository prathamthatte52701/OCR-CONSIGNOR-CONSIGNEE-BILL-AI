"""Quality-gated preprocessing — only touches the image where a real defect is detected,
never degrades an already-good capture. Handles the skew/shadow/crease issues confirmed
on real Part1/Part2 sample photographs (not flatbed scans)."""

import cv2
import fitz  # PyMuPDF
import numpy as np

BLUR_VARIANCE_THRESHOLD = 100.0
SKEW_MIN_DEGREES = 0.5
SKEW_MAX_DEGREES = 30.0
LIGHTING_QUADRANT_DELTA_THRESHOLD = 25.0
LOW_CONTRAST_GAP_THRESHOLD = 80.0


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
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    coords = cv2.findNonZero(thresh)
    if coords is None:
        return 0.0
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = 90 + angle
    return float(angle)


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


def assess_and_preprocess(image: np.ndarray) -> np.ndarray:
    """Each check is independent and only fires when its own defect is detected."""
    result = image

    gray = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
    if _blur_variance(gray) < BLUR_VARIANCE_THRESHOLD:
        result = _sharpen(result)

    gray = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
    skew = _estimate_skew_degrees(gray)
    if SKEW_MIN_DEGREES <= abs(skew) <= SKEW_MAX_DEGREES:
        result = _deskew(result, skew)

    gray = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
    if _quadrant_brightness_delta(gray) > LIGHTING_QUADRANT_DELTA_THRESHOLD:
        result = _normalize_lighting(result)

    gray = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
    if _foreground_background_gap(gray) < LOW_CONTRAST_GAP_THRESHOLD:
        result = _apply_clahe(result)

    return result
