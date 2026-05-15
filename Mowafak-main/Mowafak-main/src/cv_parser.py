import logging
import json
import re
from pypdf import PdfReader
from pydantic import BaseModel, Field

try:
    from google import genai
    from google.genai import types
except Exception:
    genai = None
    types = None

from src.settings import GEMINI_API_KEY, GEMINI_MODEL 
from src.prompts import CV_PARSER_PROMPT

# Configure secure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - PARSER - %(message)s')

# 1. Define CV template using pydantic    
class CVData(BaseModel):
    name: str = Field(default="", description="The name of the candidate")
    email: str = Field(default="", description="The email address of the candidate")
    education: list[str] = Field(default_factory=list, description="A list of the candidate education history")
    experience: list[str] = Field(default_factory=list, description="A list of the candidate work experience")
    skills: list[str] = Field(default_factory=list, description="A list of the candidate skills")

# 2. Define the client to interact with Gemini API
client = genai.Client(api_key=GEMINI_API_KEY) if genai and GEMINI_API_KEY else None

def extract_text_from_pdf(file) -> str:
    """Extracts raw text from an uploaded PDF file."""
    try:
        reader = PdfReader(file)
        text = "".join([page.extract_text() for page in reader.pages])
        logging.info("PDF extraction completed successfully.")
        return text
    except Exception as e:
        logging.error("Failed to read PDF file format.")
        return ""

def parse_cv(text: str) -> CVData | None:
    """Sends CV text to Gemini and forces it to return the exact CVData JSON structure."""
    if not text:
        logging.error("No text provided to the parser.")
        return None

    if client is None:
        return _parse_cv_locally(text)

    prompt = CV_PARSER_PROMPT.format(text=text)
    
    try:
        # We use GenerateContentConfig to FORCE Gemini to output our Pydantic schema
        response = client.models.generate_content(
            model=GEMINI_MODEL, 
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=CVData,
                temperature=0.1, # Low temperature for strict factual extraction
            )
        )

        data = json.loads(response.text)
        cv_data = CVData(**data)
        logging.info("Successfully parsed CV for candidate_id pending assignment.")
        return cv_data

    except json.JSONDecodeError:
        logging.error("Gemini output could not be decoded into JSON.")
        return None
    except Exception as e:
        logging.error("An unexpected error occurred during AI parsing.")
        return _parse_cv_locally(text)


def _parse_cv_locally(text: str) -> CVData:
    """Small deterministic fallback for demos without a Gemini key."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    email_match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text)
    skill_vocab = [
        "Python", "JavaScript", "TypeScript", "SQL", "FastAPI", "Django",
        "React", "Machine Learning", "TensorFlow", "PyTorch", "Docker",
        "Git", "Data Analysis", "LangChain", "APIs",
    ]
    lowered = text.lower()
    skills = [skill for skill in skill_vocab if skill.lower() in lowered]
    return CVData(
        name=lines[0] if lines else "Candidate",
        email=email_match.group(0) if email_match else "",
        education=[line for line in lines if "university" in line.lower() or "degree" in line.lower()][:3],
        experience=[line for line in lines if "experience" in line.lower() or "intern" in line.lower() or "developer" in line.lower()][:5],
        skills=skills or ["Python", "SQL"],
    )
