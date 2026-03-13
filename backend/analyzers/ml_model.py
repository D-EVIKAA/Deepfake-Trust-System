"""
ML-based deepfake detection using pretrained Hugging Face models.

Models
------
  Image / video frames : umm-maybe/AI-image-detector
  Audio deepfake       : m3hrdadfi/wav2vec2-xlsr-deepfake-detection

Both pipelines are loaded once at module import (global singletons) so that
repeated requests do not incur model-reload overhead.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# ── Optional dependency flags ─────────────────────────────────────────────────

try:
    from PIL import Image as PILImage
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    logger.warning("Pillow not installed — ML image analysis unavailable")

try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    logger.warning("torch not installed — ML analysis will run on CPU (or be skipped)")

try:
    from transformers import pipeline as hf_pipeline
    HAS_TRANSFORMERS = True
except ImportError:
    HAS_TRANSFORMERS = False
    logger.warning("transformers not installed — ML deepfake analysis unavailable")


# ── Model identifiers ─────────────────────────────────────────────────────────

IMAGE_MODEL_ID = "umm-maybe/AI-image-detector"
AUDIO_MODEL_ID = "mo-thecreator/Deepfake-audio-detection"

# Label strings that correspond to "AI-generated / fake" for each model.
# Multiple variants are listed for robustness across model versions.
_IMAGE_FAKE_LABELS = {"artificial", "ai-generated", "fake", "generated"}
_AUDIO_FAKE_LABELS = {"fake", "spoof", "deepfake", "1", "bonafide_fake"}


# ── Global pipeline singletons ────────────────────────────────────────────────

_image_pipeline = None
_audio_pipeline = None
_models_loaded  = False


def _load_models() -> None:
    """Load both pipelines exactly once at startup."""
    global _image_pipeline, _audio_pipeline, _models_loaded

    if _models_loaded:
        return

    if not HAS_TRANSFORMERS:
        logger.warning("transformers not installed — skipping ML model load")
        _models_loaded = True
        return

    # Use GPU if available, otherwise CPU (-1)
    device = 0 if (HAS_TORCH and torch.cuda.is_available()) else -1

    try:
        logger.info("Loading image AI-detector: %s  (device=%s)", IMAGE_MODEL_ID, device)
        _image_pipeline = hf_pipeline(
            "image-classification",
            model=IMAGE_MODEL_ID,
            device=device,
        )
        logger.info("Image ML model loaded successfully")
    except Exception as exc:
        logger.error("Failed to load image ML model (%s): %s", IMAGE_MODEL_ID, exc)
        _image_pipeline = None

    try:
        logger.info("Loading audio deepfake detector: %s  (device=%s)", AUDIO_MODEL_ID, device)
        _audio_pipeline = hf_pipeline(
            "audio-classification",
            model=AUDIO_MODEL_ID,
            device=device,
        )
        logger.info("Audio ML model loaded successfully")
    except Exception as exc:
        logger.error("Failed to load audio ML model (%s): %s", AUDIO_MODEL_ID, exc)
        _audio_pipeline = None

    _models_loaded = True


# Trigger model loading on module import (once at server startup)
_load_models()


# ── Public helpers ────────────────────────────────────────────────────────────

def _classify_image(pil_image) -> dict:
    """Run the image pipeline and return fake_probability."""
    if _image_pipeline is None:
        return {"fake_probability": 0.0}
    try:
        results = _image_pipeline(pil_image)
        # results → [{"label": "...", "score": 0.xx}, ...]
        for r in results:
            if r["label"].lower() in _IMAGE_FAKE_LABELS:
                return {"fake_probability": float(r["score"])}
        # Fallback: if none of the known fake labels matched, return 0
        return {"fake_probability": 0.0}
    except Exception as exc:
        logger.error("ML image classification error: %s", exc)
        return {"fake_probability": 0.0}


# ── Public API ────────────────────────────────────────────────────────────────

def analyze_image_frame(frame: np.ndarray) -> dict:
    """
    Classify a single OpenCV BGR frame as real or AI-generated.

    Parameters
    ----------
    frame : np.ndarray  (H × W × 3, BGR colour order)

    Returns
    -------
    {"fake_probability": float}  — 0.0 = real, 1.0 = AI-generated
    """
    if _image_pipeline is None or not HAS_PIL:
        return {"fake_probability": 0.0}
    try:
        # OpenCV uses BGR; PIL / the model expect RGB
        rgb   = frame[:, :, ::-1].copy()
        image = PILImage.fromarray(rgb.astype(np.uint8))
        return _classify_image(image)
    except Exception as exc:
        logger.error("ML image frame analysis error: %s", exc)
        return {"fake_probability": 0.0}


def analyze_image_path(image_path: str) -> dict:
    """
    Load an image from *image_path* and classify it as real or AI-generated.

    Parameters
    ----------
    image_path : str — path to JPEG / PNG / WEBP / BMP file

    Returns
    -------
    {"fake_probability": float}  — 0.0 = real, 1.0 = AI-generated
    """
    if _image_pipeline is None or not HAS_PIL:
        return {"fake_probability": 0.0}
    if not Path(image_path).exists():
        return {"fake_probability": 0.0}
    try:
        image = PILImage.open(image_path).convert("RGB")
        return _classify_image(image)
    except Exception as exc:
        logger.error("ML image path analysis error: %s", exc)
        return {"fake_probability": 0.0}


def analyze_audio_file(audio_path: str) -> dict:
    """
    Classify an audio file as real speech or deepfake / synthetic.

    The Hugging Face pipeline handles loading and resampling internally.

    Parameters
    ----------
    audio_path : str — path to WAV / MP3 / FLAC file

    Returns
    -------
    {"fake_probability": float}  — 0.0 = real, 1.0 = deepfake
    """
    if _audio_pipeline is None:
        return {"fake_probability": 0.0}
    if not Path(audio_path).exists():
        return {"fake_probability": 0.0}
    try:
        results = _audio_pipeline(audio_path)
        for r in results:
            if r["label"].lower() in _AUDIO_FAKE_LABELS:
                return {"fake_probability": float(r["score"])}
        return {"fake_probability": 0.0}
    except Exception as exc:
        logger.error("ML audio analysis error: %s", exc)
        return {"fake_probability": 0.0}


def models_available() -> dict[str, bool]:
    """Return availability status of each ML pipeline (for /api/info)."""
    return {
        "ml_image_model": _image_pipeline is not None,
        "ml_audio_model": _audio_pipeline is not None,
    }
