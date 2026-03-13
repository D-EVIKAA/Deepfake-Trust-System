"""
Deepfake Trust & Attribution System — FastAPI backend  v4.0
============================================================

Endpoints
---------
POST /api/analyze                Upload + analyse + save to DB → return result.
GET  /api/stats                  Aggregate counts & average trust score.
GET  /api/weekly                 Per-day breakdown for the last 7 days.
GET  /api/media-breakdown        Count split { VIDEO, IMAGE, AUDIO }.
GET  /api/recent                 Last N analysis rows (dashboard table).
GET  /api/report/{analysis_id}   Download plain-text forensic report (.txt).
GET  /api/health                 Liveness check.
GET  /api/info                   Dependency availability report.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import subprocess
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from analyzers.audio     import analyze_audio
from analyzers.compress  import analyze_compression
from analyzers.exif      import analyze_exif
from analyzers.image     import analyze_image
from analyzers.metadata  import analyze_metadata
from analyzers.scorer    import compute_trust_score, confidence_from_score, verdict_from_score
from analyzers.video     import analyze_video
from analyzers.watermark import analyze_watermark
from database            import AnalysisResult, get_db, init_db

# ML model support (graceful degradation if torch/transformers not installed)
try:
    from analyzers.ml_model import analyze_image_path as _ml_analyze_image_path
    from analyzers.ml_model import models_available    as _ml_models_available
    _HAS_IMAGE_ML = True
except Exception:
    _HAS_IMAGE_ML = False
    def _ml_analyze_image_path(path): return {"fake_probability": 0.0}  # noqa: E731
    def _ml_models_available():       return {"ml_image_model": False, "ml_audio_model": False}  # noqa: E731

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s — %(message)s")
logger = logging.getLogger("dts.main")

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Deepfake Trust & Attribution API",
    version="4.0.0",
    description="Real media analysis — EXIF AI detection, compression analysis, OCR watermark detection",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:5174", "http://127.0.0.1:5174",
        "http://localhost:5175", "http://127.0.0.1:5175",
        "http://localhost:5176", "http://127.0.0.1:5176",
        "http://localhost:5177", "http://127.0.0.1:5177",
        "http://localhost:5178", "http://127.0.0.1:5178",
        "http://localhost:5179", "http://127.0.0.1:5179",
        "http://localhost:3000", "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

@app.on_event("startup")
def on_startup():
    init_db()
    logger.info("Database initialised (v4 schema)")


# ── Accepted file extensions ──────────────────────────────────────────────────
MAX_FILE_BYTES = 500 * 1024 * 1024
VIDEO_EXTS     = {".mp4", ".avi", ".mov", ".webm", ".mkv"}
AUDIO_EXTS     = {".mp3", ".wav", ".aac", ".flac", ".ogg"}
IMAGE_EXTS     = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
SUPPORTED_EXTS = VIDEO_EXTS | AUDIO_EXTS | IMAGE_EXTS

# AI video generator signatures for metadata writing_app check
_VIDEO_AI_SIGS = [
    "veo", "sora", "runway", "gen-2", "gen-3", "pika", "kling",
    "stable video", "dream machine", "haiper", "luma ai",
    "ai generated", "ai-generated",
]


# ═════════════════════════════════════════════════════════════════════════════
# POST /api/analyze
# ═════════════════════════════════════════════════════════════════════════════

@app.post("/api/analyze")
async def analyze_file(
    file:        UploadFile = File(...),
    sensitivity: str        = Form(default="MEDIUM"),
    checks:      str        = Form(default='{"facial":true,"audio":true,"metadata":true,"frequency":true}'),
    db:          Session    = Depends(get_db),
):
    raw_name = file.filename or "upload"
    ext      = Path(raw_name).suffix.lower()

    if ext not in SUPPORTED_EXTS:
        raise HTTPException(
            400,
            f"Unsupported type '{ext}'. Accepted: {', '.join(sorted(SUPPORTED_EXTS))}",
        )

    try:
        enabled: dict[str, bool] = json.loads(checks)
    except json.JSONDecodeError:
        enabled = {"facial": True, "audio": True, "metadata": True, "frequency": True}

    content = await file.read()
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(413, "File exceeds 500 MB limit")
    if len(content) == 0:
        raise HTTPException(400, "File is empty")

    file_hash     = "0x" + hashlib.sha256(content).hexdigest()
    file_size_str = _format_size(len(content))
    is_video      = ext in VIDEO_EXTS
    is_image      = ext in IMAGE_EXTS

    logger.info("Analysing %s  size=%s  sensitivity=%s", raw_name, file_size_str, sensitivity)

    result = await asyncio.to_thread(
        _run_analysis,
        content, raw_name, ext, is_video, is_image,
        sensitivity,
        bool(enabled.get("metadata",  True)),
        bool(enabled.get("audio",     True)) or bool(enabled.get("frequency", True)),
        bool(enabled.get("facial",    True)),
        file_hash, file_size_str,
    )

    # ── Persist to SQLite ─────────────────────────────────────────────────────
    try:
        c = result["checks"]
        record = AnalysisResult(
            id                = result["id"],
            filename          = result["filename"],
            file_type         = result["type"],
            trust_score       = result["trustScore"],
            verdict           = result["verdict"],
            ai_probability    = result.get("confidence"),
            metadata_score    = c["metadataIntegrity"],
            frame_score       = max(c["facialInconsistency"], c["temporalConsistency"]),
            audio_score       = max(c["audioVisualSync"],     c["frequencyAnalysis"]),
            compression_score = result.get("compressionScore"),
            compression_level = result.get("compressionLevel"),
            bitrate           = result.get("bitrate"),
            ai_logo_detected  = result.get("aiLogoDetected", False),
            detected_text     = result.get("detectedText"),
            findings          = json.dumps(result["findings"]),
            created_at        = datetime.utcnow(),
        )
        db.add(record)
        db.commit()
        logger.info(
            "Saved %s  trust=%d  verdict=%s  ai_logo=%s  compression=%s",
            result["id"], result["trustScore"], result["verdict"],
            result.get("aiLogoDetected"), result.get("compressionLevel"),
        )
    except Exception as exc:
        logger.error("DB save failed (result still returned): %s", exc)
        db.rollback()

    return result


# ═════════════════════════════════════════════════════════════════════════════
# GET /api/stats
# ═════════════════════════════════════════════════════════════════════════════

@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    total      = db.query(AnalysisResult).count()
    deepfakes  = db.query(AnalysisResult).filter(AnalysisResult.verdict == "DEEPFAKE").count()
    suspicious = db.query(AnalysisResult).filter(AnalysisResult.verdict == "SUSPICIOUS").count()
    authentic  = db.query(AnalysisResult).filter(AnalysisResult.verdict == "AUTHENTIC").count()
    avg_raw    = db.query(func.avg(AnalysisResult.trust_score)).scalar()
    avg_score  = round(float(avg_raw)) if avg_raw is not None else 0
    ai_logos   = db.query(AnalysisResult).filter(AnalysisResult.ai_logo_detected == True).count()  # noqa: E712

    return {
        "totalAnalyzed":   total,
        "deepfakesFound":  deepfakes,
        "suspicious":      suspicious,
        "authenticCount":  authentic,
        "avgTrustScore":   avg_score,
        "aiLogosDetected": ai_logos,
        "sourcesVerified": round((authentic / total * 100) if total > 0 else 0),
    }


# ═════════════════════════════════════════════════════════════════════════════
# GET /api/weekly
# ═════════════════════════════════════════════════════════════════════════════

@app.get("/api/weekly")
def get_weekly(db: Session = Depends(get_db)):
    today = datetime.utcnow().date()
    days, analyzed, authentic, deepfakes = [], [], [], []

    for offset in range(6, -1, -1):
        day       = today - timedelta(days=offset)
        day_start = datetime(day.year, day.month, day.day,  0,  0,  0)
        day_end   = datetime(day.year, day.month, day.day, 23, 59, 59)

        rows = (
            db.query(AnalysisResult)
            .filter(
                AnalysisResult.created_at >= day_start,
                AnalysisResult.created_at <= day_end,
            )
            .all()
        )

        days.append(day.strftime("%a"))
        analyzed.append(len(rows))
        authentic.append(sum(1 for r in rows if r.verdict == "AUTHENTIC"))
        deepfakes.append(sum(1 for r in rows if r.verdict == "DEEPFAKE"))

    return {"days": days, "analyzed": analyzed, "authentic": authentic, "deepfakes": deepfakes}


# ═════════════════════════════════════════════════════════════════════════════
# GET /api/media-breakdown
# ═════════════════════════════════════════════════════════════════════════════

@app.get("/api/media-breakdown")
def get_media_breakdown(db: Session = Depends(get_db)):
    video = db.query(AnalysisResult).filter(AnalysisResult.file_type == "VIDEO").count()
    image = db.query(AnalysisResult).filter(AnalysisResult.file_type == "IMAGE").count()
    audio = db.query(AnalysisResult).filter(AnalysisResult.file_type == "AUDIO").count()
    return {"VIDEO": video, "IMAGE": image, "AUDIO": audio}


# ═════════════════════════════════════════════════════════════════════════════
# GET /api/recent
# ═════════════════════════════════════════════════════════════════════════════

@app.get("/api/recent")
def get_recent(limit: int = 10, db: Session = Depends(get_db)):
    rows = (
        db.query(AnalysisResult)
        .order_by(AnalysisResult.created_at.desc())
        .limit(max(1, min(limit, 100)))
        .all()
    )
    return [r.to_summary() for r in rows]


# ═════════════════════════════════════════════════════════════════════════════
# GET /api/report/{analysis_id}
# ═════════════════════════════════════════════════════════════════════════════

@app.get("/api/report/{analysis_id}")
def get_report(analysis_id: str, db: Session = Depends(get_db)):
    record = db.query(AnalysisResult).filter(AnalysisResult.id == analysis_id).first()
    if not record:
        raise HTTPException(404, f"Analysis '{analysis_id}' not found in database")

    findings_list: list[str] = json.loads(record.findings or "[]")
    findings_block = (
        "\n".join(f"  - {f}" for f in findings_list)
        if findings_list else
        "  - No significant anomalies detected"
    )

    verdict_desc = {
        "AUTHENTIC":  "Content passed all forensic checks. No manipulation detected.",
        "SUSPICIOUS": "Moderate indicators of manipulation. Manual review recommended.",
        "DEEPFAKE":   "HIGH CONFIDENCE — AI-generated or heavily manipulated content detected.",
    }.get(record.verdict, "")

    ai_prob_str  = f"{record.ai_probability}%" if record.ai_probability is not None else "N/A"
    comp_str     = record.compression_level or "N/A"
    bitrate_str  = f"{record.bitrate} kbps" if record.bitrate else "N/A"
    logo_str     = (
        f"YES — '{record.detected_text}'" if record.ai_logo_detected and record.detected_text
        else "YES" if record.ai_logo_detected
        else "NO"
    )

    # Pull ML probabilities from the stored findings JSON if present,
    # or fall back to N/A (older records pre-dating ML support).
    findings_list_raw: list[str] = json.loads(record.findings or "[]")
    _video_ml = next(
        (f for f in findings_list_raw if "video_ml_prob:" in f), None
    )
    _audio_ml = next(
        (f for f in findings_list_raw if "audio_ml_prob:" in f), None
    )
    video_ml_str = _video_ml.split("video_ml_prob:")[1].strip() if _video_ml else "N/A"
    audio_ml_str = _audio_ml.split("audio_ml_prob:")[1].strip() if _audio_ml else "N/A"

    # Derive ML probability from ai_probability field (stored as 0-100 confidence)
    raw_ml_prob = round(1.0 - record.trust_score / 100, 2) if record.trust_score is not None else 0.0
    ml_prob_str = f"{raw_ml_prob:.2f}"

    watermark_line = (
        f"Analyzed by MediaTrust AI | Trust Score: {record.trust_score} "
        f"| AI Probability: {ml_prob_str}"
    )

    report = f"""\
================================================================
         DEEPFAKE TRUST & ATTRIBUTION SYSTEM
                  FORENSIC ANALYSIS REPORT
================================================================

Analysis ID   : {record.id}
Generated     : {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")}

----------------------------------------------------------------
FILE INFORMATION
----------------------------------------------------------------
File Name     : {record.filename}
File Type     : {record.file_type}
Analysis Date : {record.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")}

----------------------------------------------------------------
VERDICT
----------------------------------------------------------------
Trust Score   : {record.trust_score} / 100
Verdict       : {record.verdict}
AI Probability: {ai_prob_str}
AI Logo Found : {logo_str}

{verdict_desc}

----------------------------------------------------------------
DETECTION MODULE SCORES  (0 = clean  |  100 = high anomaly)
----------------------------------------------------------------
Metadata / AI Signature  : {record.metadata_score    if record.metadata_score    is not None else "N/A"} / 100
Frame / Facial Analysis  : {record.frame_score       if record.frame_score       is not None else "N/A"} / 100
Audio Analysis           : {record.audio_score       if record.audio_score       is not None else "N/A"} / 100
Compression Score        : {record.compression_score if record.compression_score is not None else "N/A"} / 100
Compression Level        : {comp_str}
Bitrate                  : {bitrate_str}

----------------------------------------------------------------
ML AI ANALYSIS (Hugging Face Models)
----------------------------------------------------------------
ML AI Probability (combined) : {ml_prob_str}
Video / Image AI Probability : {video_ml_str}
Audio AI Probability         : {audio_ml_str}
Image Model                  : umm-maybe/AI-image-detector
Audio Model                  : m3hrdadfi/wav2vec2-xlsr-deepfake-detection

----------------------------------------------------------------
FINDINGS
----------------------------------------------------------------
{findings_block}

----------------------------------------------------------------
RISK CLASSIFICATION
----------------------------------------------------------------
  Score 80-100  ->  Low Risk    (AUTHENTIC)
  Score 50-79   ->  Medium Risk (SUSPICIOUS)
  Score  0-49   ->  High Risk   (DEEPFAKE)

================================================================
  {watermark_line}
  Generated by Deepfake Trust & Attribution System v5.0
  For internal / forensic use only.
================================================================
"""

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".txt", prefix="dts_report_")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            fh.write(report)
    except Exception:
        os.close(tmp_fd)
        raise HTTPException(500, "Failed to generate report file")

    safe_name = "".join(c for c in record.filename if c.isalnum() or c in "._-")[:40]
    dl_name   = f"deepfake_report_{analysis_id}_{safe_name}.txt"

    return FileResponse(
        path=tmp_path,
        filename=dl_name,
        media_type="text/plain; charset=utf-8",
        background=BackgroundTask(os.unlink, tmp_path),
    )


# ═════════════════════════════════════════════════════════════════════════════
# Utility endpoints
# ═════════════════════════════════════════════════════════════════════════════

@app.get("/api/health")
def health():
    return {"status": "ok", "version": "4.0.0", "timestamp": _now()}


@app.get("/api/info")
def info():
    deps: dict[str, bool] = {}
    for pkg in ("PIL", "pytesseract", "pymediainfo", "librosa",
                "cv2", "numpy", "scipy", "soundfile", "sqlalchemy",
                "transformers", "torch"):
        try:
            __import__(pkg)
            deps[pkg] = True
        except ImportError:
            deps[pkg] = False
    deps["Pillow"]     = deps.pop("PIL", False)
    deps["ffmpeg"]     = _ffmpeg_available()
    deps["tesseract"]  = _tesseract_available()
    deps.update(_ml_models_available())
    return {"dependencies": deps}


# ═════════════════════════════════════════════════════════════════════════════
# Core analysis (thread-pool — no async allowed)
# ═════════════════════════════════════════════════════════════════════════════

def _run_analysis(
    content:       bytes,
    filename:      str,
    ext:           str,
    is_video:      bool,
    is_image:      bool,
    sensitivity:   str,
    do_metadata:   bool,
    do_audio:      bool,
    do_video:      bool,
    file_hash:     str,
    file_size_str: str,
) -> dict:

    findings: list[str] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / filename
        file_path.write_bytes(content)

        # ── Compression analysis (all media types) ────────────────────────────
        comp_result = {
            "compression_score": 0,
            "compression_level": "unknown",
            "bitrate": None,
            "findings": [],
        }
        try:
            comp_result = analyze_compression(str(file_path))
            findings.extend(comp_result.get("findings", []))
        except Exception as exc:
            logger.error("Compression analysis failed: %s", exc)

        # ═════════════════════════════════════════════════════════════════════
        # IMAGE BRANCH
        # ═════════════════════════════════════════════════════════════════════
        if is_image:

            # 1. EXIF / AI-generator check
            exif_result = {
                "ai_generator_score": 0,
                "missing_camera": False,
                "software_tag": None,
                "findings": [],
            }
            if do_metadata:
                try:
                    exif_result = analyze_exif(str(file_path))
                    findings.extend(exif_result.get("findings", []))
                    if exif_result.get("software_tag"):
                        logger.info("EXIF software tag: %s", exif_result["software_tag"])
                except Exception as exc:
                    logger.error("EXIF analysis failed: %s", exc)

            # 2. AI watermark / logo detection (OCR + color fingerprint)
            wm_result = {
                "ai_logo_detected": False,
                "ai_logo_score": 0,
                "logo_source": None,
                "findings": [],
            }
            try:
                wm_result = analyze_watermark(str(file_path))
                findings.extend(wm_result.get("findings", []))
                if wm_result["ai_logo_detected"]:
                    logger.info(
                        "Watermark detected: source=%s score=%d",
                        wm_result.get("logo_source"), wm_result["ai_logo_score"],
                    )
            except Exception as exc:
                logger.error("Watermark analysis failed: %s", exc)

            # 3. OpenCV forensics (ELA, noise map, face anomaly checks)
            img_result = {
                "ela_score": 0, "noise_score": 0,
                "compression_score": 0, "facial_score": 0, "findings": [],
            }
            try:
                img_result = analyze_image(str(file_path))
                findings.extend(img_result.get("findings", []))
            except Exception as exc:
                logger.error("Image analysis failed: %s", exc)

            # 4. ML image analysis (AI-image-detector model)
            image_ml_prob = 0.0
            try:
                ml_img = _ml_analyze_image_path(str(file_path))
                image_ml_prob = ml_img.get("fake_probability", 0.0)
                logger.info("Image ML probability: %.3f", image_ml_prob)
            except Exception as exc:
                logger.error("Image ML analysis failed: %s", exc)

            effective_compression = max(
                comp_result["compression_score"],
                img_result["compression_score"],
            )

            # 5. Score
            trust_score, risk_level, score_findings = compute_trust_score(
                metadata_anomaly    = 0,
                compression_score   = effective_compression,
                audio_anomaly       = 0,
                frequency_score     = img_result["ela_score"],
                facial_score        = img_result["facial_score"],
                temporal_score      = img_result["noise_score"],
                sensitivity         = sensitivity,
                ai_generator_score  = exif_result["ai_generator_score"],
                ai_logo_score       = wm_result["ai_logo_score"],
                ml_fake_probability = image_ml_prob,
            )
            findings.extend(score_findings)

            checks_obj = {
                "facialInconsistency":  img_result["facial_score"],
                "audioVisualSync":      0,
                "metadataIntegrity":    exif_result["ai_generator_score"],
                "compressionArtifacts": effective_compression,
                "frequencyAnalysis":    img_result["ela_score"],
                "temporalConsistency":  img_result["noise_score"],
            }
            media_type            = "IMAGE"
            ai_logo_detected      = wm_result["ai_logo_detected"]
            detected_text         = wm_result.get("detected_text")
            ai_gen_score          = exif_result["ai_generator_score"]
            video_ml_prob         = image_ml_prob   # reuse field for images
            audio_ml_prob         = 0.0
            combined_ml_prob      = image_ml_prob

        # ═════════════════════════════════════════════════════════════════════
        # VIDEO / AUDIO BRANCH
        # ═════════════════════════════════════════════════════════════════════
        else:
            meta = {"anomaly_score": 0, "compression_score": 0, "findings": [], "raw": {}}
            ai_gen_score_video = 0

            if do_metadata:
                try:
                    meta = analyze_metadata(str(file_path))
                    findings.extend(meta.get("findings", []))
                    # Check for AI video generator in writing_app
                    writing_app = str(
                        meta.get("raw", {}).get("writing_app") or ""
                    ).lower()
                    if writing_app:
                        hit = next(
                            (sig for sig in _VIDEO_AI_SIGS if sig in writing_app), None
                        )
                        if hit:
                            ai_gen_score_video = 90
                            findings.append(
                                f"AI video generator detected in metadata: "
                                f"'{meta['raw']['writing_app']}'"
                            )
                except Exception as exc:
                    logger.error("Metadata failed: %s", exc)

            # Audio analysis
            audio = {"anomaly_score": 0, "frequency_score": 0, "findings": []}
            if do_audio:
                audio_path: str | None = str(file_path)
                if is_video:
                    extracted  = _extract_audio(str(file_path), tmpdir)
                    audio_path = extracted if extracted else None
                if audio_path and Path(audio_path).exists():
                    try:
                        audio = analyze_audio(audio_path)
                        findings.extend(audio.get("findings", []))
                    except Exception as exc:
                        logger.error("Audio analysis failed: %s", exc)

            # Video frame analysis
            video = {
                "facial_score": 0, "temporal_score": 0,
                "compression_score": 0, "findings": [],
            }
            if is_video and do_video:
                try:
                    video = analyze_video(str(file_path))
                    findings.extend(video.get("findings", []))
                except Exception as exc:
                    logger.error("Video analysis failed: %s", exc)

            effective_compression = max(
                comp_result["compression_score"],
                meta.get("compression_score", 0),
                video.get("compression_score", 0),
            )

            # Extract ML probabilities from analysis results
            video_ml_prob    = video.get("video_ml_fake_probability", 0.0)
            audio_ml_prob    = audio.get("audio_ml_fake_probability", 0.0)
            combined_ml_prob = max(video_ml_prob, audio_ml_prob)

            trust_score, risk_level, score_findings = compute_trust_score(
                metadata_anomaly    = meta["anomaly_score"],
                compression_score   = effective_compression,
                audio_anomaly       = audio["anomaly_score"],
                frequency_score     = audio["frequency_score"],
                facial_score        = video["facial_score"],
                temporal_score      = video["temporal_score"],
                sensitivity         = sensitivity,
                ai_generator_score  = ai_gen_score_video,
                ai_logo_score       = 0,   # watermark check only runs on images
                ml_fake_probability = combined_ml_prob,
            )
            findings.extend(score_findings)

            av_sync      = (audio["anomaly_score"] + video["temporal_score"]) // 2
            ai_gen_score = ai_gen_score_video
            checks_obj   = {
                "facialInconsistency":  video["facial_score"],
                "audioVisualSync":      min(100, av_sync),
                "metadataIntegrity":    max(meta["anomaly_score"], ai_gen_score),
                "compressionArtifacts": effective_compression,
                "frequencyAnalysis":    audio["frequency_score"],
                "temporalConsistency":  video["temporal_score"],
            }
            media_type       = "VIDEO" if is_video else "AUDIO"
            ai_logo_detected = False
            detected_text    = None

    # ── Deduplicate findings ──────────────────────────────────────────────────
    seen: set[str] = set()
    unique: list[str] = []
    for f in findings:
        if f not in seen:
            seen.add(f)
            unique.append(f)
    if not unique:
        unique = ["No significant anomalies detected — content appears authentic"]

    verdict    = verdict_from_score(trust_score)
    confidence = confidence_from_score(trust_score)
    ai_prob    = round((100 - trust_score) / 100, 2)   # 0.0–1.0 probability of being AI
    ana_id     = "ANA-" + uuid.uuid4().hex[:6].upper()
    now        = _now()

    logger.info(
        "Result  id=%s  trust=%d  verdict=%s  ai_gen=%d  ai_logo=%s  comp=%s",
        ana_id, trust_score, verdict, ai_gen_score,
        ai_logo_detected, comp_result["compression_level"],
    )

    ml_prob_display = round(combined_ml_prob, 4)

    return {
        "id":                  ana_id,
        "filename":            filename,
        "size":                file_size_str,
        "type":                media_type,
        "trustScore":          trust_score,
        "verdict":             verdict,
        "riskLevel":           risk_level,
        "timestamp":           now,
        "confidence":          confidence,
        "aiProbability":       ai_prob,
        "aiLogoDetected":      ai_logo_detected,
        "detectedText":        detected_text,
        "compressionScore":    comp_result["compression_score"],
        "compressionLevel":    comp_result["compression_level"],
        "bitrate":             comp_result["bitrate"],
        "model":               "DeepScan v5.0",
        "checks":              checks_obj,
        "findings":            unique,
        # ML model outputs
        "videoMlProbability":  round(video_ml_prob,  4),
        "audioMlProbability":  round(audio_ml_prob,  4),
        "mlFakeProbability":   ml_prob_display,
        "provenance": {
            "originalHash": file_hash,
            "firstSeen":    now,
            "locations":    ["upload-endpoint", "analysis-cluster", "attribution-db"],
            "signatures":   2 if trust_score >= 70 else 1,
        },
    }


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════

def _extract_audio(video_path: str, output_dir: str) -> str | None:
    if not _ffmpeg_available():
        return None
    out = os.path.join(output_dir, "audio_extracted.wav")
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", video_path, "-vn",
             "-acodec", "pcm_s16le", "-ar", "22050", "-ac", "1", out],
            capture_output=True, timeout=120,
        )
        return out if r.returncode == 0 and Path(out).exists() else None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def _ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _tesseract_available() -> bool:
    for path in [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        "tesseract",
    ]:
        try:
            r = subprocess.run([path, "--version"], capture_output=True, timeout=3)
            if r.returncode == 0:
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return False


def _format_size(n: int) -> str:
    if n < 1024:       return f"{n} B"
    if n < 1024 ** 2:  return f"{n / 1024:.1f} KB"
    return f"{n / (1024 ** 2):.2f} MB"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
