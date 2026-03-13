"""
Metadata analysis module.
Uses pymediainfo to extract file metadata and flag suspicious indicators.
"""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

try:
    from pymediainfo import MediaInfo
    HAS_MEDIAINFO = True
except ImportError:
    HAS_MEDIAINFO = False
    logger.warning("pymediainfo not installed — metadata analysis unavailable")


def analyze_metadata(file_path: str) -> dict:
    """
    Analyze file metadata for deepfake / tampering indicators.

    Returns
    -------
    dict with keys:
        anomaly_score   : int  0-100  (higher = more suspicious)
        compression_score: int 0-100
        findings        : list[str]  human-readable flags
        raw             : dict       raw metadata values for reference
    """
    findings: list[str] = []
    anomaly_score = 0
    compression_score = 0
    raw: dict = {}

    if not HAS_MEDIAINFO:
        return {
            "anomaly_score": 0,
            "compression_score": 0,
            "findings": ["pymediainfo unavailable — metadata check skipped"],
            "raw": {},
        }

    try:
        media_info = MediaInfo.parse(file_path)
    except Exception as exc:
        logger.error("MediaInfo parse failed: %s", exc)
        return {
            "anomaly_score": 30,
            "compression_score": 0,
            "findings": ["Metadata could not be parsed — file may be corrupted or tampered"],
            "raw": {},
        }

    general_track = None
    video_track = None
    audio_track = None

    for track in media_info.tracks:
        t = track.track_type
        if t == "General":
            general_track = track
        elif t == "Video":
            video_track = track
        elif t == "Audio":
            audio_track = track

    # ── General track ──────────────────────────────────────────────────────
    if general_track is None:
        return {
            "anomaly_score": 35,
            "compression_score": 0,
            "findings": ["General metadata track is entirely missing"],
            "raw": {},
        }

    writing_app = (
        getattr(general_track, "writing_application", None)
        or getattr(general_track, "encoded_application", None)
    )
    writing_lib = getattr(general_track, "writing_library", None)
    encoded_date = (
        getattr(general_track, "encoded_date", None)
        or getattr(general_track, "tagged_date", None)
    )
    file_format = getattr(general_track, "format", None)
    duration_ms = getattr(general_track, "duration", None)

    raw["writing_app"] = writing_app
    raw["writing_lib"] = writing_lib
    raw["encoded_date"] = encoded_date
    raw["format"] = file_format
    raw["duration_ms"] = duration_ms

    # Missing encoder
    if not writing_app and not writing_lib:
        anomaly_score += 20
        findings.append("Encoder / writing-application metadata is absent")
    else:
        app_str = str(writing_app or writing_lib).lower()
        SUSPICIOUS_ENCODERS = ("unknown", "generic", "deepfake", "synthesis", "gan", "ai-gen")
        if any(kw in app_str for kw in SUSPICIOUS_ENCODERS):
            anomaly_score += 25
            findings.append(f"Suspicious encoder string: '{writing_app or writing_lib}'")

    # Missing creation date
    if not encoded_date:
        anomaly_score += 10
        findings.append("Creation / encoding date metadata is absent")

    # Missing duration
    if not duration_ms:
        anomaly_score += 10
        findings.append("Duration metadata is missing")

    # ── Video track ────────────────────────────────────────────────────────
    if video_track:
        bit_rate = _safe_int(getattr(video_track, "bit_rate", None))
        codec = (
            getattr(video_track, "codec_id", None)
            or getattr(video_track, "format", None)
        )
        width = _safe_int(getattr(video_track, "width", None))
        height = _safe_int(getattr(video_track, "height", None))
        frame_rate = _safe_float(getattr(video_track, "frame_rate", None))

        raw.update({"video_bitrate": bit_rate, "codec": codec, "resolution": f"{width}x{height}", "fps": frame_rate})

        if bit_rate is not None:
            if bit_rate < 200_000:          # < 200 kbps
                anomaly_score += 15
                compression_score += 55
                findings.append(f"Heavy video compression (bitrate {bit_rate//1000} kbps — expected ≥ 200 kbps)")
            elif bit_rate < 500_000:        # 200–500 kbps
                compression_score += 30
                findings.append(f"Low video bitrate detected ({bit_rate//1000} kbps)")
            elif bit_rate > 100_000_000:    # > 100 Mbps
                anomaly_score += 10
                findings.append(f"Unusually high bitrate ({bit_rate//1_000_000} Mbps) — possible padding")
        else:
            anomaly_score += 8
            compression_score += 25
            findings.append("Video bitrate information unavailable")

        if not codec:
            anomaly_score += 10
            findings.append("Video codec information is missing")

        # Non-standard resolution (deepfake outputs often have unusual dims)
        if width and height:
            if width % 16 != 0 or height % 16 != 0:
                anomaly_score += 8
                findings.append(f"Non-standard resolution {width}×{height} (not divisible by 16)")

        if frame_rate and not (14 <= frame_rate <= 121):
            anomaly_score += 8
            findings.append(f"Unusual frame rate: {frame_rate:.1f} fps")

    # ── Audio track ────────────────────────────────────────────────────────
    if audio_track:
        audio_br = _safe_int(getattr(audio_track, "bit_rate", None))
        audio_codec = getattr(audio_track, "format", None)
        channels = _safe_int(getattr(audio_track, "channel_s", None))

        raw.update({"audio_bitrate": audio_br, "audio_codec": audio_codec, "channels": channels})

        if audio_br is not None and audio_br < 64_000:
            compression_score += 40
            findings.append(f"Heavy audio compression (bitrate {audio_br//1000} kbps)")

        if not audio_codec:
            anomaly_score += 5
            findings.append("Audio codec information missing")

    anomaly_score     = min(100, max(0, anomaly_score))
    compression_score = min(100, max(0, compression_score))

    return {
        "anomaly_score": anomaly_score,
        "compression_score": compression_score,
        "findings": findings,
        "raw": raw,
    }


def _safe_int(val) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _safe_float(val) -> float | None:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None
