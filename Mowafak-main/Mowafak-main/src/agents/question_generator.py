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
from src.cv_parser import CVData
from src.prompts import QUESTION_GENERATOR_PROMPT

# Configure secure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - QUESTION_GEN - %(message)s')

client = genai.Client(api_key=GEMINI_API_KEY) if genai and GEMINI_API_KEY else None

class SkillsMatrix(BaseModel):
    required_skills: list[str] = Field(description="List of required skills for the position")
    nice_to_have_skills: list[str] = Field(description="List of nice-to-have skills for the position")

class InterviewQuestions(BaseModel):
    questions: list[str] = Field(description="List of 3-5 tailored interview questions based on the CV and skills matrix")

def generate_questions(cv_data: CVData, skills_matrix: SkillsMatrix) -> InterviewQuestions | None:
    """Generates personalized interview questions using Native Structured Outputs."""
    
    if not cv_data or not skills_matrix:
        logging.error("Missing CV Data or Skills Matrix. Cannot generate questions.")
        return None

    if client is None:
        return _generate_questions_locally(cv_data, skills_matrix)

    prompt = QUESTION_GENERATOR_PROMPT.format(
        cv_data=cv_data, 
        skills_matrix=skills_matrix
    )
    
    try:
        # Force Gemini to output the exact InterviewQuestions schema
        response = client.models.generate_content(
            model=GEMINI_MODEL, 
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=InterviewQuestions,
                temperature=0.7, # Slightly higher temperature for creative, tailored questions
            )
        )

        data = json.loads(response.text)
        questions = InterviewQuestions(**data)
        logging.info("Successfully generated %d tailored questions.", len(questions.questions))
        return questions

    except json.JSONDecodeError:
        logging.error("Gemini output could not be decoded into JSON.")
        return None
    except ValidationError as ve:
        logging.error(f"Validation error while creating InterviewQuestions object: {ve}")
        return None
    except Exception as e:
        logging.error("An unexpected error occurred during question generation.")
        return _generate_questions_locally(cv_data, skills_matrix)


def _generate_questions_locally(cv_data: CVData, skills_matrix: SkillsMatrix) -> InterviewQuestions:
    """Deterministic fallback that keeps the demo usable without an LLM key."""
    skills = cv_data.skills or skills_matrix.required_skills or ["Python"]
    experience = cv_data.experience[0] if cv_data.experience else "one of your projects"
    education = cv_data.education[0] if cv_data.education else "your background"
    required = skills_matrix.required_skills or skills[:2]

    questions = [
        f"You listed {skills[0]} on your CV. Describe a project where you used it and the trade-off you had to make.",
        f"Your CV mentions {experience}. What was your specific contribution and how did you measure success?",
        f"Based on {education}, which concept best prepared you for a junior developer role and why?",
        f"For this role we need {', '.join(required[:3])}. Which of these skills is strongest for you, and what evidence from your work supports that?",
    ]
    return InterviewQuestions(questions=questions[:5])
