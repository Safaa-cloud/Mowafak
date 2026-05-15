import json
import logging
from pydantic import BaseModel, Field, ValidationError
from google import genai
from google.genai import types

from src.settings import GEMINI_API_KEY, GEMINI_MODEL
from src.prompts import REPORT_GENERATOR_PROMPT
from src.agents.response_evaluator import ResponseAssesment
from src.agents.question_generator import SkillsMatrix

# Configure secure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - REPORT_GEN - %(message)s')

# Define the structure of the final report using a pydantic model
class Report(BaseModel):
    overall_score: float = Field(description="Overall score for the candidate (1-5)")
    per_skill_ratings: dict[str, float] = Field(description="Per-skill ratings for the candidate")
    recommendation: str = Field(description="Final recommendation for the candidate (strong / average / weak)")
    summary: str = Field(description="Written summary of the candidate's performance in the interview")

# Define the client to interact with Gemini API
client = genai.Client(api_key=GEMINI_API_KEY)

def generate_report(assessments: list[ResponseAssesment], skills_matrix: SkillsMatrix) -> Report | None:
    """Generates the final candidate report using Native Structured Outputs."""
    
    if not assessments or not skills_matrix:
        logging.error("Missing assessments or skills matrix. Cannot generate report.")
        return None

    prompt = REPORT_GENERATOR_PROMPT.format(
        assessments=assessments, 
        skills_matrix=skills_matrix
    )
    
    try:
        # Force Gemini to output the exact Report schema using GenerateContentConfig
        response = client.models.generate_content(
            model=GEMINI_MODEL, 
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=Report,
                temperature=0.2, # Low temperature for objective summarization
            )
        )

        data = json.loads(response.text)
        report = Report(**data)
        logging.info(f"Final HR Report generated successfully with recommendation: {report.recommendation}")
        return report

    except json.JSONDecodeError:
        logging.error("Gemini output could not be decoded into JSON.")
        return None
    except ValidationError as ve:
        logging.error(f"Validation error while creating Report object: {ve}")
        return None
    except Exception as e:
        logging.error("An unexpected error occurred during report generation.")
        return None