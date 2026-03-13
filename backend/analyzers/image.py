"""
Image forensics analysis module.
Uses OpenCV + numpy to run deepfake / manipulation detection on still images.

Techniques used
---------------
ELA   — Error Level Analysis: JPEG re-compression reveals regions with a
        different compression history, which indicates splicing or editing.
        (JPEG only; PNG is lossless so ELA is replaced by noise-map analysis.)

NCM   — Noise Consistency Map: genuine images have spatially consistent
        sensor noise; composited / AI-generated images do not.

Face  — Haar-cascade face detection + per-face checks:
          • blur (GAN faces can have unnatural smoothness)
          • boundary discontinuity (face-swap seams)
          • bilateral symmetry (GANs often generate over-symmetric faces)

Block — JPEG 8×8 DCT blocking: heavy re-encoding leaves visible block grids.

Color — Channel variance & saturation checks flag unnaturally uniform or
        over-saturated images.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
    logger.warning("opencv not installed — image analysis unavailable")

JPEG_EXTS = {".jpg", ".jpeg"}


# ═════════════════════════════════════════════════════════════════════════════
# Public entry-point
# ═════════════════════════════════════════════════════════════════════════════

def analyze_image(image_path: str) -> dict:
    """
    Run full forensic analysis on a still image.

    Returns
    -------
    dict with keys:
        ela_score         : int  0-100  (ELA / re-compression anomaly)
        noise_score       : int  0-100  (spatial noise consistency)
        compression_score : int  0-100  (blocking / quality artefacts)
        facial_score      : int  0-100  (face anomalies)
        findings          : list[str]
    """
    empty = {"ela_score": 0, "noise_score": 0,
             "compression_score": 0, "facial_score": 0, "findings": []}

    if not HAS_CV2:
        return {**empty, "findings": ["opencv not installed — image analysis skipped"]}

    if not Path(image_path).exists():
        return {**empty, "findings": ["Image file not found"]}

    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img is None:
        return {**empty, "findings": ["Image could not be decoded (unsupported or corrupt)"]}

    ext = Path(image_path).suffix.lower()
    findings: list[str] = []
    ela_score         = 0
    noise_score       = 0
    compression_score = 0
    facial_score      = 0

    h, w = img.shape[:2]
    logger.info("Image loaded — %dx%d  ext=%s", w, h, ext)

    # ── 1. Resolution check ───────────────────────────────────────────────────
    total_px = w * h
    if total_px < 10_000:          # < ~100×100
        compression_score += 30
        findings.append(f"Very low resolution ({w}x{h}) — image may have been heavily downscaled")
    elif total_px < 50_000:        # < ~224×224
        compression_score += 15
        findings.append(f"Low resolution ({w}x{h}) — limited forensic detail available")

    # Non-standard aspect ratio (AI models often output specific ratios)
    ar = w / h if h else 1
    if not (0.5 <= ar <= 3.0):
        findings.append(f"Unusual aspect ratio {ar:.2f} — not typical for camera photos")

    # ── 2. ELA — JPEG only ────────────────────────────────────────────────────
    if ext in JPEG_EXTS:
        ela_score = _compute_ela(img, findings)
    else:
        # PNG / BMP: run extra noise-map analysis in its place
        ela_score = _png_frequency_check(img, findings)

    # ── 3. Noise Consistency Map ──────────────────────────────────────────────
    noise_score = _noise_consistency(img, findings)

    # ── 4. JPEG blocking artefacts ────────────────────────────────────────────
    if ext in JPEG_EXTS:
        block_s = _blocking_artifacts(img, findings)
        compression_score = max(compression_score, block_s)

    # ── 5. Color distribution ─────────────────────────────────────────────────
    color_s = _color_distribution(img, findings)
    # Feed color anomaly into noise_score (general image-quality slot)
    noise_score = min(100, noise_score + color_s // 3)

    # ── 6. Face detection & per-face forensics ────────────────────────────────
    facial_score = _analyze_faces(img, findings)

    return {
        "ela_score":         min(100, max(0, ela_score)),
        "noise_score":       min(100, max(0, noise_score)),
        "compression_score": min(100, max(0, compression_score)),
        "facial_score":      min(100, max(0, facial_score)),
        "findings":          findings,
    }


# ═════════════════════════════════════════════════════════════════════════════
# ELA — Error Level Analysis
# ═════════════════════════════════════════════════════════════════════════════

def _compute_ela(img: np.ndarray, findings: list[str]) -> int:
    """
    Re-compress the image at quality=90 and measure per-block error.
    High regional ELA variance → splicing / copy-paste.
    """
    try:
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 90]
        ok, buf = cv2.imencode(".jpg", img, encode_param)
        if not ok:
            return 0
        recompressed = cv2.imdecode(buf, cv2.IMREAD_COLOR)

        # Pixel-wise absolute difference (amplified for visibility)
        ela = cv2.absdiff(img.astype(np.float32), recompressed.astype(np.float32))
        ela_gray = cv2.cvtColor(ela.astype(np.uint8), cv2.COLOR_BGR2GRAY)

        # Analyse in 32×32 blocks
        h, w = ela_gray.shape
        bsz = max(16, min(h, w) // 24)
        block_means: list[float] = []

        for y in range(0, h - bsz, bsz):
            for x in range(0, w - bsz, bsz):
                block_means.append(float(np.mean(ela_gray[y:y + bsz, x:x + bsz])))

        if len(block_means) < 4:
            return 0

        arr         = np.array(block_means)
        global_mean = float(np.mean(arr))
        ela_cv      = float(np.std(arr)) / (global_mean + 1e-8)

        # Fraction of blocks with suspiciously high ELA
        high_ratio  = float(np.sum(arr > global_mean * 2.8)) / len(arr)

        score = 0
        if high_ratio > 0.12:
            score += 35
            findings.append(
                f"ELA: {high_ratio*100:.0f}% of image blocks show elevated re-compression "
                "error — possible splicing or region-level editing"
            )
        if ela_cv > 1.4:
            score += 25
            findings.append(
                f"ELA coefficient of variation {ela_cv:.2f} — regions have "
                "inconsistent compression history"
            )
        elif ela_cv > 0.9:
            score += 12
            findings.append(f"Moderate ELA variance (CV={ela_cv:.2f}) — minor inconsistencies")

        return min(100, score)

    except Exception as exc:
        logger.warning("ELA failed: %s", exc)
        return 0


def _png_frequency_check(img: np.ndarray, findings: list[str]) -> int:
    """
    For lossless formats (PNG) run a DCT-based frequency check instead of ELA.
    Unusual high-frequency energy distribution can indicate AI generation.
    """
    try:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
        h, w = gray.shape
        bsz  = 32
        hf_ratios: list[float] = []

        for y in range(0, h - bsz, bsz):
            for x in range(0, w - bsz, bsz):
                block = gray[y:y + bsz, x:x + bsz]
                dct   = cv2.dct(block)
                total = float(np.sum(np.abs(dct))) + 1e-8
                # High-frequency energy = top-right corner of DCT block
                hf    = float(np.sum(np.abs(dct[bsz // 2:, bsz // 2:])))
                hf_ratios.append(hf / total)

        if len(hf_ratios) < 4:
            return 0

        arr    = np.array(hf_ratios)
        hf_cv  = float(np.std(arr)) / (float(np.mean(arr)) + 1e-8)
        avg_hf = float(np.mean(arr))

        score = 0
        # AI-generated PNGs often have unusually uniform frequency distribution
        if hf_cv < 0.15 and avg_hf < 0.05:
            score += 20
            findings.append(
                "Frequency distribution is unusually uniform — consistent with AI-generated imagery"
            )
        return min(100, score)

    except Exception as exc:
        logger.warning("PNG frequency check failed: %s", exc)
        return 0


# ═════════════════════════════════════════════════════════════════════════════
# Noise Consistency Map
# ═════════════════════════════════════════════════════════════════════════════

def _noise_consistency(img: np.ndarray, findings: list[str]) -> int:
    """
    Divide the image into blocks and estimate local noise level per block.
    High variance across blocks = composited image (different source noise).
    """
    try:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        bsz  = max(32, min(h, w) // 12)
        noise_levels: list[float] = []

        for y in range(0, h - bsz, bsz):
            for x in range(0, w - bsz, bsz):
                blk      = gray[y:y + bsz, x:x + bsz].astype(np.float32)
                blurred  = cv2.GaussianBlur(gray[y:y + bsz, x:x + bsz], (5, 5), 0).astype(np.float32)
                noise_levels.append(float(np.std(blk - blurred)))

        if len(noise_levels) < 4:
            return 0

        arr = np.array(noise_levels)
        cv  = float(np.std(arr)) / (float(np.mean(arr)) + 1e-8)

        score = 0
        if cv > 0.85:
            score += 28
            findings.append(
                f"Noise map shows high regional inconsistency (CV={cv:.2f}) — "
                "typical of composited or AI-inpainted images"
            )
        elif cv > 0.55:
            score += 14
            findings.append(f"Moderate noise inconsistency across image regions (CV={cv:.2f})")

        return min(100, score)

    except Exception as exc:
        logger.warning("Noise map failed: %s", exc)
        return 0


# ═════════════════════════════════════════════════════════════════════════════
# JPEG Blocking Artefacts
# ═════════════════════════════════════════════════════════════════════════════

def _blocking_artifacts(img: np.ndarray, findings: list[str]) -> int:
    """
    Measure sharpness jump at 8-pixel DCT block boundaries vs interior edges.
    High blockiness ratio = re-encoding artefacts after manipulation.
    """
    try:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
        h, w = gray.shape

        boundary_diffs: list[float] = []
        interior_diffs: list[float] = []

        for y in range(1, h):
            row_diff = float(np.mean(np.abs(gray[y, :] - gray[y - 1, :])))
            if y % 8 == 0:
                boundary_diffs.append(row_diff)
            else:
                interior_diffs.append(row_diff)

        if not boundary_diffs or not interior_diffs:
            return 0

        ratio = float(np.mean(boundary_diffs)) / (float(np.mean(interior_diffs)) + 1e-8)

        if ratio > 2.2:
            findings.append(
                f"Heavy JPEG blocking artefacts (boundary/interior ratio={ratio:.2f}) — "
                "image was re-encoded after modification"
            )
            return 65
        elif ratio > 1.5:
            findings.append(f"Moderate JPEG blocking (ratio={ratio:.2f})")
            return 35

        return 0

    except Exception as exc:
        logger.warning("Blocking check failed: %s", exc)
        return 0


# ═════════════════════════════════════════════════════════════════════════════
# Color Distribution
# ═════════════════════════════════════════════════════════════════════════════

def _color_distribution(img: np.ndarray, findings: list[str]) -> int:
    """
    Flag unusual channel variance or over-saturation (common in GAN outputs).
    """
    try:
        score = 0

        # Per-channel std — very low = suspiciously uniform
        for i, ch_name in enumerate(["Blue", "Green", "Red"]):
            std = float(np.std(img[:, :, i]))
            if std < 8:
                score += 12
                findings.append(
                    f"Channel {ch_name} has very low variance ({std:.1f}) — unnaturally uniform colour"
                )

        # HSV saturation
        hsv      = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        sat_mean = float(np.mean(hsv[:, :, 1]))
        if sat_mean > 210:
            score += 15
            findings.append(
                f"Mean saturation {sat_mean:.0f}/255 is unusually high — "
                "possible synthetic or heavily post-processed image"
            )

        return min(100, score)

    except Exception as exc:
        logger.warning("Colour check failed: %s", exc)
        return 0


# ═════════════════════════════════════════════════════════════════════════════
# Face Detection & Per-Face Forensics
# ═════════════════════════════════════════════════════════════════════════════

def _analyze_faces(img: np.ndarray, findings: list[str]) -> int:
    """
    Detect faces and run per-face anomaly checks:
      • blur  — GAN faces are often unnaturally smooth
      • boundary discontinuity — face-swap seams
      • bilateral symmetry — GANs over-symmetrise faces
    """
    try:
        gray          = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        face_cascade  = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        faces = face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40)
        )

        if len(faces) == 0:
            return 0

        score = 0

        for (fx, fy, fw, fh) in faces:
            face_gray = gray[fy: fy + fh, fx: fx + fw]

            # ── Blur check ────────────────────────────────────────────────────
            lap_var = float(cv2.Laplacian(face_gray, cv2.CV_64F).var())
            if lap_var < 15:
                score += 28
                findings.append(
                    f"Face region is unusually blurry (Laplacian var={lap_var:.1f}) — "
                    "possible face-swap or GAN smoothing artefact"
                )
            elif lap_var < 40:
                score += 12
                findings.append(f"Face region shows moderate blurring (var={lap_var:.1f})")

            # ── Boundary noise discontinuity ──────────────────────────────────
            if fx > 8 and fy > 8:
                # Create face mask and 10 px border ring
                mask    = np.zeros(gray.shape, dtype=np.uint8)
                mask[fy: fy + fh, fx: fx + fw] = 255
                kernel  = np.ones((10, 10), np.uint8)
                border  = cv2.subtract(cv2.dilate(mask, kernel), mask)

                face_noise   = float(np.std(gray[mask > 0]))
                border_noise = float(np.std(gray[border > 0])) if np.any(border > 0) else face_noise

                max_n = max(face_noise, border_noise, 1e-8)
                discontinuity = abs(face_noise - border_noise) / max_n

                if discontinuity > 0.55:
                    score += 22
                    findings.append(
                        f"Noise discontinuity at face boundary ({discontinuity:.2f}) — "
                        "indicates the face was composited onto the background"
                    )

            # ── Bilateral symmetry ────────────────────────────────────────────
            if face_gray.shape[0] >= 20 and face_gray.shape[1] >= 20:
                r64      = cv2.resize(face_gray, (64, 64)).astype(np.float32)
                flipped  = cv2.flip(r64, 1)
                sym      = 1.0 - float(np.mean(np.abs(r64 - flipped))) / 128.0

                if sym > 0.93:
                    score += 18
                    findings.append(
                        f"Face bilateral symmetry {sym:.3f} — unnaturally high, "
                        "typical of GAN-synthesised faces"
                    )

        return min(100, score)

    except Exception as exc:
        logger.warning("Face analysis failed: %s", exc)
        return 0
