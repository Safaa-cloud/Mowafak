import json
import logging
from pydantic import BaseModel, Field, ValidationError
try:
    from google import genai
    from google.genai import types
except Exception:
    genai = None
    types = None

from src.settings import GEMINI_API_KEY, GEMINI_MODEL
from src.agents.question_generator import SkillsMatrix
from src.prompts import RESPONSE_EVALUATOR_PROMPT

# Configure secure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - EVALUATOR - %(message)s')

# FIXED TYPO: ResponseAssesment -> ResponseAssessment
class ResponseAssessment(BaseModel):
    relevance_score: int = Field(description="Relevance of the candidate's answer to the question on a scale of 1-5")
    clarity_score: int = Field(description="Clarity of the candidate's answer on a scale of 1-5")
    technical_depth_score: int = Field(description="Technical depth of the candidate's answer on a scale of 1-5")
    evidence_from_transcript: str = Field(description="Specific evidence from the candidate's answer transcript that supports the assigned scores")
    concerns: list[str] = Field(description="List of any concerns or red flags raised by the candidate's answer")

client = genai.Client(api_key=GEMINI_API_KEY) if genai and GEMINI_API_KEY else None

def evaluate_response(transcript: str, skill_matrix: SkillsMatrix, original_question: str) -> ResponseAssessment | None:
    """Evaluates a single candidate answer using Native Structured Outputs."""
    
    if not transcript or not original_question:
        logging.warning("Missing transcript or original question. Skipping evaluation.")
        return None

    if client is None:
        return _evaluate_response_locally(transcript, skill_matrix, original_question)

    prompt = RESPONSE_EVALUATOR_PROMPT.format(
        transcript=transcript, 
        skill_matrix=skill_matrix, 
        original_question=original_question
    )
    
    try:
        # Force Gemini to output the exact ResponseAssessment schema
        response = client.models.generate_content(
            model=GEMINI_MODEL, 
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ResponseAssessment,
                temperature=0.1, # Low temperature for strict, objective grading
            )
        )

        data = json.loads(response.text)
        assessment = ResponseAssessment(**data)
        logging.info(f"Successfully evaluated response. Relevance Score: {assessment.relevance_score}/5")
        return assessment

    except json.JSONDecodeError:
        logging.error("Gemini output could not be decoded into JSON.")
        return None
    except ValidationError as ve:
        logging.error(f"Validation error while creating ResponseAssessment object: {ve}")
        return None
    except Exception as e:
        logging.error("An unexpected error occurred during response evaluation.")
        return _evaluate_response_locally(transcript, skill_matrix, original_question)


def _score_from_transcript(transcript: str, skills: list[str]) -> tuple[int, int, int]:
    words = transcript.split()
    word_count = len(words)
    skill_hits = sum(1 for skill in skills if skill.lower() in transcript.lower())
    relevance = 4 if word_count >= 35 else 3 if word_count >= 15 else 2
    clarity = 4 if any(token in transcript.lower() for token in ["because", "first", "then", "so", "result"]) else 3
    technical = min(5, max(2, 2 + skill_hits + (1 if word_count >= 50 else 0)))
    return relevance, clarity, technical


def _evidence_quote(transcript: str) -> str:
    clean = " ".join(transcript.split())
    if not clean:
        return "[No speech detected]"
    return clean[:220]


def _evaluate_response_locally(
    transcript: str,
    skill_matrix: SkillsMatrix,
    original_question: str,
) -> ResponseAssessment:
    skills = (skill_matrix.required_skills or []) + (skill_matrix.nice_to_have_skills or [])
    relevance, clarity, technical = _score_from_transcript(transcript, skills)
    concerns = []
    if len(transcript.split()) < 20:
        concerns.append("Answer is brief and may need follow-up evidence.")
    if technical <= 2:
        concerns.append("Limited explicit technical detail in the transcript.")
    return ResponseAssessment(
        relevance_score=relevance,
        clarity_score=clarity,
        technical_depth_score=technical,
        evidence_from_transcript=_evidence_quote(transcript),
        concerns=concerns,
    )


class ResponseEvaluator:
    """Compatibility wrapper used by the bias audit and tests."""

    async def evaluate(
        self,
        question: str,
        transcript: str,
        skills_required: list[str] | None = None,
    ) -> ResponseAssessment:
        matrix = SkillsMatrix(
            required_skills=skills_required or ["Python", "SQL"],
            nice_to_have_skills=[],
        )
        assessment = evaluate_response(transcript, matrix, question)
        if assessment is None:
            return _evaluate_response_locally(transcript, matrix, question)
        return assessment
