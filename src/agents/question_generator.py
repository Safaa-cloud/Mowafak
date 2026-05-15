import json
import logging
from pydantic import BaseModel, Field, ValidationError
from google import genai
from google.genai import types

from src.settings import GEMINI_API_KEY, GEMINI_MODEL
from src.cv_parser import CVData
from src.prompts import QUESTION_GENERATOR_PROMPT

# Configure secure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - QUESTION_GEN - %(message)s')

client = genai.Client(api_key=GEMINI_API_KEY)

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
        logging.info(f"Successfully generated {len(questions.questions)} tailored questions for {cv_data.name}.")
        return questions

    except json.JSONDecodeError:
        logging.error("Gemini output could not be decoded into JSON.")
        return None
    except ValidationError as ve:
        logging.error(f"Validation error while creating InterviewQuestions object: {ve}")
        return None
    except Exception as e:
        logging.error("An unexpected error occurred during question generation.")
        return None