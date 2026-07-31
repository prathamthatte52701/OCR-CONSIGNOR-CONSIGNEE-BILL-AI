import cv2
import numpy as np

from app.features.ocr.preprocessing import assess_and_preprocess


def _blank_page(w: int = 400, h: int = 300) -> np.ndarray:
    img = np.full((h, w, 3), 255, dtype=np.uint8)
    cv2.putText(img, "SAMPLE TEXT 12345", (20, 150), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
    return img


def test_clean_sharp_image_is_left_alone() -> None:
    img = _blank_page()
    result = assess_and_preprocess(img)
    assert result.shape == img.shape
    assert np.array_equal(result, img)


def test_blurred_image_gets_sharpened() -> None:
    img = _blank_page()
    blurred = cv2.GaussianBlur(img, (15, 15), 0)
    result = assess_and_preprocess(blurred)
    assert not np.array_equal(result, blurred)


def test_shadowed_image_gets_lighting_normalized() -> None:
    img = _blank_page()
    shadow = img.copy().astype(np.float64)
    h, w = shadow.shape[:2]
    shadow[:, w // 2 :] *= 0.4  # darken right half heavily
    shadow = shadow.astype(np.uint8)
    result = assess_and_preprocess(shadow)
    assert not np.array_equal(result, shadow)


def test_output_never_crashes_on_tiny_image() -> None:
    tiny = np.full((10, 10, 3), 128, dtype=np.uint8)
    result = assess_and_preprocess(tiny)
    assert result.shape == tiny.shape
