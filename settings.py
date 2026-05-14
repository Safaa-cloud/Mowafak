import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()

BASE_DIR = Path(__file__).parent.parent

class Settings(BaseSettings):
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-1.5-flash"
    WHISPER_MODEL: str = "base"
    DATABASE_URL: str = str(BASE_DIR / "mowafak.db")
    AUDIT_LOG_PATH: str = str(BASE_DIR / "responsible_ai" / "audit_log.jsonl")
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8001
    UPLOAD_DIR: str = str(BASE_DIR / "data" / "uploads")
    MAX_TOOL_CALLS: int = 4

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

settings = Settings()

Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)