"""
Video analysis module.
Uses OpenCV to sample frames, detect faces, and measure temporal consistency.

Deepfake indicators we check:
  - Brightness / colour inconsistency across frames  (video splicing)
  - Frame sharpness inconsistency                    (GAN output vs real frames)
  - Edge-density inconsistency                       (blending artefacts)
  - Face detection rate drops                        (face-swap failure)
  - Face bounding-box size jitter                    (GAN instability)
  - Compression / noise artefacts                    (re-encoding after manipulation)
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
    logger.warning("opencv not installed — video analysis unavailable")

try:
    from analyzers.ml_model import analyze_image_frame as _ml_analyze_frame
    _HAS_ML = True
except Exception:
    _HAS_ML = False
    def _ml_analyze_frame(frame):  # noqa: F811
        return {"fake_probability": 0.0}

MAX_SAMPLE_FRAMES = 30   # analyse at most this many frames
MIN_FACE_SIZE     = 40   # px — ignore very small detections
_ML_MAX_FRAMES    = 5    # number of frames passed to the ML model


def analyze_video(video_path: str) -> dict:
    """
    Analyse video frames for manipulation / deepfake indicators.

    Returns
    -------
    dict with keys:
        facial_score              : int   0-100
        temporal_score            : int   0-100
        compression_score         : int   0-100
        video_ml_fake_probability : float 0.0-1.0
        findings                  : list[str]
    """
    findings: list[str] = []
    facial_score      = 0
    temporal_score    = 0
    compression_score = 0

    if not HAS_CV2:
        return {
            "facial_score": 0, "temporal_score": 0,
            "compression_score": 0, "video_ml_fake_probability": 0.0,
            "findings": ["opencv not installed — video analysis skipped"],
        }

    if not Path(video_path).exists():
        return {
            "facial_score": 0, "temporal_score": 0,
            "compression_score": 0, "video_ml_fake_probability": 0.0,
            "findings": ["Video file not found"],
        }

    # ── Open video ──────────────────────────────────────────────────────────
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {
            "facial_score": 0, "temporal_score": 0,
            "compression_score": 0, "video_ml_fake_probability": 0.0,
            "findings": ["Could not open video — format may be unsupported"],
        }

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    fps          = float(cap.get(cv2.CAP_PROP_FPS)) or 25.0
    width        = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height       = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # Evenly distribute sample points
    sample_interval = max(1, total_frames // MAX_SAMPLE_FRAMES)

    # Load face detector (Haar cascade — ships with OpenCV, no download needed)
    cascade_path  = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade  = cv2.CascadeClassifier(cascade_path)
    has_cascade   = not face_cascade.empty()

    # Accumulators
    brightnesses:    list[float]     = []
    blurs:           list[float]     = []
    edges_mean:      list[float]     = []
    noise_levels:    list[float]     = []
    faces_per_frame: list[int]       = []
    face_areas:      list[float]     = []
    ml_frames:       list[np.ndarray] = []   # up to _ML_MAX_FRAMES for ML model

    try:
        for i in range(0, total_frames, sample_interval):
            if len(brightnesses) >= MAX_SAMPLE_FRAMES:
                break
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ret, frame = cap.read()
            if not ret or frame is None:
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # Collect frame for ML analysis (evenly spaced, up to _ML_MAX_FRAMES)
            if len(ml_frames) < _ML_MAX_FRAMES:
                step = max(1, MAX_SAMPLE_FRAMES // _ML_MAX_FRAMES)
                if len(brightnesses) % step == 0:
                    ml_frames.append(frame.copy())

            # Brightness (mean pixel intensity)
            brightnesses.append(float(np.mean(gray)))

            # Blurriness — Laplacian variance (higher = sharper)
            blurs.append(float(cv2.Laplacian(gray, cv2.CV_64F).var()))

            # Edge density
            edges = cv2.Canny(gray, 50, 150)
            edges_mean.append(float(np.mean(edges)))

            # Noise estimation
            noise_levels.append(_estimate_noise(gray))

            # Face detection
            if has_cascade:
                faces = face_cascade.detectMultiScale(
                    gray, scaleFactor=1.1, minNeighbors=5,
                    minSize=(MIN_FACE_SIZE, MIN_FACE_SIZE),
                )
                n = len(faces)
                faces_per_frame.append(n)
                if n > 0:
                    face_areas.extend([float(w * h) for (_, _, w, h) in faces])
    except Exception as exc:
        logger.error("Frame sampling error: %s", exc)
        findings.append(f"Frame sampling interrupted: {str(exc)[:80]}")
    finally:
        cap.release()

    n = len(brightnesses)
    if n < 2:
        return {
            "facial_score": 0, "temporal_score": 0,
            "compression_score": 0, "video_ml_fake_probability": 0.0,
            "findings": ["Insufficient frames extracted for analysis"],
        }

    # ── ML Frame Analysis ────────────────────────────────────────────────────
    video_ml_fake_probability = 0.0
    if ml_frames and _HAS_ML:
        try:
            probs = [
                _ml_analyze_frame(f).get("fake_probability", 0.0)
                for f in ml_frames
            ]
            video_ml_fake_probability = float(np.mean(probs))
            logger.info(
                "ML video frame analysis: frames=%d  avg_prob=%.3f",
                len(probs), video_ml_fake_probability,
            )
            if video_ml_fake_probability > 0.70:
                findings.append(
                    f"ML model detected possible AI-generated visual patterns "
                    f"(probability={video_ml_fake_probability:.2f})"
                )
        except Exception as exc:
            logger.error("ML video frame analysis failed: %s", exc)

    # ── Temporal Consistency ────────────────────────────────────────────────
    b_arr = np.array(brightnesses)
    b_cv  = _coeff_of_variation(b_arr)

    if b_cv > 0.35:
        temporal_score += 28
        findings.append(
            f"Significant brightness inconsistency across frames (CV={b_cv:.2f}) — "
            "possible video splicing or face-swap seams"
        )
    elif b_cv > 0.20:
        temporal_score += 13
        findings.append(f"Moderate brightness variation across frames (CV={b_cv:.2f})")

    blur_arr = np.array(blurs)
    blur_cv  = _coeff_of_variation(blur_arr)

    if blur_cv > 1.0:
        temporal_score += 22
        findings.append(
            f"High frame-sharpness inconsistency (CV={blur_cv:.2f}) — "
            "mixed real / generated frames suspected"
        )
    elif blur_cv > 0.60:
        temporal_score += 11
        findings.append(f"Noticeable sharpness variation across frames (CV={blur_cv:.2f})")

    edge_arr = np.array(edges_mean)
    edge_cv  = _coeff_of_variation(edge_arr)
    if edge_cv > 0.55:
        temporal_score += 12
        findings.append(
            f"Edge density inconsistency (CV={edge_cv:.2f}) — "
            "blending artefacts may be present"
        )

    # ── Compression Artefacts ────────────────────────────────────────────────
    avg_blur  = float(np.mean(blurs))
    avg_noise = float(np.mean(noise_levels)) if noise_levels else 0.0

    if avg_blur < 15:
        compression_score += 45
        findings.append(
            f"Very low frame sharpness (Laplacian var={avg_blur:.1f}) — "
            "heavy compression artefacts detected"
        )
    elif avg_blur < 40:
        compression_score += 22
        findings.append(f"Moderate compression artefacts (Laplacian var={avg_blur:.1f})")

    if avg_noise > 18:
        compression_score += 28
        findings.append(
            f"High noise level ({avg_noise:.1f}) — codec artefacts or re-encoding detected"
        )
    elif avg_noise > 9:
        compression_score += 12
        findings.append(f"Elevated noise level ({avg_noise:.1f}) — minor encoding artefacts")

    # Resolution check
    if width and height:
        if (width * height) < 90_000:   # below ~300×300
            compression_score += 20
            findings.append(f"Very low resolution ({width}×{height})")

    # ── Facial Analysis ──────────────────────────────────────────────────────
    if faces_per_frame:
        total_checked = len(faces_per_frame)
        frames_with_face = sum(1 for f in faces_per_frame if f > 0)
        face_rate = frames_with_face / total_checked

        if frames_with_face > 0:
            # Intermittent face detection — unstable face-swap
            if 0.05 < face_rate < 0.55:
                facial_score += 22
                findings.append(
                    f"Faces detected in only {face_rate*100:.0f}% of sampled frames — "
                    "unstable face presence (possible face-swap artefact)"
                )

            # Face area jitter
            if len(face_areas) >= 4:
                area_arr = np.array(face_areas)
                area_cv  = _coeff_of_variation(area_arr)
                if area_cv > 0.55:
                    facial_score += 22
                    findings.append(
                        f"Face bounding-box size varies significantly (CV={area_cv:.2f}) — "
                        "GAN instability indicator"
                    )
                elif area_cv > 0.30:
                    facial_score += 10
                    findings.append(
                        f"Moderate face-size variation across frames (CV={area_cv:.2f})"
                    )

            # Multiple faces in single frames
            multi_face_frames = sum(1 for f in faces_per_frame if f > 1)
            if total_checked > 0 and multi_face_frames / total_checked > 0.25:
                facial_score += 10
                findings.append(
                    f"Multiple faces in {multi_face_frames}/{total_checked} frames — "
                    "unexpected; verify source"
                )
    else:
        # No face data collected (cascade unavailable or no faces in video)
        pass

    facial_score      = min(100, max(0, facial_score))
    temporal_score    = min(100, max(0, temporal_score))
    compression_score = min(100, max(0, compression_score))

    return {
        "facial_score":              facial_score,
        "temporal_score":            temporal_score,
        "compression_score":         compression_score,
        "video_ml_fake_probability": round(video_ml_fake_probability, 4),
        "findings":                  findings,
    }


# ── Helpers ─────────────────────────────────────────────────────────────────

def _estimate_noise(gray: np.ndarray) -> float:
    """High-frequency noise estimate via Gaussian residual."""
    try:
        blurred = cv2.GaussianBlur(gray.astype(np.float32), (5, 5), 0)
        diff    = np.abs(gray.astype(np.float32) - blurred)
        return float(np.mean(diff))
    except Exception:
        return 0.0


def _coeff_of_variation(arr: np.ndarray) -> float:
    """std / mean; returns 0 if mean ≈ 0."""
    m = float(np.mean(arr))
    if m < 1e-8:
        return 0.0
    return float(np.std(arr)) / m
