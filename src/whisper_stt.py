import os
import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timezone

import whisper

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL", "base")

DB_PATH = os.getenv("DB_PATH", "data/mowafak.db")

AUDIO_DIR = os.getenv("AUDIO_DIR", "data/sample_recordings")

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# --------------------------------------------------------------------------- #
# Model
# --------------------------------------------------------------------------- #

_model: whisper.Whisper | None = None


def _get_model() -> whisper.Whisper:
    global _model
    if _model is None:
        logger.info("Loading Whisper model: %s", WHISPER_MODEL_SIZE)
        _model = whisper.load_model(WHISPER_MODEL_SIZE)
    return _model


# --------------------------------------------------------------------------- #
# DB Connection
# --------------------------------------------------------------------------- #

def _get_connection() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


# --------------------------------------------------------------------------- #
# DB INIT
# --------------------------------------------------------------------------- #

def init_db() -> None:
    with _get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS question_answer (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                question_no INTEGER NOT NULL,
                audio_path TEXT NOT NULL,
                transcript TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()

    logger.info("Database initialized → %s", DB_PATH)


init_db()


# --------------------------------------------------------------------------- #
# Transcription
# --------------------------------------------------------------------------- #

def transcribe_audio(audio_path: str | Path) -> str:
    audio_path = Path(audio_path)

    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    model = _get_model()

    result = model.transcribe(str(audio_path), fp16=False)
    transcript = (result.get("text") or "").strip()

    if not transcript:
        raise RuntimeError("Empty transcript returned by Whisper")

    return transcript


# --------------------------------------------------------------------------- #
# SAVE TO DB
# --------------------------------------------------------------------------- #

def save_transcript(session_id: str, question_no: int, audio_path: str, transcript: str) -> int:

    created_at = datetime.now(timezone.utc).isoformat()

    with _get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO question_answer (
                session_id,
                question_no,
                audio_path,
                transcript,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, question_no, str(audio_path), transcript, created_at),
        )

        conn.commit()
        return cursor.lastrowid


# --------------------------------------------------------------------------- #
# PIPELINE
# --------------------------------------------------------------------------- #

def transcribe_and_save(session_id: str, question_no: int, audio_path: str | Path):

    transcript = transcribe_audio(audio_path)
    row_id = save_transcript(session_id, question_no, audio_path, transcript)

    return {
        "session_id": session_id,
        "question_no": question_no,
        "transcript": transcript,
        "row_id": row_id,
    }


# --------------------------------------------------------------------------- #
# GET DATA
# --------------------------------------------------------------------------- #

def get_transcripts_for_session(session_id: str):

    with _get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, session_id, question_no, audio_path, transcript, created_at
            FROM question_answer
            WHERE session_id = ?
            ORDER BY question_no ASC
            """,
            (session_id,),
        ).fetchall()

    return [dict(row) for row in rows]