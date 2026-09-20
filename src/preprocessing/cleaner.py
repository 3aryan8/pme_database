"""Phase 4 cleaning: deskew -> dark-border trim -> CLAHE -> bilateral filter.

Raw renders are NEVER modified (immutable); cleaned output goes to
data/interim/high_res_clean/ — per docs/group1_contract.md.

Deliberate design decisions:
- Skew < 0.3 deg is NOT corrected: rotation would only add interpolation
  blur for zero gain.
- Skew > 5 deg is NOT corrected: that's a rotation/orientation problem,
  not skew. Auto-rotating on a guess can destroy a page — it is logged
  for human review instead.
- "Crop" only trims fully-dark scanner border bands. It does NOT
  tight-crop to text content: signatures, stamps and thumbprints live at
  page margins, and aggressive content-cropping would delete exactly the
  regions detection must find.
- Near-blank pages (duplex scan backsides) are flagged and returned
  unprocessed — no filter cost, and detection skips them.
"""
import cv2
import numpy as np

from src.utils.config_loader import config
from src.utils.logger import setup_logger

log = setup_logger("preprocess")

MIN_SKEW_DEG = 0.3
MAX_SKEW_DEG = 5.0
BLANK_INK_FRACTION = 0.005     # < 0.5% dark pixels => blank page
DARK_BAND_FRACTION = 0.60      # row/col >=60% dark => scanner border band
DARK_PIXEL_LEVEL = 100


def _skew_angle_deg(gray: np.ndarray) -> float:
    """Median angle (degrees) of near-horizontal Hough lines. 0.0 if none."""
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 360, threshold=120,
                            minLineLength=int(gray.shape[1] * 0.25),
                            maxLineGap=20)
    if lines is None:
        return 0.0
    if lines.ndim == 3:        # OpenCV <5 returns (N, 1, 4); 5.x returns (N, 4)
        lines = lines[:, 0]
    angles = []
    for x1, y1, x2, y2 in lines:
        a = np.degrees(np.arctan2(int(y2) - int(y1), int(x2) - int(x1)))
        if abs(a) <= 15.0:      # near-horizontal lines carry the skew signal
            angles.append(a)
    return float(np.median(angles)) if angles else 0.0


def _rotate(bgr: np.ndarray, angle: float) -> np.ndarray:
    h, w = bgr.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), angle, 1.0)
    return cv2.warpAffine(bgr, M, (w, h), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_REPLICATE)


def _trim_dark_borders(bgr: np.ndarray) -> np.ndarray:
    """Trim fully-dark edge bands (scanner borders). Nothing else."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    dark = gray < DARK_PIXEL_LEVEL
    row_frac = dark.mean(axis=1)
    col_frac = dark.mean(axis=0)
    h, w = bgr.shape[:2]
    top, bot, left, right = 0, h - 1, 0, w - 1
    while top < bot and row_frac[top] > DARK_BAND_FRACTION:
        top += 1
    while bot > top and row_frac[bot] > DARK_BAND_FRACTION:
        bot -= 1
    while left < right and col_frac[left] > DARK_BAND_FRACTION:
        left += 1
    while right > left and col_frac[right] > DARK_BAND_FRACTION:
        right -= 1
    if (top, bot, left, right) == (0, h - 1, 0, w - 1):
        return bgr
    # small margin so content touching a band is never shaved
    top, left = max(0, top - 8), max(0, left - 8)
    bot, right = min(h - 1, bot + 8), min(w - 1, right + 8)
    return bgr[top:bot + 1, left:right + 1]


def clean_page(bgr: np.ndarray) -> tuple[np.ndarray, dict]:
    """Clean one BGR page. Returns (cleaned_image, flags). Never raises."""
    flags: dict = {"blank": False, "deskewed": False, "skew_deg": 0.0,
                   "borders_trimmed": False, "skew_suspicious": False}
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    ink = float(np.mean(gray < 200))
    flags["ink_fraction"] = round(ink, 5)
    if ink < BLANK_INK_FRACTION:
        flags["blank"] = True
        return bgr, flags

    p = config.pipeline.preprocessing
    out = bgr

    if p.deskew:
        angle = _skew_angle_deg(gray)
        flags["skew_deg"] = round(angle, 2)
        if MIN_SKEW_DEG <= abs(angle) <= MAX_SKEW_DEG:
            candidate = _rotate(out, angle)
            # self-check: if rotation made residual skew WORSE, the sign
            # convention bit us — redo with the opposite sign.
            residual = _skew_angle_deg(
                cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY))
            if abs(residual) > abs(angle):
                candidate = _rotate(out, -angle)
            out = candidate
            flags["deskewed"] = True
        elif abs(angle) > MAX_SKEW_DEG:
            flags["skew_suspicious"] = True

    if p.crop_to_content:
        trimmed = _trim_dark_borders(out)
        if trimmed.shape != out.shape:
            flags["borders_trimmed"] = True
            out = trimmed

    if p.contrast_equalization:
        lab = cv2.cvtColor(out, cv2.COLOR_BGR2LAB)
        lab[..., 0] = cv2.createCLAHE(clipLimit=2.0,
                                      tileGridSize=(8, 8)).apply(lab[..., 0])
        out = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    if p.denoise.enabled and p.denoise.method == "bilateral":
        d = int(p.denoise.params.get("d", 9))
        sc = float(p.denoise.params.get("sigma_color", 75))
        ss = float(p.denoise.params.get("sigma_space", 75))
        out = cv2.bilateralFilter(out, d, sc, ss)

    return out, flags