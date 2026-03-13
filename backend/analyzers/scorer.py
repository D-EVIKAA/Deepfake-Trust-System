"""
Trust score aggregation module.

Starts from 100 and subtracts points based on anomaly signals.

Score bands
-----------
  80-100  Low Risk     AUTHENTIC
  50-79   Medium Risk  SUSPICIOUS
   0-49   High Risk    DEEPFAKE

ai_generator_score is a first-class signal that bypasses the per-category soft
caps and can push the score directly into SUSPICIOUS / DEEPFAKE territory even
when no other forensic signals are raised.
"""
from __future__ import annotations


# Sensitivity multipliers
_MULT: dict[str, float] = {"LOW": 0.65, "MEDIUM": 1.0, "HIGH": 1.40}

# Per-category deduction caps (raised from previous version)
_MAX_METADATA    = 25
_MAX_COMPRESSION = 18
_MAX_AUDIO       = 30
_MAX_FACIAL      = 25
_MAX_TEMPORAL    = 20


def compute_trust_score(
    metadata_anomaly:    int,
    compression_score:   int,
    audio_anomaly:       int,
    frequency_score:     int,
    facial_score:        int,
    temporal_score:      int,
    sensitivity:         str   = "MEDIUM",
    ai_generator_score:  int   = 0,
    ai_logo_score:       int   = 0,
    ml_fake_probability: float = 0.0,
) -> tuple[int, str, list[str]]:
    """
    Compute the final trust score from individual anomaly signals.

    All input scores are in range 0-100 (higher = more anomalous).
    ai_generator_score    = 0-100 from EXIF / metadata AI-tool detection.
    ml_fake_probability   = 0.0-1.0 from Hugging Face ML deepfake models.

    Returns (trust_score, risk_level, score_findings).
    """
    mult     = _MULT.get(sensitivity.upper(), 1.0)
    score    = 100
    findings: list[str] = []

    # ── AI Generator (evaluated first — highest priority signal) ─────────────
    # A confirmed AI-tool tag is definitive; partial signals still matter.
    if ai_generator_score >= 80:
        # Confirmed AI generator tag (e.g. "Gemini", "Stable Diffusion" in EXIF)
        ai_ded = min(65, int(60 * mult))
        score -= ai_ded
        findings.append(
            f"Confirmed AI generator signature detected (-{ai_ded} pts)"
        )
    elif ai_generator_score >= 45:
        # Strong indicators — no camera hardware metadata at all
        ai_ded = min(42, int(38 * mult))
        score -= ai_ded
        findings.append(
            f"Strong AI generation indicators — no camera metadata (-{ai_ded} pts)"
        )
    elif ai_generator_score >= 25:
        # Moderate indicators — no EXIF, stripped metadata
        ai_ded = min(28, int(24 * mult))
        score -= ai_ded
        findings.append(
            f"Missing camera / EXIF metadata — typical of AI-generated images (-{ai_ded} pts)"
        )

    # ── Metadata integrity ────────────────────────────────────────────────────
    meta_ded = _deduct(metadata_anomaly, threshold=20, scale=0.38, cap=_MAX_METADATA, mult=mult)
    if meta_ded:
        score -= meta_ded
        findings.append(f"Metadata integrity issues (-{meta_ded} pts)")

    # ── Compression artefacts ─────────────────────────────────────────────────
    comp_ded = _deduct(compression_score, threshold=28, scale=0.28, cap=_MAX_COMPRESSION, mult=mult)
    if comp_ded:
        score -= comp_ded
        findings.append(f"Compression artefacts detected (-{comp_ded} pts)")

    # ── Audio (use worst of general anomaly and frequency anomaly) ────────────
    effective_audio = max(audio_anomaly, frequency_score)
    audio_ded = _deduct(effective_audio, threshold=18, scale=0.40, cap=_MAX_AUDIO, mult=mult)
    if audio_ded:
        score -= audio_ded
        findings.append(f"Audio anomalies detected (-{audio_ded} pts)")

    # ── Facial ────────────────────────────────────────────────────────────────
    face_ded = _deduct(facial_score, threshold=13, scale=0.35, cap=_MAX_FACIAL, mult=mult)
    if face_ded:
        score -= face_ded
        findings.append(f"Facial inconsistencies found (-{face_ded} pts)")

    # ── Temporal / spatial noise ──────────────────────────────────────────────
    temp_ded = _deduct(temporal_score, threshold=13, scale=0.28, cap=_MAX_TEMPORAL, mult=mult)
    if temp_ded:
        score -= temp_ded
        findings.append(f"Temporal / spatial inconsistencies found (-{temp_ded} pts)")

    # ── AI logo / watermark (second highest priority after EXIF tag) ──────────
    # Penalties per spec: ai_logo_detected → -60 pts
    if ai_logo_score >= 70:
        logo_ded = min(65, int(60 * mult))
        score -= logo_ded
        findings.append(f"AI generator logo / watermark detected (-{logo_ded} pts)")
    elif ai_logo_score >= 35:
        logo_ded = min(30, int(25 * mult))
        score -= logo_ded
        findings.append(f"Possible AI watermark pattern in image (-{logo_ded} pts)")

    # ── ML model probability ──────────────────────────────────────────────────
    # Penalties scale with the model's fake-probability output.
    if ml_fake_probability > 0.85:
        ml_ded = min(60, int(60 * mult))
    elif ml_fake_probability > 0.70:
        ml_ded = min(40, int(40 * mult))
    elif ml_fake_probability > 0.50:
        ml_ded = min(25, int(25 * mult))
    elif ml_fake_probability > 0.30:
        ml_ded = min(10, int(10 * mult))
    else:
        ml_ded = 0

    if ml_ded:
        score -= ml_ded
        findings.append(
            f"ML model detected possible AI-generated media patterns (-{ml_ded} pts)"
        )

    score = max(0, min(100, score))

    if score >= 80:
        risk_level = "Low"
    elif score >= 50:
        risk_level = "Medium"
    else:
        risk_level = "High"

    return score, risk_level, findings


def verdict_from_score(score: int) -> str:
    if score >= 80:
        return "AUTHENTIC"
    if score >= 50:
        return "SUSPICIOUS"
    return "DEEPFAKE"


def confidence_from_score(score: int) -> int:
    """
    Confidence is highest when the score is far from a decision boundary.
    Boundaries: 50 (SUSPICIOUS/DEEPFAKE) and 80 (AUTHENTIC/SUSPICIOUS).
    """
    distances = [abs(score - b) for b in (0, 50, 80, 100)]
    return min(99, 72 + min(distances))


# ── Internal helper ───────────────────────────────────────────────────────────

def _deduct(raw_score: int, threshold: int, scale: float, cap: int, mult: float) -> int:
    """
    Convert an anomaly score into a trust deduction.
    Only triggers when raw_score > threshold.
    """
    if raw_score <= threshold:
        return 0
    excess = raw_score - threshold
    ded    = int(excess * scale * mult)
    return min(cap, max(0, ded))
