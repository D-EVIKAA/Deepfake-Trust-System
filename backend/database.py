"""
Database layer — SQLite via SQLAlchemy 2.x
==========================================

Table: analysis_results
  Stores every file analysed through the /api/analyze endpoint so that
  dashboard graphs and downloadable reports can use real, persisted data.

Migration strategy: on startup, ALTER TABLE adds any columns that were
introduced in later versions — safe and non-destructive.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    Boolean, Column, DateTime, Integer, String, Text,
    create_engine, inspect, text,
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker

logger = logging.getLogger(__name__)

DB_PATH      = Path(__file__).parent / "deepfake.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id                = Column(String,   primary_key=True, index=True)
    filename          = Column(String,   nullable=False)
    file_type         = Column(String,   nullable=False)     # VIDEO | IMAGE | AUDIO
    trust_score       = Column(Integer,  nullable=False)
    verdict           = Column(String,   nullable=False)     # AUTHENTIC | SUSPICIOUS | DEEPFAKE
    ai_probability    = Column(Integer,  nullable=True)      # confidence 0-100
    metadata_score    = Column(Integer,  nullable=True)      # AI-detection / metadata anomaly score
    frame_score       = Column(Integer,  nullable=True)      # facial + temporal max
    audio_score       = Column(Integer,  nullable=True)      # audio + frequency max
    compression_score = Column(Integer,  nullable=True)      # compression anomaly 0-100
    compression_level = Column(String,   nullable=True)      # low | medium | high | very_high
    bitrate           = Column(Integer,  nullable=True)      # kbps (video/audio)
    ai_logo_detected  = Column(Boolean,  nullable=True, default=False)
    detected_text     = Column(String,   nullable=True)      # OCR-matched keyword e.g. "gemini"
    findings          = Column(Text,     nullable=True)      # JSON-encoded list[str]
    created_at        = Column(DateTime, nullable=False, default=datetime.utcnow)

    def to_summary(self) -> dict:
        """Compact dict for dashboard tables / recent-analyses lists."""
        return {
            "id":           self.id,
            "filename":     self.filename,
            "type":         self.file_type,
            "trustScore":   self.trust_score,
            "verdict":      self.verdict,
            "timestamp":    self.created_at.isoformat() + "Z",
            "aiLogo":       bool(self.ai_logo_detected),
        }


# ── Public helpers ────────────────────────────────────────────────────────────

def init_db() -> None:
    """Create tables (if absent) then apply non-destructive column migrations."""
    Base.metadata.create_all(bind=engine)
    _migrate_columns()


def get_db():
    """FastAPI dependency — yields a DB session and closes it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Internal migration ────────────────────────────────────────────────────────

def _migrate_columns() -> None:
    """
    Add columns introduced in later schema versions to an existing database.
    Uses SQLite's ALTER TABLE … ADD COLUMN (safe, never removes data).
    """
    _NEW_COLUMNS: dict[str, str] = {
        "compression_score": "INTEGER",
        "compression_level": "VARCHAR",
        "bitrate":           "INTEGER",
        "ai_logo_detected":  "BOOLEAN",
        "detected_text":     "VARCHAR",
    }
    try:
        insp     = inspect(engine)
        existing = {col["name"] for col in insp.get_columns("analysis_results")}
        with engine.connect() as conn:
            for col, col_type in _NEW_COLUMNS.items():
                if col not in existing:
                    conn.execute(
                        text(f"ALTER TABLE analysis_results ADD COLUMN {col} {col_type}")
                    )
                    logger.info("DB migration: added column '%s'", col)
            conn.commit()
    except Exception as exc:
        logger.warning("DB migration check failed (non-fatal): %s", exc)
