from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import shutil
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
import sys
import json
from contextlib import asynccontextmanager

sys.path.append(str(Path(__file__).parent.parent))
from src.settings import settings

def get_db_connection():
    conn = sqlite3.connect(settings.DATABASE_URL, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS candidates (
            id          TEXT PRIMARY KEY,
            name        TEXT,
            email       TEXT,
            cv_path     TEXT,
            session_id  TEXT,
            created_at  TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id              TEXT PRIMARY KEY,
            candidate_id    TEXT,
            status          TEXT DEFAULT 'pending',
            questions_json  TEXT,
            created_at      TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS answers (
            id              TEXT PRIMARY KEY,
            session_id      TEXT,
            question_index  INTEGER,
            audio_path      TEXT,
            transcript      TEXT,
            created_at      TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id              TEXT PRIMARY KEY,
            session_id      TEXT,
            report_json     TEXT,
            hr_decision     TEXT,
            hr_notes        TEXT,
            hr_user_id      TEXT,
            decided_at      TEXT
        )
    """)
    conn.commit()
    conn.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title="Mowafak AI Pre-Screen API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}

@app.post("/upload_cv")
async def upload_cv(
    file: UploadFile = File(...),
    name: str = Form(...),
    email: str = Form(...),
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    candidate_id = str(uuid.uuid4())
    upload_path = Path(settings.UPLOAD_DIR) / f"cv_{candidate_id}.pdf"

    with open(upload_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO candidates (id, name, email, cv_path, session_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (candidate_id, name, email, str(upload_path), session_id, now),
    )
    cursor.execute(
        "INSERT INTO sessions (id, candidate_id, status, created_at) VALUES (?, ?, 'pending', ?)",
        (session_id, candidate_id, now),
    )
    conn.commit()
    conn.close()

    return {
        "message": "CV uploaded successfully.",
        "candidate_id": candidate_id,
        "session_id": session_id,
        "cv_path": str(upload_path),
    }

@app.post("/start_interview")
async def start_interview(
    session_id: str = Form(...),
    questions_json: str = Form(...),
):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE sessions SET status='in_progress', questions_json=? WHERE id=?",
        (questions_json, session_id),
    )
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Session not found.")
    conn.commit()
    conn.close()
    return {"message": "Interview started.", "session_id": session_id}

@app.post("/upload_answer")
async def upload_answer(
    session_id: str = Form(...),
    question_index: int = Form(...),
    audio: UploadFile = File(...),
):
    answer_id = str(uuid.uuid4())
    suffix = Path(audio.filename).suffix if audio.filename else ".webm"
    audio_path = Path(settings.UPLOAD_DIR) / f"answer_{answer_id}{suffix}"

    with open(audio_path, "wb") as buffer:
        shutil.copyfileobj(audio.file, buffer)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO answers (id, session_id, question_index, audio_path, transcript, created_at) VALUES (?, ?, ?, ?, NULL, ?)",
        (answer_id, session_id, question_index, str(audio_path), datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()

    return {
        "message": "Answer uploaded successfully.",
        "answer_id": answer_id,
        "audio_path": str(audio_path),
    }

@app.get("/get_report")
async def get_report(session_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reports WHERE session_id=?", (session_id,))
    report = cursor.fetchone()
    conn.close()

    if report is None:
        raise HTTPException(status_code=404, detail="Report not found. It may still be generating.")

    return dict(report)

@app.post("/hr_decision")
async def hr_decision(
    session_id: str = Form(...),
    decision: str = Form(...),
    hr_user_id: str = Form(...),
    hr_notes: str = Form(""),
):
    allowed = {"approve", "reject", "hold"}
    if decision not in allowed:
        raise HTTPException(status_code=400, detail=f"Decision must be one of: {allowed}")

    now = datetime.now(timezone.utc).isoformat()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE reports SET hr_decision=?, hr_notes=?, hr_user_id=?, decided_at=? WHERE session_id=?",
        (decision, hr_notes, hr_user_id, now, session_id),
    )

    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Report not found for this session.")

    cursor.execute("SELECT candidate_id FROM sessions WHERE id=?", (session_id,))
    session_row = cursor.fetchone()
    conn.commit()
    conn.close()

    candidate_id = dict(session_row)["candidate_id"] if session_row else "unknown"

    audit_entry = {
        "timestamp": now,
        "candidate_id": candidate_id,
        "session_id": session_id,
        "hr_decision": decision,
        "hr_user_id": hr_user_id,
        "hr_notes_hash": str(hash(hr_notes)),
    }

    Path(settings.AUDIT_LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(settings.AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(audit_entry) + "\n")

    return {
        "message": f"HR decision '{decision}' recorded.",
        "session_id": session_id,
        "timestamp": now,
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.BACKEND_HOST,
        port=settings.BACKEND_PORT,
        reload=True,
    )