import logging
import json
from pypdf import PdfReader
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

from src.settings import GEMINI_API_KEY, GEMINI_MODEL 
from src.prompts import CV_PARSER_PROMPT

# Configure secure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - PARSER - %(message)s')

# 1. Define CV template using pydantic    
class CVData(BaseModel):
    name: str = Field(description="The name of the candidate")
    email: str = Field(description="The email address of the candidate")
    education: list[str] = Field(description="A list of the candidate education history")
    experience: list[str] = Field(description="A list of the candidate work experience")
    skills: list[str] = Field(description="A list of the candidate skills")

# 2. Define the client to interact with Gemini API
client = genai.Client(api_key=GEMINI_API_KEY)

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
        logging.info(f"Successfully parsed CV for candidate: {cv_data.name}")
        return cv_data

    except json.JSONDecodeError:
        logging.error("Gemini output could not be decoded into JSON.")
        return None
    except Exception as e:
        logging.error("An unexpected error occurred during AI parsing.")
        return None