"""Generates the synthetic degraded-document set used to validate the OCR quality gate.

Not a pytest module (no test_* name, never collected). Run it manually:

    python -m app.features.ocr.test_fixtures.generate_variants <src_dir> <out_dir> [n_samples]

Real samples live outside the repo (E:\\part 1 cons cons, E:\\part 2 cons cons) and the
generated variants are large binaries, so nothing is committed - only this generator is.
"""

import sys
from pathlib import Path

import cv2
import numpy as np

# Every variant is one deliberate defect, matching one gate in preprocessing.py.
VARIANTS = (
    "control",
    "blur",
    "tilt5",
    "rot90",
    "rot180",
    "rot270",
    "watermark",
    "lowcontrast",
    "shadow",
    "downscale",
    "upscale",
    "stamp",
    "boldcolored",
)


def _blur(img: np.ndarray) -> np.ndarray:
    return cv2.GaussianBlur(img, (9, 9), 0)


def _tilt(img: np.ndarray, degrees: float = 5.0) -> np.ndarray:
    h, w = img.shape[:2]
    matrix = cv2.getRotationMatrix2D((w // 2, h // 2), degrees, 1.0)
    return cv2.warpAffine(
        img, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )


def _multiply(img: np.ndarray, layer: np.ndarray) -> np.ndarray:
    """Multiply blend - ink laid *on top of* the page. Alpha-blending the whole frame instead
    would ghost a second copy of the document over itself, which is a different defect."""
    return (img.astype(np.float32) * (layer.astype(np.float32) / 255.0)).astype(np.uint8)


def _watermark(img: np.ndarray) -> np.ndarray:
    """Semi-transparent grey diagonal 'COPY' band across the page."""
    h, w = img.shape[:2]
    layer = np.full((h, w, 3), 255, dtype=np.uint8)
    cv2.putText(
        layer,
        "COPY",
        (int(w * 0.12), int(h * 0.62)),
        cv2.FONT_HERSHEY_SIMPLEX,
        w / 200.0,
        (150, 150, 150),
        max(6, w // 120),
        cv2.LINE_AA,
    )
    matrix = cv2.getRotationMatrix2D((w // 2, h // 2), 30, 1.0)
    rotated = cv2.warpAffine(layer, matrix, (w, h), borderValue=(255, 255, 255))
    return _multiply(img, rotated)


def _stamp(img: np.ndarray) -> np.ndarray:
    """Blue circular rubber seal over the middle of the field block - what the real Part 2
    samples carry, and what a Part 1 page picks up when it is countersigned."""
    h, w = img.shape[:2]
    layer = np.full((h, w, 3), 255, dtype=np.uint8)
    centre = (int(w * 0.55), int(h * 0.55))
    radius = int(min(h, w) * 0.22)
    blue = (200, 120, 60)
    cv2.circle(layer, centre, radius, blue, max(3, w // 250))
    cv2.circle(layer, centre, int(radius * 0.78), blue, max(2, w // 400))
    cv2.putText(
        layer,
        "VERIFIED",
        (centre[0] - int(radius * 0.62), centre[1]),
        cv2.FONT_HERSHEY_SIMPLEX,
        w / 900.0,
        blue,
        max(2, w // 400),
        cv2.LINE_AA,
    )
    return _multiply(img, layer)


def _bold_colored(img: np.ndarray) -> np.ndarray:
    """Thicken and re-ink every dark stroke - the bold/coloured-font condition."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    ink = cv2.dilate((gray < 120).astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    out = img.copy()
    out[ink] = (150, 40, 40)  # dark blue, BGR
    return out


def _lowcontrast(img: np.ndarray) -> np.ndarray:
    return np.clip(img.astype(np.float32) * 0.35 + 150, 0, 255).astype(np.uint8)


def _shadow(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    ramp = np.linspace(1.0, 0.35, w, dtype=np.float32)[None, :, None]
    return np.clip(img.astype(np.float32) * ramp, 0, 255).astype(np.uint8)


def _downscale(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    return cv2.resize(img, (w // 3, h // 3), interpolation=cv2.INTER_AREA)


def _upscale(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    return cv2.resize(img, (w * 3, h * 3), interpolation=cv2.INTER_CUBIC)


_MAKERS = {
    "control": lambda img: img,
    "blur": _blur,
    "tilt5": _tilt,
    "rot90": lambda img: cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE),
    "rot180": lambda img: cv2.rotate(img, cv2.ROTATE_180),
    "rot270": lambda img: cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE),
    "watermark": _watermark,
    "lowcontrast": _lowcontrast,
    "shadow": _shadow,
    "downscale": _downscale,
    "upscale": _upscale,
    "stamp": _stamp,
    "boldcolored": _bold_colored,
}


def generate(src_dir: Path, out_dir: Path, n_samples: int = 3) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    # The source folders contain literal "name (1).jpeg" duplicates; skip them.
    sources = sorted(p for p in src_dir.glob("*.jpeg") if "(" not in p.name)[:n_samples]
    written = []
    for src in sources:
        img = cv2.imread(str(src))
        if img is None:
            continue
        for variant in VARIANTS:
            path = out_dir / f"{src.stem}__{variant}.jpeg"
            cv2.imwrite(str(path), _MAKERS[variant](img), [cv2.IMWRITE_JPEG_QUALITY, 95])
            written.append(path)
    return written


if __name__ == "__main__":
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    paths = generate(Path(sys.argv[1]), Path(sys.argv[2]), n)
    print(f"wrote {len(paths)} files to {sys.argv[2]}")
