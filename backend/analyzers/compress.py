"""
Compression Level Analysis
===========================

Estimates how heavily a media file has been compressed / re-encoded.
Highly compressed or repeatedly re-encoded files are a manipulation indicator.

Strategy
--------
  JPEG   → PIL quantization-table analysis  (no external tool needed)
  PNG    → lossless by definition, score = 0
  Video  → pymediainfo bitrate (kbps)
  Audio  → pymediainfo bitrate (kbps)
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# bitrate thresholds (kbps)
_VID_VERY_HIGH = 200     # < 200 kbps  → extreme compression
_VID_HIGH      = 600     # 200–600 kbps → heavy
_VID_MEDIUM    = 2_500   # 600–2500 kbps → moderate

_AUD_VERY_HIGH = 64      # < 64 kbps   → extreme
_AUD_HIGH      = 128     # 64–128 kbps → heavy

try:
    from pymediainfo import MediaInfo
    HAS_MEDIAINFO = True
except ImportError:
    HAS_MEDIAINFO = False
    logger.warning("pymediainfo not installed — media compression check skipped")

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def analyze_compression(file_path: str) -> dict:
    """
    Returns
    -------
    dict:
        compression_score : int   0-100  (higher = more suspicious)
        compression_level : str   "lossless" | "low" | "medium" | "high" | "very_high"
        bitrate           : int | None  (kbps)
        findings          : list[str]
    """
    ext = Path(file_path).suffix.lower()

    if ext in (".jpg", ".jpeg"):
        return _jpeg_compression(file_path)

    if ext == ".png":
        return {
            "compression_score": 0,
            "compression_level": "lossless",
            "bitrate": None,
            "findings": [],
        }

    if HAS_MEDIAINFO:
        return _media_compression(file_path)

    return {
        "compression_score": 0,
        "compression_level": "unknown",
        "bitrate": None,
        "findings": ["Compression analysis unavailable (pymediainfo not installed)"],
    }


# ── JPEG ─────────────────────────────────────────────────────────────────────

def _jpeg_compression(file_path: str) -> dict:
    """Read JPEG quantization tables via PIL — higher average = more compression."""
    if not HAS_PIL:
        return {"compression_score": 0, "compression_level": "unknown",
                "bitrate": None, "findings": []}
    try:
        img     = Image.open(file_path)
        qtables = img.quantization   # dict: table_id → list[64 values]

        if not qtables:
            return {"compression_score": 15, "compression_level": "unknown",
                    "bitrate": None,
                    "findings": ["JPEG quantization tables absent — unusual"]}

        all_vals = [v for tbl in qtables.values() for v in tbl]
        avg_q    = sum(all_vals) / len(all_vals)

        # avg_q ranges:  < 5=quality≥95   5–15=80–95   15–30=60–80
        #                30–50=40–60       >50=quality<40
        if avg_q > 50:
            return {
                "compression_score": 75,
                "compression_level": "very_high",
                "bitrate": None,
                "findings": [
                    f"Very high JPEG compression detected (avg quant={avg_q:.0f}) — "
                    "heavy quality loss, consistent with re-encoding after manipulation"
                ],
            }
        if avg_q > 30:
            return {
                "compression_score": 50,
                "compression_level": "high",
                "bitrate": None,
                "findings": [
                    f"High JPEG compression (avg quant={avg_q:.0f}) — "
                    "significant quality reduction"
                ],
            }
        if avg_q > 15:
            return {
                "compression_score": 20,
                "compression_level": "medium",
                "bitrate": None,
                "findings": [f"Moderate JPEG compression (avg quant={avg_q:.0f})"],
            }
        return {"compression_score": 0, "compression_level": "low",
                "bitrate": None, "findings": []}

    except Exception as exc:
        logger.warning("JPEG compression analysis failed: %s", exc)
        return {"compression_score": 0, "compression_level": "unknown",
                "bitrate": None, "findings": []}


# ── Video / Audio via pymediainfo ────────────────────────────────────────────

def _media_compression(file_path: str) -> dict:
    findings: list[str] = []
    try:
        info = MediaInfo.parse(file_path)
    except Exception as exc:
        logger.warning("pymediainfo parse error: %s", exc)
        return {"compression_score": 15, "compression_level": "unknown",
                "bitrate": None,
                "findings": ["Media container could not be parsed — possible corruption"]}

    video = next((t for t in info.tracks if t.track_type == "Video"), None)
    audio = next((t for t in info.tracks if t.track_type == "Audio"), None)

    bitrate_kbps: int | None = None
    score  = 0
    level  = "low"

    if video:
        raw_br = getattr(video, "bit_rate", None)
        if raw_br:
            try:
                bitrate_kbps = int(raw_br) // 1000
            except (TypeError, ValueError):
                pass

        if bitrate_kbps is not None:
            if bitrate_kbps < _VID_VERY_HIGH:
                score, level = 80, "very_high"
                findings.append(
                    f"Very high video compression ({bitrate_kbps} kbps) — "
                    "possible re-encoding after manipulation or AI generation"
                )
            elif bitrate_kbps < _VID_HIGH:
                score, level = 55, "high"
                findings.append(
                    f"High video compression detected ({bitrate_kbps} kbps)"
                )
            elif bitrate_kbps < _VID_MEDIUM:
                score, level = 20, "medium"
                findings.append(f"Moderate video compression ({bitrate_kbps} kbps)")
        else:
            score = 15
            findings.append("Video bitrate unavailable — format may have been re-packaged")

    elif audio:
        raw_br = getattr(audio, "bit_rate", None)
        if raw_br:
            try:
                bitrate_kbps = int(raw_br) // 1000
            except (TypeError, ValueError):
                pass

        if bitrate_kbps is not None:
            if bitrate_kbps < _AUD_VERY_HIGH:
                score, level = 65, "very_high"
                findings.append(
                    f"Very high audio compression ({bitrate_kbps} kbps) — "
                    "possible AI-synthesised or heavily re-encoded audio"
                )
            elif bitrate_kbps < _AUD_HIGH:
                score, level = 35, "high"
                findings.append(f"High audio compression ({bitrate_kbps} kbps)")

    return {
        "compression_score": score,
        "compression_level": level,
        "bitrate":           bitrate_kbps,
        "findings":          findings,
    }
