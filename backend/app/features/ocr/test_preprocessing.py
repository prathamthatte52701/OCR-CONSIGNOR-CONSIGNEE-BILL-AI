import cv2
import numpy as np
import pytest

from app.features.ocr import preprocessing
from app.features.ocr.preprocessing import assess_and_preprocess, prepare_for_ocr


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


def _big_clean_page() -> np.ndarray:
    """A ruled form, like both real parts: large enough that the resolution gate stays shut,
    and with the long straight rules the skew estimator votes on."""
    img = np.full((1100, 1600, 3), 255, dtype=np.uint8)
    cv2.rectangle(img, (60, 60), (1540, 1040), (0, 0, 0), 3)
    for i in range(6):
        y = 150 + i * 140
        cv2.line(img, (60, y + 40), (1540, y + 40), (0, 0, 0), 2)
        cv2.putText(img, "SAMPLE TEXT 12345", (90, y), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 3)
    return img


@pytest.mark.parametrize("part", [1, 2])
def test_good_page_triggers_no_steps_for_either_part(part: int) -> None:
    img = _big_clean_page()
    result, report = prepare_for_ocr(img, part=part)
    assert report.steps == []
    assert np.array_equal(result, img)


def test_part2_never_alters_geometry_but_part1_deskews() -> None:
    img = _big_clean_page()
    h, w = img.shape[:2]
    tilted = cv2.warpAffine(
        img,
        cv2.getRotationMatrix2D((w // 2, h // 2), 5.0, 1.0),
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,  # black-filled corners would read as a 0-degree box
    )

    part1, report1 = prepare_for_ocr(tilted, part=1)
    part2, report2 = prepare_for_ocr(tilted, part=2)

    assert "deskew" in report1.steps and not np.array_equal(part1, tilted)
    # PP-Structure's cell geometry must see exactly the pixels it was tuned on.
    assert report2.steps == [] and np.array_equal(part2, tilted)


@pytest.mark.parametrize("degrees", [-6.0, 6.0])
def test_skew_is_measured_in_both_directions(degrees: float) -> None:
    """Regression: minAreaRect reports a counter-clockwise tilt as ~84 degrees, which used to
    fall outside SKEW_MAX_DEGREES and skip the deskew entirely."""
    img = _big_clean_page()
    h, w = img.shape[:2]
    tilted = cv2.warpAffine(
        img,
        cv2.getRotationMatrix2D((w // 2, h // 2), degrees, 1.0),
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    measured = preprocessing._estimate_skew_degrees(cv2.cvtColor(tilted, cv2.COLOR_BGR2GRAY))
    assert abs(abs(measured) - abs(degrees)) < 1.0


def test_low_resolution_page_is_upscaled_on_part1() -> None:
    small = cv2.resize(_big_clean_page(), (320, 220))
    result, report = prepare_for_ocr(small, part=1)
    assert "upscale" in report.steps
    assert max(result.shape[:2]) == preprocessing.OCR_TARGET_SIDE


def test_low_resolution_page_is_measured_but_not_upscaled_on_part2() -> None:
    # Part 2 allows zero steps (see PART_ALLOWED_STEPS comment): upscaling was measured
    # against real Part 2 samples and recovered 0/3 table detections while shortening
    # OCR text on 2/3 - so the metric is still recorded (max_side) but never acted on.
    small = cv2.resize(_big_clean_page(), (320, 220))
    result, report = prepare_for_ocr(small, part=2)
    assert "upscale" not in report.steps
    assert report.metrics["max_side"] == 320.0
    assert result.shape[:2] == small.shape[:2]


def test_disabled_steps_kill_switch() -> None:
    small = cv2.resize(_big_clean_page(), (320, 220))
    preprocessing.DISABLED_STEPS.add("upscale")
    try:
        result, report = prepare_for_ocr(small, part=1)
    finally:
        preprocessing.DISABLED_STEPS.discard("upscale")
    assert "upscale" not in report.steps
    assert result.shape[:2] == small.shape[:2]


def test_report_records_the_metric_each_gate_fired_on() -> None:
    _, report = prepare_for_ocr(_big_clean_page(), part=1)
    assert set(report.metrics) == {
        "max_side",
        "blur_variance",
        "skew_degrees",
        "quadrant_delta",
        "fg_bg_gap",
    }
