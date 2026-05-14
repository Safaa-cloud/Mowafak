import os
import uuid
import shutil
import logging
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from whisper_stt import init_db, transcribe_and_save, get_transcripts_for_session


# ------------------------------------------------------------------ #
# App Setup
# ------------------------------------------------------------------ #
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Mowafak AI Pre-Screen API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path(os.getenv("AUDIO_DIR", "data/sample_recordings"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.on_event("startup")
def on_startup():
    init_db()
    logger.info("Mowafak API ready.")


# ------------------------------------------------------------------ #
# Upload Answer
# ------------------------------------------------------------------ #
@app.post("/upload_answer")
async def upload_answer(
    audio: UploadFile = File(...),
    session_id: str = Form(...),
    question_no: int = Form(...)
):
    try:
        # ---------------- Validation ----------------
        if not session_id.strip():
            raise HTTPException(
                status_code=400,
                detail="session_id is required"
            )

        if question_no < 1:
            raise HTTPException(
                status_code=400,
                detail="question_no must be >= 1"
            )

        if not audio.filename:
            raise HTTPException(
                status_code=400,
                detail="No audio file uploaded"
            )

        # -------- Keep original extension ----------
        ext = Path(audio.filename).suffix.lower()

        if ext not in [".wav", ".webm", ".mp3", ".m4a"]:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {ext}"
            )

        safe_filename = (
            f"{session_id}_q{question_no}_"
            f"{uuid.uuid4().hex[:8]}{ext}"
        )

        audio_path = UPLOAD_DIR / safe_filename

        # --------------- Save file ------------------
        with audio_path.open("wb") as buffer:
            shutil.copyfileobj(audio.file, buffer)

        logger.info(f"Audio saved: {audio_path}")

        # check file size
        if audio_path.stat().st_size == 0:
            raise HTTPException(
                status_code=400,
                detail="Uploaded audio file is empty"
            )

        # ------------- Transcribe -------------------
        logger.info("Starting transcription...")

        result = transcribe_and_save(
            session_id=session_id,
            question_no=question_no,
            audio_path=audio_path
        )

        logger.info("Transcription successful")

        return JSONResponse(
            status_code=200,
            content={
                "session_id": result["session_id"],
                "question_no": result["question_no"],
                "transcript": result["transcript"],
                "row_id": result["row_id"]
            }
        )

    except HTTPException:
        raise

    except RuntimeError as e:
        logger.error(f"Whisper RuntimeError: {str(e)}")
        raise HTTPException(
            status_code=422,
            detail=str(e)
        )

    except FileNotFoundError as e:
        logger.error(f"FileNotFoundError: {str(e)}")
        raise HTTPException(
            status_code=422,
            detail=str(e)
        )

    except Exception as e:
        logger.error(f"Unexpected Error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# ------------------------------------------------------------------ #
# Get Transcripts
# ------------------------------------------------------------------ #
@app.get("/get_transcripts/{session_id}")
def get_transcripts(session_id: str):
    rows = get_transcripts_for_session(session_id)

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No transcripts found for {session_id}"
        )

    safe_rows = [
        {
            "row_id": r["id"],
            "question_no": r["question_no"],
            "transcript": r["transcript"],
            "created_at": r["created_at"]
        }
        for r in rows
    ]

    return {
        "session_id": session_id,
        "transcripts": safe_rows
    }



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=True
    )