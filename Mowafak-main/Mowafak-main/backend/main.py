from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import asyncio
import sqlite3
import shutil
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
from src.whisper_stt import transcribe_audio as real_whisper_transcribe
from src.audit_log import log_decision


# =============================================================================
# CONSTANTS
# =============================================================================

MAX_CV_SIZE_MB    = 10
MAX_AUDIO_SIZE_MB = 25

ALLOWED_AUDIO_EXTENSIONS = {".wav", ".webm", ".mp3", ".m4a"}
ALLOWED_CV_CONTENT_TYPE  = "application/pdf"


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
            question_text       TEXT,
            audio_path          TEXT,
            transcript          TEXT,
            created_at          TEXT
        )
        """
    )

    # has the original question alongside the transcript.

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

    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_reports_session_id ON reports(session_id)"
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

    if file_size > max_size_mb * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds {max_size_mb} MB limit.",
        )


def validate_audio_extension(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported audio format.",
        )
    return suffix


# =============================================================================
# WHISPER WRAPPER
# =============================================================================

def _transcribe_sync(audio_path: str) -> str:
    """Synchronous wrapper — called via run_in_executor to avoid blocking."""
    return real_whisper_transcribe(audio_path)


def _default_skills_matrix() -> dict:
    return {
        "required_skills": ["Python", "Machine Learning", "SQL"],
        "nice_to_have_skills": ["TensorFlow", "Docker"],
    }


def _json_model(model) -> str:
    return model.model_dump_json() if hasattr(model, "model_dump_json") else json.dumps(model.dict())


async def maybe_generate_report(session_id: str):
    """Generate the HR report once all stored questions have an answer."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT questions_json FROM sessions WHERE id=?", (session_id,))
        session_row = cursor.fetchone()
        if not session_row or not session_row["questions_json"]:
            return

        questions = json.loads(session_row["questions_json"])
        cursor.execute(
            """
            SELECT question_index, question_text, transcript
            FROM answers
            WHERE session_id=?
            ORDER BY question_index ASC
            """,
            (session_id,),
        )
        answer_rows = cursor.fetchall()
    finally:
        conn.close()

    answered_indices = {row["question_index"] for row in answer_rows if row["transcript"]}
    if len(answered_indices) < len(questions):
        return

    def build_report_sync():
        from src.agents.question_generator import SkillsMatrix
        from src.agents.response_evaluator import evaluate_response
        from src.report_generator import generate_report
        from src.orchestrator import save_to_db

        matrix = SkillsMatrix(**_default_skills_matrix())
        assessments = []
        for row in answer_rows:
            idx = row["question_index"]
            question = row["question_text"] or (questions[idx] if idx < len(questions) else "")
            assessment = evaluate_response(row["transcript"], matrix, question)
            if assessment:
                assessments.append(assessment)

        report = generate_report(assessments, matrix)
        if report:
            save_to_db(session_id, report)
            report_conn = get_db_connection()
            try:
                report_conn.execute(
                    "UPDATE sessions SET status='awaiting_hr' WHERE id=?",
                    (session_id,),
                )
                report_conn.commit()
            finally:
                report_conn.close()

    await asyncio.to_thread(build_report_sync)


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class HRDecisionRequest(BaseModel):
    session_id: str
    decision:   str
    hr_user_id: str
    hr_notes:   Optional[str] = ""


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
# record.html is a static file — when opened via file:// its origin is "null".
# When served via Live Server or another local server it uses a different port.
# Added "null" and common dev-server ports so candidate POSTs are not blocked.

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:8001",
        "http://127.0.0.1:8001",
        "http://localhost:5500",   # VS Code Live Server
        "http://127.0.0.1:5500",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "null",                    # file:// origin (record.html opened directly)
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
    file:             UploadFile = File(...),
    name:             str        = Form(...),
    email:            str        = Form(...),
    consent_accepted: bool       = Form(...),
):
    if not consent_accepted:
        raise HTTPException(status_code=400, detail="Candidate consent is required.")

    if file.content_type != ALLOWED_CV_CONTENT_TYPE:
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    validate_file_size(file, MAX_CV_SIZE_MB)

    candidate_id = str(uuid.uuid4())
    session_id   = str(uuid.uuid4())

    upload_path  = Path(settings.UPLOAD_DIR) / f"cv_{candidate_id}.pdf"

    with open(upload_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    now  = datetime.now(timezone.utc).isoformat()
    conn = get_db_connection()

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO candidates
                (id, name, email, cv_path, session_id, consent_accepted, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (candidate_id, name, email, str(upload_path), session_id, 1, now),
        )

        cursor.execute(
            """
            INSERT INTO sessions (id, candidate_id, status, created_at)
            VALUES (?, ?, 'pending', ?)
            """,
            (session_id, candidate_id, now),
        )

        cursor.execute(
            """
            INSERT INTO reports (id, session_id, hr_decision)
            VALUES (?, ?, 'pending')
            """,
            (f"report_{session_id}", session_id),
        )

        conn.commit()

    except sqlite3.Error:
        raise HTTPException(status_code=500, detail="Database operation failed.")

    finally:
        conn.close()

    # Trigger orchestrator automatically in background
    async def run_orchestrator_bg():
        from src.orchestrator import orchestrator_app
        initial_state = {
            "candidate_id": candidate_id,
            "session_id": session_id,
            "cv_path": str(upload_path),
            "skills_matrix": _default_skills_matrix(),
            "cv_data": {},
            "questions": [],
            "transcripts": [],
            "assessments": [],
            "final_report": {},
            "status": ""
        }
        await asyncio.to_thread(orchestrator_app.invoke, initial_state)

    asyncio.create_task(run_orchestrator_bg())

    return {
        "message":      "CV uploaded successfully.",
        "candidate_id": candidate_id,
        "session_id":   session_id,
    }


# =============================================================================
# START INTERVIEW
# =============================================================================

@app.post("/start_interview")
async def start_interview(
    session_id:     str = Form(...),
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
            raise HTTPException(status_code=404, detail="Session not found.")

        conn.commit()

    finally:
        conn.close()

    return {"message": "Interview started.", "session_id": session_id}


# =============================================================================
# GET QUESTIONS  
# =============================================================================

@app.get("/get_questions")
async def get_questions(session_id: str):
    """
    Returns the AI-generated questions for a session so record.html can
    display them to the candidate.  The questions are stored as a JSON array
    in sessions.questions_json by the /start_interview endpoint (or directly
    by the LangGraph orchestrator).
    """
    conn = get_db_connection()

    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT questions_json FROM sessions WHERE id=?",
            (session_id,),
        )
        row = cursor.fetchone()

    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Session not found.")

    if not row["questions_json"]:
        raise HTTPException(
            status_code=404,
            detail="Questions not ready yet. Run the orchestrator first.",
        )

    return {"session_id": session_id, "questions": json.loads(row["questions_json"])}


# =============================================================================
# UPLOAD ANSWER
# =============================================================================

@app.post("/upload_answer")
async def upload_answer(
    session_id:     str        = Form(...),
    question_index: int        = Form(...),
    question_text:  str        = Form(""),   # FIX (Bug 3): was missing, now stored
    audio:          UploadFile = File(...),
):
    """
    Receives a voice answer from record.html, runs Whisper transcription,
    and stores everything in the answers table.

    FIX (Bug 3): question_text is now accepted and persisted so the evaluator
    agent always has the original question to evaluate the transcript against.

    FIX (Bug 4 / WARN): Whisper is called via run_in_executor so it does not
    block the async event loop during the 10–60 s transcription window.
    """
    # ── Consent check ────────────────────────────────────────────────────────
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

    finally:
        conn.close()

    if not consent_row:
        raise HTTPException(status_code=404, detail="Session not found.")

    if consent_row["consent_accepted"] != 1:
        raise HTTPException(status_code=403, detail="Consent required before recording.")

    # ── File validation & save ────────────────────────────────────────────────
    validate_file_size(audio, MAX_AUDIO_SIZE_MB)
    suffix    = validate_audio_extension(audio.filename or "audio.webm")
    answer_id = str(uuid.uuid4())
    audio_path = Path(settings.UPLOAD_DIR) / f"answer_{answer_id}{suffix}"

    with open(audio_path, "wb") as buffer:
        shutil.copyfileobj(audio.file, buffer)

    # ── Whisper transcription (non-blocking) ──────────────────────────────────
    loop       = asyncio.get_event_loop()
    transcript = await loop.run_in_executor(None, _transcribe_sync, str(audio_path))

    # ── Persist to DB ─────────────────────────────────────────────────────────
    conn = get_db_connection()

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO answers
                (id, session_id, question_index, question_text,
                 audio_path, transcript, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                answer_id,
                session_id,
                question_index,
                question_text,
                str(audio_path),
                transcript,
                datetime.now(timezone.utc).isoformat(),
            ),
        )

        conn.commit()

    finally:
        conn.close()

    await maybe_generate_report(session_id)

    return {
        "message":    "Answer uploaded successfully.",
        "answer_id":  answer_id,
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
        cursor.execute("SELECT * FROM reports WHERE session_id=?", (session_id,))
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
    """
    Records the HR decision in the database and writes ONE signed entry to the
    append-only audit log.

    Chainlit can record HR actions directly through app.py. API callers can use
    this endpoint; both paths use src.audit_log.log_decision for the same signed
    append-only format.
    """
    allowed = {"approve", "reject", "hold"}

    if request.decision not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Decision must be one of: {allowed}",
        )

    now  = datetime.now(timezone.utc).isoformat()
    conn = get_db_connection()

    try:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT ai_recommendation FROM reports WHERE session_id=?",
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
            SET hr_decision=?, hr_notes=?, hr_user_id=?, decided_at=?
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
    log_decision(
        candidate_id=candidate_id,
        ai_recommendation=ai_recommendation,
        hr_decision=request.decision,
        hr_notes=request.hr_notes or "",
        hr_user_id=request.hr_user_id,
    )

    return {
        "message":    f"HR decision '{request.decision}' recorded.",
        "session_id": request.session_id,
        "timestamp":  now,
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
