from pathlib import Path
import os

try:
    from dotenv import load_dotenv
except ImportError:  # Allows lightweight local checks before dependencies are installed.
    def load_dotenv(*args, **kwargs):
        return False

load_dotenv()

BASE_DIR = Path(__file__).parent.parent

def _sqlite_path(value: str | None) -> str:
    """Return a filesystem path sqlite3 can open, accepting sqlite:/// URLs."""
    if not value:
        return str(BASE_DIR / "mowafak.db")

    if value.startswith("sqlite:///"):
        value = value.removeprefix("sqlite:///")

    path = Path(value)
    if not path.is_absolute():
        path = BASE_DIR / path
    return str(path)


class Settings:
    def __init__(self):
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
        self.GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        self.WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
        self.DATABASE_URL = _sqlite_path(os.getenv("DATABASE_URL"))
        self.RESPONSIBLE_AI_DIR = BASE_DIR / "responsible_ai"
        self.AUDIT_LOG_PATH = os.getenv(
            "AUDIT_LOG_PATH",
            str(self.RESPONSIBLE_AI_DIR / "audit_log.jsonl"),
        )
        self.BACKEND_HOST = os.getenv("BACKEND_HOST", "0.0.0.0")
        self.BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8001"))
        self.UPLOAD_DIR = os.getenv("UPLOAD_DIR", str(BASE_DIR / "data" / "uploads"))
        self.MAX_TOOL_CALLS = int(os.getenv("MAX_TOOL_CALLS", "4"))
        self.BIAS_AUDIT_THRESHOLD = float(os.getenv("BIAS_AUDIT_THRESHOLD", "0.3"))

settings = Settings()

Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
Path(settings.AUDIT_LOG_PATH).parent.mkdir(parents=True, exist_ok=True)

GEMINI_API_KEY = settings.GEMINI_API_KEY
GEMINI_MODEL = settings.GEMINI_MODEL


def get_settings() -> Settings:
    return settings
