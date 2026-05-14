from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import sqlite3
import shutil
import hashlib
import uuid
import json
import os
import sys

from pathlib import Path
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Optional

sys.path.append(str(Path(__file__).parent.parent))

from src.settings import settings


# =============================================================================
# CONSTANTS
# =============================================================================

MAX_CV_SIZE_MB = 10
MAX_AUDIO_SIZE_MB = 25

ALLOWED_AUDIO_EXTENSIONS = {".wav", ".webm", ".mp3", ".m4a"}
ALLOWED_CV_CONTENT_TYPE = "application/pdf"


# =============================================================================
# DATABASE HELPERS
# =============================================================================


def get_db_connection():
    conn = sqlite3.connect(settings.DATABASE_URL, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn



def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS candidates (
            id                  TEXT PRIMARY KEY,
            name                TEXT,
            email               TEXT,
            cv_path             TEXT,
            session_id          TEXT,
            consent_accepted    INTEGER DEFAULT 0,
            created_at          TEXT
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id                  TEXT PRIMARY KEY,
            candidate_id        TEXT,
            status              TEXT DEFAULT 'pending',
            questions_json      TEXT,
            created_at          TEXT
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS answers (
            id                  TEXT PRIMARY KEY,
            session_id          TEXT,
            question_index      INTEGER,
            audio_path          TEXT,
            transcript          TEXT,
            created_at          TEXT
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS reports (
            id                  TEXT PRIMARY KEY,
            session_id          TEXT,
            report_json         TEXT,
            ai_recommendation   TEXT,
            hr_decision         TEXT,
            hr_notes            TEXT,
            hr_user_id          TEXT,
            decided_at          TEXT
        )
    """
    )

    conn.commit()
    conn.close()


# =============================================================================
# FILE HELPERS
# =============================================================================


def ensure_directories_exist():
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    Path(settings.AUDIT_LOG_PATH).parent.mkdir(parents=True, exist_ok=True)



def validate_file_size(upload_file: UploadFile, max_size_mb: int):
    upload_file.file.seek(0, os.SEEK_END)
    file_size = upload_file.file.tell()
    upload_file.file.seek(0)

    max_bytes = max_size_mb * 1024 * 1024

    if file_size > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds {max_size_mb} MB limit.",
        )



def validate_audio_extension(filename: str):
    suffix = Path(filename).suffix.lower()

    if suffix not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported audio format.",
        )

    return suffix


# =============================================================================
# WHISPER PLACEHOLDER
# =============================================================================


def transcribe_audio(audio_path: str) -> str:
    """
    Placeholder for Whisper integration.

    Replace with:
    from src.whisper_stt import transcribe
    """

    return "Transcript pending Whisper integration"


# =============================================================================
# PYDANTIC MODELS
# =============================================================================


class HRDecisionRequest(BaseModel):
    session_id: str
    decision: str
    hr_user_id: str
    hr_notes: Optional[str] = ""


# =============================================================================
# APP LIFECYCLE
# =============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_directories_exist()
    init_db()
    yield


app = FastAPI(
    title="Mowafak AI Pre-Screen API",
    version="1.0.0",
    lifespan=lifespan,
)


# =============================================================================
# CORS
# =============================================================================


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# HEALTH CHECK
# =============================================================================


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# =============================================================================
# UPLOAD CV
# =============================================================================


@app.post("/upload_cv")
async def upload_cv(
    file: UploadFile = File(...),
    name: str = Form(...),
    email: str = Form(...),
    consent_accepted: bool = Form(...),
):
    if not consent_accepted:
        raise HTTPException(
            status_code=400,
            detail="Candidate consent is required.",
        )

    if file.content_type != ALLOWED_CV_CONTENT_TYPE:
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are accepted.",
        )

    validate_file_size(file, MAX_CV_SIZE_MB)

    candidate_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())

    upload_path = Path(settings.UPLOAD_DIR) / f"cv_{candidate_id}.pdf"

    with open(upload_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    now = datetime.now(timezone.utc).isoformat()

    conn = get_db_connection()

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO candidates (
                id,
                name,
                email,
                cv_path,
                session_id,
                consent_accepted,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                candidate_id,
                name,
                email,
                str(upload_path),
                session_id,
                1,
                now,
            ),
        )

        cursor.execute(
            """
            INSERT INTO sessions (
                id,
                candidate_id,
                status,
                created_at
            )
            VALUES (?, ?, 'pending', ?)
        """,
            (session_id, candidate_id, now),
        )

        conn.commit()

    except sqlite3.Error:
        raise HTTPException(
            status_code=500,
            detail="Database operation failed.",
        )

    finally:
        conn.close()

    return {
        "message": "CV uploaded successfully.",
        "candidate_id": candidate_id,
        "session_id": session_id,
    }


# =============================================================================
# START INTERVIEW
# =============================================================================


@app.post("/start_interview")
async def start_interview(
    session_id: str = Form(...),
    questions_json: str = Form(...),
):
    conn = get_db_connection()

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE sessions
            SET status='in_progress', questions_json=?
            WHERE id=?
        """,
            (questions_json, session_id),
        )

        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=404,
                detail="Session not found.",
            )

        conn.commit()

    finally:
        conn.close()

    return {
        "message": "Interview started.",
        "session_id": session_id,
    }


# =============================================================================
# UPLOAD ANSWER
# =============================================================================


@app.post("/upload_answer")
async def upload_answer(
    session_id: str = Form(...),
    question_index: int = Form(...),
    audio: UploadFile = File(...),
):
    conn = get_db_connection()

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT c.consent_accepted
            FROM candidates c
            JOIN sessions s ON c.id = s.candidate_id
            WHERE s.id=?
        """,
            (session_id,),
        )

        consent_row = cursor.fetchone()

        if not consent_row:
            raise HTTPException(
                status_code=404,
                detail="Session not found.",
            )

        if consent_row["consent_accepted"] != 1:
            raise HTTPException(
                status_code=403,
                detail="Consent required before recording.",
            )

    finally:
        conn.close()

    validate_file_size(audio, MAX_AUDIO_SIZE_MB)

    suffix = validate_audio_extension(audio.filename or "audio.webm")

    answer_id = str(uuid.uuid4())
    audio_path = Path(settings.UPLOAD_DIR) / f"answer_{answer_id}{suffix}"

    with open(audio_path, "wb") as buffer:
        shutil.copyfileobj(audio.file, buffer)

    transcript = transcribe_audio(str(audio_path))

    conn = get_db_connection()

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO answers (
                id,
                session_id,
                question_index,
                audio_path,
                transcript,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                answer_id,
                session_id,
                question_index,
                str(audio_path),
                transcript,
                datetime.now(timezone.utc).isoformat(),
            ),
        )

        conn.commit()

    finally:
        conn.close()

    return {
        "message": "Answer uploaded successfully.",
        "answer_id": answer_id,
        "transcript": transcript,
    }


# =============================================================================
# GET REPORT
# =============================================================================


@app.get("/get_report")
async def get_report(session_id: str):
    conn = get_db_connection()

    try:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM reports WHERE session_id=?",
            (session_id,),
        )

        report = cursor.fetchone()

    finally:
        conn.close()

    if report is None:
        raise HTTPException(
            status_code=404,
            detail="Report not found. It may still be generating.",
        )

    return dict(report)


# =============================================================================
# HR DECISION
# =============================================================================


@app.post("/hr_decision")
async def hr_decision(request: HRDecisionRequest):
    allowed = {"approve", "reject", "hold"}

    if request.decision not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Decision must be one of: {allowed}",
        )

    now = datetime.now(timezone.utc).isoformat()

    conn = get_db_connection()

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT ai_recommendation
            FROM reports
            WHERE session_id=?
        """,
            (request.session_id,),
        )

        report_row = cursor.fetchone()

        if not report_row:
            raise HTTPException(
                status_code=404,
                detail="Report not found for this session.",
            )

        ai_recommendation = report_row["ai_recommendation"]

        cursor.execute(
            """
            UPDATE reports
            SET hr_decision=?,
                hr_notes=?,
                hr_user_id=?,
                decided_at=?
            WHERE session_id=?
        """,
            (
                request.decision,
                request.hr_notes,
                request.hr_user_id,
                now,
                request.session_id,
            ),
        )

        cursor.execute(
            "SELECT candidate_id FROM sessions WHERE id=?",
            (request.session_id,),
        )

        session_row = cursor.fetchone()

        conn.commit()

    finally:
        conn.close()

    candidate_id = session_row["candidate_id"] if session_row else "unknown"

    hr_notes_hash = hashlib.sha256(
        request.hr_notes.encode("utf-8")
    ).hexdigest()

    audit_entry = {
        "timestamp": now,
        "candidate_id": candidate_id,
        "session_id": request.session_id,
        "ai_recommendation": ai_recommendation,
        "hr_decision": request.decision,
        "hr_user_id": request.hr_user_id,
        "hr_notes_hash": hr_notes_hash,
    }

    with open(settings.AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(audit_entry) + "\n")

    return {
        "message": f"HR decision '{request.decision}' recorded.",
        "session_id": request.session_id,
        "timestamp": now,
    }


# =============================================================================
# MAIN
# =============================================================================


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.BACKEND_HOST,
        port=settings.BACKEND_PORT,
        reload=True,
    )
