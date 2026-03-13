"""
Deepfake Trust & Attribution System — Streamlit UI
===================================================

Pages
-----
  Home / Analyzer  — upload & analyse media files
  Activity Log     — table of all past analyses stored in the DB
  Evidence DB      — detailed metadata browser with per-file drill-down
  Settings         — configure watermark text, thresholds, sensitivity

Run with:
    cd backend
    streamlit run app.py
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Suppress Streamlit's torch.classes file-watcher crash (cosmetic only, non-fatal)
os.environ.setdefault("STREAMLIT_SERVER_FILE_WATCHER_TYPE", "none")

import pandas as pd
import streamlit as st

# ── Make sure the backend directory is on the path ───────────────────────────
_BACKEND_DIR = Path(__file__).parent.resolve()
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from database import AnalysisResult, SessionLocal, init_db  # noqa: E402
from analyzers.audio     import analyze_audio       # noqa: E402
from analyzers.compress  import analyze_compression  # noqa: E402
from analyzers.exif      import analyze_exif        # noqa: E402
from analyzers.image     import analyze_image       # noqa: E402
from analyzers.metadata  import analyze_metadata    # noqa: E402
from analyzers.scorer    import (                   # noqa: E402
    compute_trust_score, confidence_from_score, verdict_from_score,
)
from analyzers.video     import analyze_video       # noqa: E402
from analyzers.watermark import analyze_watermark   # noqa: E402

try:
    from analyzers.ml_model import analyze_image_path as _ml_image, analyze_audio_file as _ml_audio
    _HAS_ML = True
except Exception:
    _HAS_ML = False
    def _ml_image(p): return {"fake_probability": 0.0}   # noqa: E731
    def _ml_audio(p): return {"fake_probability": 0.0}   # noqa: E731

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
SETTINGS_PATH = _BACKEND_DIR / "settings.json"
VIDEO_EXTS    = {".mp4", ".avi", ".mov", ".webm", ".mkv"}
AUDIO_EXTS    = {".mp3", ".wav", ".aac", ".flac", ".ogg"}
IMAGE_EXTS    = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

_VIDEO_AI_SIGS = [
    "veo", "sora", "runway", "gen-2", "gen-3", "pika", "kling",
    "stable video", "dream machine", "haiper", "luma ai",
    "ai generated", "ai-generated",
]

# ── Default settings ──────────────────────────────────────────────────────────
DEFAULT_SETTINGS: dict = {
    "watermark_text":          "Analyzed by MediaTrust AI",
    "authentic_threshold":     80,
    "suspicious_threshold":    50,
    "authentic_label":         "AUTHENTIC",
    "suspicious_label":        "SUSPICIOUS",
    "deepfake_label":          "DEEPFAKE",
    "default_sensitivity":     "MEDIUM",
    "show_ml_scores":          True,
    "max_activity_rows":       200,
}


# ══════════════════════════════════════════════════════════════════════════════
# Settings helpers
# ══════════════════════════════════════════════════════════════════════════════

def load_settings() -> dict:
    if SETTINGS_PATH.exists():
        try:
            with open(SETTINGS_PATH, encoding="utf-8") as f:
                saved = json.load(f)
            return {**DEFAULT_SETTINGS, **saved}
        except Exception:
            pass
    return dict(DEFAULT_SETTINGS)


def save_settings(s: dict) -> None:
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2)
    except Exception as exc:
        st.error(f"Could not save settings: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# Database helpers
# ══════════════════════════════════════════════════════════════════════════════

def _db_all_results() -> list[AnalysisResult]:
    db = SessionLocal()
    try:
        return db.query(AnalysisResult).order_by(AnalysisResult.created_at.desc()).all()
    finally:
        db.close()


def _db_get(analysis_id: str) -> AnalysisResult | None:
    db = SessionLocal()
    try:
        return db.query(AnalysisResult).filter(AnalysisResult.id == analysis_id).first()
    finally:
        db.close()


def _db_save(record: AnalysisResult) -> None:
    db = SessionLocal()
    try:
        db.add(record)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("DB save failed: %s", exc)
    finally:
        db.close()


def _rows_to_df(rows: list[AnalysisResult]) -> pd.DataFrame:
    data = []
    for r in rows:
        data.append({
            "ID":               r.id,
            "File Name":        r.filename,
            "Type":             r.file_type,
            "Trust Score":      r.trust_score,
            "Verdict":          r.verdict,
            "AI Probability":   r.ai_probability,
            "Compression":      r.compression_level or "—",
            "AI Logo":          "Yes" if r.ai_logo_detected else "No",
            "Detected Text":    r.detected_text or "—",
            "Metadata Score":   r.metadata_score,
            "Frame Score":      r.frame_score,
            "Audio Score":      r.audio_score,
            "Timestamp":        r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "—",
        })
    return pd.DataFrame(data)


# ══════════════════════════════════════════════════════════════════════════════
# Risk / verdict helpers (respect Settings thresholds)
# ══════════════════════════════════════════════════════════════════════════════

def score_to_verdict(score: int, s: dict) -> str:
    if score >= s["authentic_threshold"]:
        return s["authentic_label"]
    if score >= s["suspicious_threshold"]:
        return s["suspicious_label"]
    return s["deepfake_label"]


def score_to_risk(score: int, s: dict) -> str:
    if score >= s["authentic_threshold"]:
        return "Low"
    if score >= s["suspicious_threshold"]:
        return "Medium"
    return "High"


def verdict_color(verdict: str, s: dict) -> str:
    if verdict == s["authentic_label"]:
        return "green"
    if verdict == s["suspicious_label"]:
        return "orange"
    return "red"


# ══════════════════════════════════════════════════════════════════════════════
# Analysis runner
# ══════════════════════════════════════════════════════════════════════════════

def run_analysis(
    file_bytes: bytes,
    filename:   str,
    sensitivity: str,
    settings:   dict,
) -> dict:
    """Run the full analysis pipeline and return a result dict."""
    ext      = Path(filename).suffix.lower()
    is_video = ext in VIDEO_EXTS
    is_image = ext in IMAGE_EXTS
    findings: list[str] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        fp = Path(tmpdir) / filename
        fp.write_bytes(file_bytes)

        # ── Compression (all media) ─────────────────────────────────────────
        comp = {"compression_score": 0, "compression_level": "unknown", "bitrate": None, "findings": []}
        try:
            comp = analyze_compression(str(fp))
            findings.extend(comp.get("findings", []))
        except Exception as exc:
            logger.error("Compression: %s", exc)

        if is_image:
            # EXIF / AI generator
            exif = {"ai_generator_score": 0, "missing_camera": False, "software_tag": None, "findings": []}
            try:
                exif = analyze_exif(str(fp))
                findings.extend(exif.get("findings", []))
            except Exception as exc:
                logger.error("EXIF: %s", exc)

            # Watermark / logo
            wm = {"ai_logo_detected": False, "ai_logo_score": 0, "findings": []}
            try:
                wm = analyze_watermark(str(fp))
                findings.extend(wm.get("findings", []))
            except Exception as exc:
                logger.error("Watermark: %s", exc)

            # OpenCV forensics
            img = {"ela_score": 0, "noise_score": 0, "compression_score": 0, "facial_score": 0, "findings": []}
            try:
                img = analyze_image(str(fp))
                findings.extend(img.get("findings", []))
            except Exception as exc:
                logger.error("Image: %s", exc)

            # ML image analysis
            img_ml_prob = 0.0
            if _HAS_ML and settings.get("show_ml_scores", True):
                try:
                    img_ml_prob = _ml_image(str(fp)).get("fake_probability", 0.0)
                except Exception as exc:
                    logger.error("ML image: %s", exc)

            eff_comp = max(comp["compression_score"], img["compression_score"])
            trust, risk, sf = compute_trust_score(
                metadata_anomaly    = 0,
                compression_score   = eff_comp,
                audio_anomaly       = 0,
                frequency_score     = img["ela_score"],
                facial_score        = img["facial_score"],
                temporal_score      = img["noise_score"],
                sensitivity         = sensitivity,
                ai_generator_score  = exif["ai_generator_score"],
                ai_logo_score       = wm["ai_logo_score"],
                ml_fake_probability = img_ml_prob,
            )
            findings.extend(sf)

            return {
                "trust_score":        trust,
                "risk_level":         risk,
                "verdict":            verdict_from_score(trust),
                "confidence":         confidence_from_score(trust),
                "ai_probability":     confidence_from_score(trust),
                "media_type":         "IMAGE",
                "ai_logo_detected":   wm["ai_logo_detected"],
                "ai_logo_score":      wm["ai_logo_score"],
                "detected_text":      wm.get("detected_text"),
                "compression_score":  eff_comp,
                "compression_level":  comp["compression_level"],
                "bitrate":            comp["bitrate"],
                "metadata_score":     exif["ai_generator_score"],
                "frame_score":        img["facial_score"],
                "audio_score":        0,
                "video_ml_prob":      img_ml_prob,
                "audio_ml_prob":      0.0,
                "ml_fake_probability": img_ml_prob,
                "findings":           findings,
                "software_tag":       exif.get("software_tag"),
            }

        else:
            # Metadata
            meta = {"anomaly_score": 0, "compression_score": 0, "findings": [], "raw": {}}
            ai_gen_video = 0
            try:
                meta = analyze_metadata(str(fp))
                findings.extend(meta.get("findings", []))
                app_str = str(meta.get("raw", {}).get("writing_app") or "").lower()
                if any(sig in app_str for sig in _VIDEO_AI_SIGS):
                    ai_gen_video = 90
                    findings.append(f"AI video generator detected in metadata: '{meta['raw']['writing_app']}'")
            except Exception as exc:
                logger.error("Metadata: %s", exc)

            # Audio
            audio = {"anomaly_score": 0, "frequency_score": 0, "audio_ml_fake_probability": 0.0, "findings": []}
            audio_path_str: str | None = str(fp)
            if is_video:
                extracted = _extract_audio(str(fp), tmpdir)
                audio_path_str = extracted if extracted else None

            if audio_path_str and Path(audio_path_str).exists():
                try:
                    audio = analyze_audio(audio_path_str)
                    findings.extend(audio.get("findings", []))
                except Exception as exc:
                    logger.error("Audio: %s", exc)

            # Video frames
            video = {"facial_score": 0, "temporal_score": 0, "compression_score": 0,
                     "video_ml_fake_probability": 0.0, "findings": []}
            if is_video:
                try:
                    video = analyze_video(str(fp))
                    findings.extend(video.get("findings", []))
                except Exception as exc:
                    logger.error("Video: %s", exc)

            video_ml = video.get("video_ml_fake_probability", 0.0)
            audio_ml = audio.get("audio_ml_fake_probability", 0.0)
            combined_ml = max(video_ml, audio_ml)

            eff_comp = max(comp["compression_score"], meta.get("compression_score", 0),
                           video.get("compression_score", 0))

            trust, risk, sf = compute_trust_score(
                metadata_anomaly    = meta["anomaly_score"],
                compression_score   = eff_comp,
                audio_anomaly       = audio["anomaly_score"],
                frequency_score     = audio["frequency_score"],
                facial_score        = video["facial_score"],
                temporal_score      = video["temporal_score"],
                sensitivity         = sensitivity,
                ai_generator_score  = ai_gen_video,
                ai_logo_score       = 0,
                ml_fake_probability = combined_ml,
            )
            findings.extend(sf)

            return {
                "trust_score":         trust,
                "risk_level":          risk,
                "verdict":             verdict_from_score(trust),
                "confidence":          confidence_from_score(trust),
                "ai_probability":      confidence_from_score(trust),
                "media_type":          "VIDEO" if is_video else "AUDIO",
                "ai_logo_detected":    False,
                "ai_logo_score":       0,
                "detected_text":       None,
                "compression_score":   eff_comp,
                "compression_level":   comp["compression_level"],
                "bitrate":             comp["bitrate"],
                "metadata_score":      max(meta["anomaly_score"], ai_gen_video),
                "frame_score":         max(video["facial_score"], video["temporal_score"]),
                "audio_score":         max(audio["anomaly_score"], audio["frequency_score"]),
                "video_ml_prob":       video_ml,
                "audio_ml_prob":       audio_ml,
                "ml_fake_probability": combined_ml,
                "findings":            findings,
                "software_tag":        None,
            }


def _extract_audio(video_path: str, out_dir: str) -> str | None:
    out = os.path.join(out_dir, "audio_extracted.wav")
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", video_path, "-vn",
             "-acodec", "pcm_s16le", "-ar", "22050", "-ac", "1", out],
            capture_output=True, timeout=120,
        )
        return out if r.returncode == 0 and Path(out).exists() else None
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# Page renderers
# ══════════════════════════════════════════════════════════════════════════════

def page_home(settings: dict) -> None:
    st.title("🔍 Deepfake Analyzer")
    st.markdown("Upload an image, video, or audio file to run the full forensic pipeline.")

    col1, col2 = st.columns([3, 1])
    with col1:
        uploaded = st.file_uploader(
            "Choose a media file",
            type=["jpg", "jpeg", "png", "webp", "bmp",
                  "mp4", "avi", "mov", "webm", "mkv",
                  "mp3", "wav", "aac", "flac", "ogg"],
            help="Max recommended size: 100 MB for best performance",
        )
    with col2:
        sensitivity = st.selectbox(
            "Sensitivity",
            ["LOW", "MEDIUM", "HIGH"],
            index=["LOW", "MEDIUM", "HIGH"].index(settings.get("default_sensitivity", "MEDIUM")),
            help="Higher sensitivity = stricter scoring",
        )

    if uploaded is None:
        st.info("⬆️  Upload a file above to begin analysis.")
        return

    file_bytes = uploaded.read()
    file_size  = len(file_bytes)

    st.markdown(f"**File:** `{uploaded.name}` &nbsp;|&nbsp; **Size:** {file_size / 1024:.1f} KB")

    if st.button("▶  Run Analysis", type="primary", use_container_width=True):
        with st.spinner("Running forensic analysis — this may take a moment…"):
            try:
                result = run_analysis(file_bytes, uploaded.name, sensitivity, settings)
            except Exception as exc:
                st.error(f"Analysis failed: {exc}")
                logger.exception("Analysis error")
                return

        # Store in session so we can reference it
        st.session_state["last_result"]   = result
        st.session_state["last_filename"] = uploaded.name
        st.session_state["last_bytes"]    = file_bytes

        # Persist to DB
        ana_id = "ANA-" + hashlib.sha256(file_bytes[:1024]).hexdigest()[:6].upper()
        seen   = {r.id for r in _db_all_results()}
        if ana_id not in seen:
            record = AnalysisResult(
                id                = ana_id,
                filename          = uploaded.name,
                file_type         = result["media_type"],
                trust_score       = result["trust_score"],
                verdict           = result["verdict"],
                ai_probability    = result["ai_probability"],
                metadata_score    = result["metadata_score"],
                frame_score       = result["frame_score"],
                audio_score       = result["audio_score"],
                compression_score = result["compression_score"],
                compression_level = result["compression_level"],
                bitrate           = result["bitrate"],
                ai_logo_detected  = result["ai_logo_detected"],
                detected_text     = result["detected_text"],
                findings          = json.dumps(result["findings"]),
                created_at        = datetime.now(timezone.utc).replace(tzinfo=None),
            )
            _db_save(record)
            st.session_state["last_id"] = ana_id

    # ── Render result if available ────────────────────────────────────────────
    if "last_result" not in st.session_state:
        return

    result   = st.session_state["last_result"]
    filename = st.session_state.get("last_filename", "")
    trust    = result["trust_score"]
    verdict  = score_to_verdict(trust, settings)
    risk     = score_to_risk(trust, settings)
    v_color  = verdict_color(verdict, settings)

    st.divider()
    st.subheader("Analysis Results")

    # Verdict banner
    st.markdown(
        f"""
        <div style="
            background: {'#1a3a1a' if v_color=='green' else '#3a2a1a' if v_color=='orange' else '#3a1a1a'};
            border-left: 4px solid {'#00cc66' if v_color=='green' else '#ffaa00' if v_color=='orange' else '#ff3355'};
            padding: 16px 20px; border-radius: 8px; margin-bottom: 16px;">
            <span style="font-size:1.4em; font-weight:700;
                color:{'#00cc66' if v_color=='green' else '#ffaa00' if v_color=='orange' else '#ff3355'}">
                {verdict}
            </span>
            &nbsp;&nbsp;
            <span style="color:#aaa; font-size:0.9em">
                Trust Score: <b style="color:#fff">{trust}/100</b>
                &nbsp;|&nbsp; Risk: <b style="color:#fff">{risk}</b>
                &nbsp;|&nbsp; {filename}
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Metric cards
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Trust Score",   f"{trust}/100")
    c2.metric("Confidence",    f"{result['confidence']}%")
    c3.metric("Media Type",    result["media_type"])
    c4.metric("AI Logo Found", "Yes ⚠️" if result["ai_logo_detected"] else "No ✅")

    # Progress bar for trust score
    bar_color = "#00cc66" if trust >= settings["authentic_threshold"] else \
                "#ffaa00" if trust >= settings["suspicious_threshold"] else "#ff3355"
    st.markdown(
        f"""
        <div style="background:#1a1a2e;border-radius:6px;padding:3px;margin:8px 0">
          <div style="width:{trust}%;height:14px;border-radius:4px;
                      background:{bar_color};transition:width 1s"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Detection scores
    st.markdown("#### Detection Module Scores")
    scores_df = pd.DataFrame([
        {"Module": "Metadata / AI Signature",   "Score (0=clean)": result["metadata_score"]},
        {"Module": "Frame / Facial Analysis",   "Score (0=clean)": result["frame_score"]},
        {"Module": "Audio Analysis",            "Score (0=clean)": result["audio_score"]},
        {"Module": "Compression Artifacts",     "Score (0=clean)": result["compression_score"]},
    ])
    st.dataframe(scores_df, use_container_width=True, hide_index=True)

    # ML scores
    if settings.get("show_ml_scores", True):
        ml_video = result.get("video_ml_prob", 0.0)
        ml_audio = result.get("audio_ml_prob", 0.0)
        ml_combined = result.get("ml_fake_probability", 0.0)

        if ml_combined > 0:
            st.markdown("#### ML Model Analysis (Hugging Face)")
            mc1, mc2, mc3 = st.columns(3)
            media_label = "Image AI Prob" if result["media_type"] == "IMAGE" else "Video AI Prob"
            mc1.metric(media_label,       f"{ml_video*100:.1f}%")
            mc2.metric("Audio AI Prob",   f"{ml_audio*100:.1f}%")
            mc3.metric("Combined ML Score", f"{ml_combined*100:.1f}%")

            if ml_combined > 0.70:
                st.warning(
                    f"⚠️  ML model flagged this media as likely AI-generated "
                    f"(probability {ml_combined*100:.1f}%)"
                )

    # Watermark text
    wm_text = settings.get("watermark_text", DEFAULT_SETTINGS["watermark_text"])
    ml_p    = result.get("ml_fake_probability", 0.0)
    st.caption(f"🔏  {wm_text} | Trust Score: {trust} | AI Probability: {ml_p:.2f}")

    # Findings
    with st.expander("📋  Detailed Findings", expanded=True):
        findings = result.get("findings", [])
        if findings:
            for f in findings:
                icon = "🔴" if "anomal" in f.lower() or "detect" in f.lower() \
                    else "🟡" if "moderate" in f.lower() or "slight" in f.lower() \
                    else "🟢"
                st.markdown(f"{icon}  {f}")
        else:
            st.success("No significant anomalies detected — content appears authentic.")

    # Image preview
    ext = Path(filename).suffix.lower()
    if ext in IMAGE_EXTS and "last_bytes" in st.session_state:
        with st.expander("🖼  Image Preview"):
            st.image(st.session_state["last_bytes"], caption=filename, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────

def page_activity_log(settings: dict) -> None:
    st.title("📋  Activity Log")
    st.markdown("All media files analysed through this system, most recent first.")

    rows = _db_all_results()

    if not rows:
        st.info("No analysis records found yet. Run your first analysis on the Home page.")
        return

    df = _rows_to_df(rows)

    # ── Filters ───────────────────────────────────────────────────────────────
    with st.expander("🔎  Filters", expanded=False):
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            verdict_filter = st.multiselect(
                "Verdict",
                options=df["Verdict"].unique().tolist(),
                default=[],
                placeholder="All verdicts",
            )
        with fc2:
            type_filter = st.multiselect(
                "Media Type",
                options=df["Type"].unique().tolist(),
                default=[],
                placeholder="All types",
            )
        with fc3:
            min_score, max_score = st.slider(
                "Trust Score range",
                min_value=0, max_value=100,
                value=(0, 100),
            )

    filtered = df.copy()
    if verdict_filter:
        filtered = filtered[filtered["Verdict"].isin(verdict_filter)]
    if type_filter:
        filtered = filtered[filtered["Type"].isin(type_filter)]
    filtered = filtered[
        (filtered["Trust Score"] >= min_score) &
        (filtered["Trust Score"] <= max_score)
    ]

    # ── Summary stats ─────────────────────────────────────────────────────────
    total = len(filtered)
    auth  = (filtered["Verdict"] == settings["authentic_label"]).sum()
    susp  = (filtered["Verdict"] == settings["suspicious_label"]).sum()
    deep  = (filtered["Verdict"] == settings["deepfake_label"]).sum()
    avg_s = filtered["Trust Score"].mean() if total > 0 else 0

    s1, s2, s3, s4, s5 = st.columns(5)
    s1.metric("Total Records",  total)
    s2.metric("Authentic ✅",   int(auth))
    s3.metric("Suspicious ⚠️", int(susp))
    s4.metric("Deepfake 🔴",    int(deep))
    s5.metric("Avg Trust Score", f"{avg_s:.1f}")

    st.divider()

    # ── Table columns to display ──────────────────────────────────────────────
    display_cols = ["File Name", "Type", "Trust Score", "Verdict", "AI Logo", "Timestamp"]
    display_df   = filtered[display_cols].head(settings.get("max_activity_rows", 200))

    # Colour the Verdict column
    def colour_verdict(val: str) -> str:
        if val == settings["authentic_label"]:
            return "color: #00cc66; font-weight: bold"
        if val == settings["suspicious_label"]:
            return "color: #ffaa00; font-weight: bold"
        return "color: #ff3355; font-weight: bold"

    styled = display_df.style.applymap(colour_verdict, subset=["Verdict"])
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # Export
    csv = filtered.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇  Export full log as CSV",
        data=csv,
        file_name=f"activity_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
    )


# ─────────────────────────────────────────────────────────────────────────────

def page_evidence_db(settings: dict) -> None:
    st.title("🗄️  Evidence Database")
    st.markdown("Detailed metadata browser — select a record to inspect its full forensic profile.")

    rows = _db_all_results()

    if not rows:
        st.info("No evidence records yet. Analyse a file first.")
        return

    df = _rows_to_df(rows)

    # ── Search ────────────────────────────────────────────────────────────────
    search = st.text_input("🔍  Search by filename", placeholder="e.g. video.mp4")
    if search:
        mask = df["File Name"].str.contains(search, case=False, na=False)
        df   = df[mask]

    if df.empty:
        st.warning("No records match your search.")
        return

    # ── Card grid ─────────────────────────────────────────────────────────────
    cols_per_row = 3
    records_list = list(zip(df["ID"], df["File Name"], df["Type"],
                            df["Trust Score"], df["Verdict"], df["Timestamp"]))

    for row_start in range(0, len(records_list), cols_per_row):
        cols = st.columns(cols_per_row)
        for col_idx, rec in enumerate(records_list[row_start: row_start + cols_per_row]):
            ana_id, fname, ftype, score, verdict_val, ts = rec
            v_color = (
                "#00cc66" if verdict_val == settings["authentic_label"]
                else "#ffaa00" if verdict_val == settings["suspicious_label"]
                else "#ff3355"
            )
            icon = "🎬" if ftype == "VIDEO" else "🔊" if ftype == "AUDIO" else "🖼"
            with cols[col_idx]:
                st.markdown(
                    f"""
                    <div style="
                        border:1px solid #2a2a4a; border-radius:10px;
                        padding:14px; margin-bottom:8px;
                        background:#0f1929;">
                        <div style="font-size:1.6em">{icon}</div>
                        <div style="font-weight:600;font-size:0.9em;
                             margin:6px 0 2px;word-break:break-all">{fname}</div>
                        <div style="color:#888;font-size:0.75em">{ftype} · {ts[:10]}</div>
                        <div style="
                            color:{v_color};font-weight:700;
                            font-size:0.85em;margin-top:6px">{verdict_val}</div>
                        <div style="color:#ccc;font-size:0.8em">Trust: {score}/100</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button("View Details", key=f"view_{ana_id}"):
                    st.session_state["evidence_selected"] = ana_id

    # ── Detail panel ──────────────────────────────────────────────────────────
    sel_id = st.session_state.get("evidence_selected")
    if sel_id:
        record = _db_get(sel_id)
        if record:
            st.divider()
            st.subheader(f"📄  Record Detail — {record.id}")
            d1, d2 = st.columns(2)

            with d1:
                st.markdown("**File Information**")
                info_df = pd.DataFrame([
                    {"Field": "Analysis ID",       "Value": record.id},
                    {"Field": "File Name",          "Value": record.filename},
                    {"Field": "File Type",          "Value": record.file_type},
                    {"Field": "Analysed At",        "Value": record.created_at.strftime("%Y-%m-%d %H:%M:%S") if record.created_at else "—"},
                    {"Field": "Compression Level",  "Value": record.compression_level or "—"},
                    {"Field": "Bitrate",            "Value": f"{record.bitrate} kbps" if record.bitrate else "—"},
                    {"Field": "AI Logo Detected",   "Value": "Yes ⚠️" if record.ai_logo_detected else "No ✅"},
                    {"Field": "Detected Text",      "Value": record.detected_text or "—"},
                ])
                st.dataframe(info_df, use_container_width=True, hide_index=True)

            with d2:
                st.markdown("**Analysis Scores**")
                v_color = (
                    "#00cc66" if record.verdict == settings["authentic_label"]
                    else "#ffaa00" if record.verdict == settings["suspicious_label"]
                    else "#ff3355"
                )
                st.markdown(
                    f"<span style='font-size:1.3em;font-weight:700;color:{v_color}'>"
                    f"{record.verdict}</span>",
                    unsafe_allow_html=True,
                )
                scores_df = pd.DataFrame([
                    {"Module": "Trust Score",            "Score": record.trust_score},
                    {"Module": "Metadata / AI Signature","Score": record.metadata_score},
                    {"Module": "Frame / Facial",         "Score": record.frame_score},
                    {"Module": "Audio",                  "Score": record.audio_score},
                    {"Module": "Compression",            "Score": record.compression_score},
                ])
                st.dataframe(scores_df, use_container_width=True, hide_index=True)

            findings_raw = json.loads(record.findings or "[]")
            if findings_raw:
                st.markdown("**Findings**")
                for f in findings_raw:
                    icon_f = "🔴" if "anomal" in f.lower() or "detect" in f.lower() \
                        else "🟡" if "moderate" in f.lower() or "slight" in f.lower() \
                        else "🟢"
                    st.markdown(f"{icon_f}  {f}")

            if st.button("✖  Close", key="close_detail"):
                del st.session_state["evidence_selected"]
                st.rerun()


# ─────────────────────────────────────────────────────────────────────────────

def page_settings(settings: dict) -> dict:
    """Render the Settings page. Returns the (possibly updated) settings dict."""
    st.title("⚙️  Settings")
    st.markdown("Configure analysis behaviour, scoring thresholds, and display options.")

    changed = False
    s = dict(settings)

    # ── Watermark / Attribution ───────────────────────────────────────────────
    st.subheader("🔏  Watermark & Attribution")
    new_wm = st.text_input(
        "Watermark text",
        value=s.get("watermark_text", DEFAULT_SETTINGS["watermark_text"]),
        help="This text appears on analysis results and in the forensic report footer.",
    )
    if new_wm != s["watermark_text"]:
        s["watermark_text"] = new_wm
        changed = True

    st.divider()

    # ── Trust Score Thresholds ────────────────────────────────────────────────
    st.subheader("🎯  Trust Score Thresholds")
    st.markdown("Scores above the **Authentic threshold** are classified as authentic. "
                "Scores between the two thresholds are suspicious. Below = deepfake.")

    tc1, tc2 = st.columns(2)
    with tc1:
        new_auth = st.slider(
            "Authentic threshold (min score for AUTHENTIC)",
            min_value=50, max_value=99,
            value=int(s.get("authentic_threshold", 80)),
            step=1,
        )
    with tc2:
        new_susp = st.slider(
            "Suspicious threshold (min score for SUSPICIOUS)",
            min_value=1, max_value=new_auth - 1,
            value=min(int(s.get("suspicious_threshold", 50)), new_auth - 1),
            step=1,
        )

    if new_auth != s["authentic_threshold"] or new_susp != s["suspicious_threshold"]:
        s["authentic_threshold"] = new_auth
        s["suspicious_threshold"] = new_susp
        changed = True

    st.info(
        f"Current bands:  "
        f"**{new_susp}–{new_auth-1}** → SUSPICIOUS  |  "
        f"**0–{new_susp-1}** → DEEPFAKE  |  "
        f"**{new_auth}–100** → AUTHENTIC"
    )

    st.divider()

    # ── Risk Level Labels ─────────────────────────────────────────────────────
    st.subheader("🏷️  Risk Classification Labels")
    lc1, lc2, lc3 = st.columns(3)
    with lc1:
        new_al = st.text_input("Authentic label",  value=s.get("authentic_label",  "AUTHENTIC"))
    with lc2:
        new_sl = st.text_input("Suspicious label", value=s.get("suspicious_label", "SUSPICIOUS"))
    with lc3:
        new_dl = st.text_input("Deepfake label",   value=s.get("deepfake_label",   "DEEPFAKE"))

    for key, val, orig in [
        ("authentic_label",  new_al, s["authentic_label"]),
        ("suspicious_label", new_sl, s["suspicious_label"]),
        ("deepfake_label",   new_dl, s["deepfake_label"]),
    ]:
        if val.strip() and val != orig:
            s[key] = val.strip().upper()
            changed = True

    st.divider()

    # ── Analysis Defaults ─────────────────────────────────────────────────────
    st.subheader("🔬  Analysis Defaults")
    dc1, dc2 = st.columns(2)
    with dc1:
        new_sens = st.selectbox(
            "Default sensitivity",
            options=["LOW", "MEDIUM", "HIGH"],
            index=["LOW", "MEDIUM", "HIGH"].index(s.get("default_sensitivity", "MEDIUM")),
            help="Pre-selects the sensitivity level on the Analyzer page.",
        )
        if new_sens != s["default_sensitivity"]:
            s["default_sensitivity"] = new_sens
            changed = True

    with dc2:
        new_ml = st.toggle(
            "Show ML model scores",
            value=bool(s.get("show_ml_scores", True)),
            help="Display Hugging Face ML probability scores in the results.",
        )
        if new_ml != s.get("show_ml_scores", True):
            s["show_ml_scores"] = new_ml
            changed = True

    st.divider()

    # ── Activity Log ──────────────────────────────────────────────────────────
    st.subheader("📋  Activity Log")
    new_max = st.number_input(
        "Max rows to display in Activity Log",
        min_value=10, max_value=5000,
        value=int(s.get("max_activity_rows", 200)),
        step=50,
    )
    if new_max != s["max_activity_rows"]:
        s["max_activity_rows"] = int(new_max)
        changed = True

    st.divider()

    # ── Save button ───────────────────────────────────────────────────────────
    col_save, col_reset, _ = st.columns([1, 1, 3])
    with col_save:
        if st.button("💾  Save Settings", type="primary", use_container_width=True):
            save_settings(s)
            st.session_state["settings"] = s
            st.success("✅  Settings saved.")
            changed = False

    with col_reset:
        if st.button("↩  Reset to Defaults", use_container_width=True):
            save_settings(DEFAULT_SETTINGS)
            st.session_state["settings"] = dict(DEFAULT_SETTINGS)
            st.info("Settings reset to defaults.")
            st.rerun()

    if changed:
        st.caption("⚠️  You have unsaved changes — click **Save Settings** to apply.")

    return s


# ══════════════════════════════════════════════════════════════════════════════
# Sidebar
# ══════════════════════════════════════════════════════════════════════════════

def render_sidebar(settings: dict) -> str:
    """Render the sidebar navigation. Returns the active page name."""
    with st.sidebar:
        st.markdown(
            """
            <div style="text-align:center;padding:12px 0 20px">
                <div style="font-size:2em">🛡️</div>
                <div style="font-weight:700;font-size:1.1em;color:#00ccff">
                    MediaTrust AI
                </div>
                <div style="font-size:0.72em;color:#666;margin-top:2px">
                    Deepfake Trust & Attribution
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("##### Navigation")
        pages = {
            "🏠  Analyzer":     "home",
            "📋  Activity Log": "activity_log",
            "🗄️  Evidence DB":  "evidence_db",
            "⚙️  Settings":     "settings",
        }

        current = st.session_state.get("page", "home")

        for label, key in pages.items():
            is_active = current == key
            if st.button(
                label,
                key=f"nav_{key}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                st.session_state["page"] = key
                # Clear sub-state when changing pages
                st.session_state.pop("evidence_selected", None)
                st.rerun()

        st.divider()

        # Quick stats
        st.markdown("##### Quick Stats")
        try:
            rows = _db_all_results()
            total  = len(rows)
            deep   = sum(1 for r in rows if r.verdict == settings["deepfake_label"])
            auth   = sum(1 for r in rows if r.verdict == settings["authentic_label"])
            avg_ts = (sum(r.trust_score for r in rows) / total) if total else 0

            st.metric("Analyses Run", total)
            col_a, col_b = st.columns(2)
            col_a.metric("Authentic", auth)
            col_b.metric("Deepfakes", deep)
            st.metric("Avg Trust Score", f"{avg_ts:.0f}")
        except Exception:
            st.caption("Stats unavailable")

        st.divider()
        st.caption("v5.0 · FastAPI + Streamlit")

    return st.session_state.get("page", "home")


# ══════════════════════════════════════════════════════════════════════════════
# App entry point
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    st.set_page_config(
        page_title="Deepfake Trust & Attribution System",
        page_icon="🛡️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Initialise DB on first run
    try:
        init_db()
    except Exception as exc:
        st.error(f"Database init failed: {exc}")

    # Load / cache settings
    if "settings" not in st.session_state:
        st.session_state["settings"] = load_settings()
    settings = st.session_state["settings"]

    # Initialise page
    if "page" not in st.session_state:
        st.session_state["page"] = "home"

    # Render sidebar + get active page
    active_page = render_sidebar(settings)

    # Route to the correct page
    if active_page == "home":
        page_home(settings)
    elif active_page == "activity_log":
        page_activity_log(settings)
    elif active_page == "evidence_db":
        page_evidence_db(settings)
    elif active_page == "settings":
        updated = page_settings(settings)
        st.session_state["settings"] = updated
    else:
        page_home(settings)


if __name__ == "__main__":
    main()
