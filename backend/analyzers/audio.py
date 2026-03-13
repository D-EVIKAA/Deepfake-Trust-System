"""
Audio analysis module.
Uses librosa + numpy to extract spectral features and flag deepfake indicators.

What we look for:
  - Unnaturally consistent zero-crossing rate (voice clones are too stable)
  - Spectral flatness above natural speech range (AI-gen audio is flatter)
  - MFCC variance too low (synthetic voices lack natural expressiveness)
  - Compressed dynamic range (over-produced / post-processed audio)
  - Audio clipping (aggressive encoding)
  - Excessive silence blocks (editing artifacts)
"""
from __future__ import annotations
import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

try:
    import librosa
    HAS_LIBROSA = True
except ImportError:
    HAS_LIBROSA = False
    logger.warning("librosa not installed — audio analysis unavailable")

try:
    from analyzers.ml_model import analyze_audio_file as _ml_analyze_audio
    _HAS_ML = True
except Exception:
    _HAS_ML = False
    def _ml_analyze_audio(path):  # noqa: F811
        return {"fake_probability": 0.0}


# ── Thresholds ─────────────────────────────────────────────────────────────
# Natural human speech reference ranges (empirically derived)
ZCR_LOW   = 0.012   # below this = too smooth / synthetic
ZCR_HIGH  = 0.22    # above this = too noisy / clipped
ZCR_STD_LOW = 0.004 # very low std = unnaturally consistent

SC_LOW  = 300    # Hz — below this = muffled / very low-freq content
SC_HIGH = 7000   # Hz — above this = unusual for speech
SC_STD_LOW = 100 # Hz — very stable centroid = synthetic

FLATNESS_WARN = 0.30  # slight concern
FLATNESS_HIGH = 0.42  # strong indicator of synthetic / white-noise-like audio

MFCC_STD_LOW  = 8.0   # strong indicator of clone
MFCC_STD_MED  = 12.0  # mild indicator

DYNAMIC_RANGE_LOW = 0.25  # rms_std / rms_mean — too compressed

CLIPPING_WARN  = 0.008  # 0.8 % samples clipped
SILENCE_HIGH   = 0.40   # 40 % silence = lots of editing


def analyze_audio(audio_path: str, max_duration: float = 45.0) -> dict:
    """
    Analyze audio for manipulation / deepfake indicators.

    Parameters
    ----------
    audio_path   : path to WAV / MP3 / extracted audio file
    max_duration : only analyze this many seconds (perf limit)

    Returns
    -------
    dict with keys:
        anomaly_score              : int   0-100
        frequency_score            : int   0-100  (spectral domain anomalies)
        audio_ml_fake_probability  : float 0.0-1.0
        findings                   : list[str]
    """
    findings: list[str] = []
    anomaly_score  = 0
    frequency_score = 0

    if not HAS_LIBROSA:
        return {"anomaly_score": 0, "frequency_score": 0,
                "audio_ml_fake_probability": 0.0,
                "findings": ["librosa not installed — audio analysis skipped"]}

    if not Path(audio_path).exists():
        return {"anomaly_score": 0, "frequency_score": 0,
                "audio_ml_fake_probability": 0.0,
                "findings": ["Audio file not found"]}

    # ── Load audio ─────────────────────────────────────────────────────────
    try:
        y, sr = librosa.load(audio_path, sr=None, mono=True, duration=max_duration)
    except Exception as exc:
        logger.warning("librosa.load failed: %s", exc)
        return {"anomaly_score": 20, "frequency_score": 20,
                "audio_ml_fake_probability": 0.0,
                "findings": [f"Audio load error — possibly corrupted: {str(exc)[:80]}"]}

    if len(y) < sr * 0.5:
        return {"anomaly_score": 0, "frequency_score": 0,
                "audio_ml_fake_probability": 0.0,
                "findings": ["Audio too short for meaningful analysis (< 0.5 s)"]}

    try:
        # ── Zero Crossing Rate ────────────────────────────────────────────
        zcr_arr   = librosa.feature.zero_crossing_rate(y)[0]
        zcr_mean  = float(np.mean(zcr_arr))
        zcr_std   = float(np.std(zcr_arr))

        if zcr_mean < ZCR_LOW:
            anomaly_score += 18
            findings.append(
                f"Abnormally low zero-crossing rate ({zcr_mean:.4f}) — "
                "may indicate synthetic / over-smoothed audio"
            )
        elif zcr_mean > ZCR_HIGH:
            anomaly_score += 15
            findings.append(
                f"Abnormally high zero-crossing rate ({zcr_mean:.4f}) — "
                "possible audio manipulation or heavy noise"
            )

        if zcr_std < ZCR_STD_LOW:
            anomaly_score += 10
            findings.append(
                "Zero-crossing rate shows unnatural temporal consistency "
                "(natural speech is irregular)"
            )

        # ── Spectral Centroid ─────────────────────────────────────────────
        sc_arr  = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
        sc_mean = float(np.mean(sc_arr))
        sc_std  = float(np.std(sc_arr))

        if sc_mean < SC_LOW or sc_mean > SC_HIGH:
            frequency_score += 25
            findings.append(
                f"Spectral centroid {sc_mean:.0f} Hz is outside the normal "
                f"speech range ({SC_LOW}–{SC_HIGH} Hz)"
            )

        if sc_std < SC_STD_LOW and len(y) > sr * 2:
            frequency_score += 20
            findings.append(
                f"Spectral centroid std {sc_std:.1f} Hz is suspiciously low — "
                "natural speech has high frequency variation"
            )

        # ── Spectral Flatness ─────────────────────────────────────────────
        # Measures how noise-like the spectrum is (0 = pure tone, 1 = white noise)
        # Human speech: 0.01–0.25 | AI-generated: often > 0.35
        flatness_arr  = librosa.feature.spectral_flatness(y=y)[0]
        flatness_mean = float(np.mean(flatness_arr))

        if flatness_mean > FLATNESS_HIGH:
            anomaly_score  += 22
            frequency_score += 28
            findings.append(
                f"High spectral flatness ({flatness_mean:.3f}) — "
                "signal resembles synthetic or heavily processed audio"
            )
        elif flatness_mean > FLATNESS_WARN:
            anomaly_score  += 10
            frequency_score += 12
            findings.append(
                f"Elevated spectral flatness ({flatness_mean:.3f}) — "
                "slightly unusual for natural speech"
            )

        # ── MFCC Variance Analysis ────────────────────────────────────────
        # Voice clones are unnaturally consistent across frames
        mfcc          = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
        mfcc_stds     = np.std(mfcc, axis=1)
        avg_mfcc_std  = float(np.mean(mfcc_stds))

        if avg_mfcc_std < MFCC_STD_LOW:
            anomaly_score += 22
            findings.append(
                f"MFCC coefficient variance ({avg_mfcc_std:.2f}) is abnormally low — "
                "possible voice clone or text-to-speech synthesis"
            )
        elif avg_mfcc_std < MFCC_STD_MED:
            anomaly_score += 10
            findings.append(
                f"MFCC variance ({avg_mfcc_std:.2f}) slightly below natural range — "
                "minor speech irregularity"
            )

        # ── Dynamic Range ─────────────────────────────────────────────────
        rms_arr  = librosa.feature.rms(y=y)[0]
        rms_mean = float(np.mean(rms_arr))
        rms_std  = float(np.std(rms_arr))

        if rms_mean > 1e-5:
            dyn_range = rms_std / rms_mean
            if dyn_range < DYNAMIC_RANGE_LOW:
                anomaly_score += 15
                findings.append(
                    f"Audio dynamic range is unnaturally compressed "
                    f"(ratio {dyn_range:.3f}) — indicates heavy post-processing"
                )

        # ── Clipping Detection ────────────────────────────────────────────
        clipping_ratio = float(np.mean(np.abs(y) > 0.97))
        if clipping_ratio > CLIPPING_WARN:
            anomaly_score += 10
            findings.append(
                f"Audio clipping detected ({clipping_ratio*100:.1f}% of samples at saturation)"
            )

        # ── Silence Analysis ──────────────────────────────────────────────
        silence_threshold = 0.001
        silence_ratio = float(np.mean(np.abs(y) < silence_threshold))
        if silence_ratio > SILENCE_HIGH:
            anomaly_score += 10
            findings.append(
                f"Excessive silence ({silence_ratio*100:.0f}% of audio) — "
                "may indicate spliced / edited content"
            )

        # ── Spectral Rolloff ──────────────────────────────────────────────
        rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr, roll_percent=0.85)[0]
        rolloff_mean = float(np.mean(rolloff))
        # Typical speech rolloff: 2 kHz – 8 kHz
        if rolloff_mean < 1500 or rolloff_mean > 16000:
            frequency_score += 15
            findings.append(
                f"Spectral rolloff {rolloff_mean:.0f} Hz is unusual for human speech"
            )

    except Exception as exc:
        logger.error("Audio feature extraction error: %s", exc)
        findings.append(f"Partial audio analysis error — {str(exc)[:80]}")

    anomaly_score   = min(100, max(0, anomaly_score))
    frequency_score = min(100, max(0, frequency_score))

    # ── ML Audio Analysis ─────────────────────────────────────────────────────
    audio_ml_fake_probability = 0.0
    if _HAS_ML:
        try:
            ml_result = _ml_analyze_audio(audio_path)
            audio_ml_fake_probability = ml_result.get("fake_probability", 0.0)
            logger.info("ML audio analysis: prob=%.3f", audio_ml_fake_probability)
            if audio_ml_fake_probability > 0.70:
                findings.append(
                    f"ML model detected possible AI-synthesised audio patterns "
                    f"(probability={audio_ml_fake_probability:.2f})"
                )
        except Exception as exc:
            logger.error("ML audio analysis failed: %s", exc)

    return {
        "anomaly_score":             anomaly_score,
        "frequency_score":           frequency_score,
        "audio_ml_fake_probability": round(audio_ml_fake_probability, 4),
        "findings":                  findings,
    }
