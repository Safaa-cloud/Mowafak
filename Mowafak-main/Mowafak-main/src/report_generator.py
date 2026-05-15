import json
import logging
from typing import Literal
from pydantic import BaseModel, Field, ValidationError

try:
    from google import genai
    from google.genai import types
except Exception:
    genai = None
    types = None

from src.settings import GEMINI_API_KEY, GEMINI_MODEL
from src.prompts import REPORT_GENERATOR_PROMPT
from src.agents.response_evaluator import ResponseAssessment
from src.agents.question_generator import SkillsMatrix

# Configure secure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - REPORT_GEN - %(message)s')

# Define the structure of the final report using a pydantic model
class Report(BaseModel):
    overall_score: float = Field(description="Overall score for the candidate (1-5)")
    per_skill_ratings: dict[str, float] = Field(description="Per-skill ratings for the candidate")
    recommendation: Literal["strong_yes", "weak_yes", "weak_no", "strong_no"] = Field(description="Final advisory recommendation")
    summary: str = Field(description="Written summary of the candidate's performance in the interview")
    assessments: list[ResponseAssessment] = Field(default_factory=list, description="Per-question assessments with transcript evidence")

# Define the client to interact with Gemini API
client = genai.Client(api_key=GEMINI_API_KEY) if genai and GEMINI_API_KEY else None

def generate_report(assessments: list[ResponseAssessment], skills_matrix: SkillsMatrix) -> Report | None:
    """Generates the final candidate report using Native Structured Outputs."""
    
    assessments = [item for item in assessments if item is not None]
    if not assessments or not skills_matrix:
        logging.error("Missing assessments or skills matrix. Cannot generate report.")
        return None

    if client is None:
        return _generate_report_locally(assessments, skills_matrix)

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
        return _generate_report_locally(assessments, skills_matrix)
    except ValidationError as ve:
        logging.error(f"Validation error while creating Report object: {ve}")
        return _generate_report_locally(assessments, skills_matrix)
    except Exception as e:
        logging.error("An unexpected error occurred during report generation.")
        return _generate_report_locally(assessments, skills_matrix)


def _generate_report_locally(
    assessments: list[ResponseAssessment],
    skills_matrix: SkillsMatrix,
) -> Report:
    avg = sum(
        (
            item.relevance_score
            + item.clarity_score
            + item.technical_depth_score
        ) / 3
        for item in assessments
    ) / len(assessments)

    if avg >= 4.25:
        recommendation = "strong_yes"
    elif avg >= 3.25:
        recommendation = "weak_yes"
    elif avg >= 2.25:
        recommendation = "weak_no"
    else:
        recommendation = "strong_no"

    skills = skills_matrix.required_skills + skills_matrix.nice_to_have_skills
    per_skill = {skill: round(avg, 2) for skill in skills}
    concern_count = sum(len(item.concerns) for item in assessments)
    summary = (
        f"The candidate averaged {avg:.1f}/5 across relevance, clarity, and technical depth. "
        f"The report includes transcript evidence for every answer and remains advisory until HR review."
    )
    if concern_count:
        summary += f" HR should review {concern_count} noted concern(s) before deciding."

    return Report(
        overall_score=round(avg, 2),
        per_skill_ratings=per_skill,
        recommendation=recommendation,
        summary=summary,
        assessments=assessments,
    )
