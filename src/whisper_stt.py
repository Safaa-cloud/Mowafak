"""
src/whisper_stt.py
──────────────────
Single responsibility: load the Whisper model and transcribe an audio file.

FIX (Bug 6): All database code has been removed from this module.
  - The old version called init_db() at module level, which opened a second
    SQLite file (data/mowafak.db relative to CWD) instead of the one defined
    in settings.DATABASE_URL, creating a silent orphan database.
  - save_transcript() was dead code — main.py never called it and did its own
    INSERT with a different ID format (uuid4 vs os.urandom hex), risking schema
    inconsistency if both were ever active.

Database writes now live exclusively in backend/main.py where the settings
path is used consistently.  This module is imported by main.py only for the
transcribe_audio() function.
"""

import os
import logging
from pathlib import Path

import whisper

# ---------------------------------------------------------------------------
# Configuration — read from environment or .env via settings (set by caller)
# ---------------------------------------------------------------------------

WHISPER_MODEL_SIZE: str = os.getenv("WHISPER_MODEL", "base")

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model — lazy singleton (loaded once, reused for every transcription)
# ---------------------------------------------------------------------------

_model: whisper.Whisper | None = None


def _get_model() -> whisper.Whisper:
    global _model
    if _model is None:
        logger.info("Loading Whisper model: %s (first call only)", WHISPER_MODEL_SIZE)
        _model = whisper.load_model(WHISPER_MODEL_SIZE)
    return _model


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def transcribe_audio(audio_path: str | Path) -> str:
    """
    Transcribe an audio file using OpenAI Whisper in batch mode.

    Parameters
    ----------
    audio_path : str | Path
        Absolute path to the saved audio file.

    Returns
    -------
    str
        The transcribed text, or "[No speech detected]" if the model
        produced an empty result.

    Raises
    ------
    FileNotFoundError
        If the audio file does not exist at the given path.
    """
    audio_path = Path(audio_path)

    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    model  = _get_model()
    result = model.transcribe(str(audio_path), fp16=False)

    transcript = (result.get("text") or "").strip()

    if not transcript:
        logger.warning("Whisper returned empty transcript for: %s", audio_path.name)
        return "[No speech detected]"

    logger.info("Transcribed %s → %d chars", audio_path.name, len(transcript))
    return transcript