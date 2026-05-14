import json
from pydantic import BaseModel, Field, ValidationError
from cv_parser import CVData
from question_generator import InterviewQuestions, SkillsMatrix
from google import genai
from settings import GEMINI_API_KEY, GEMINI_MODEL
from prompts import RESPONSE_EVALUATOR_PROMPT

class ResponseAssesment(BaseModel):
    relevance_score : int = Field(description="Relevance of the candidate's answer to the question on a scale of 1-5")
    clarity_score : int = Field(description="Clarity of the candidate's answer on a scale of 1-5")
    technical_depth_score : int = Field(description="Technical depth of the candidate's answer on a scale of 1-5")
    evidence_from_transcript : str = Field(description="Specific evidence from the candidate's answer transcript that supports the assigned scores")
    concerns: list[str] = Field(description="List of any concerns or red flags raised by the candidate's answer")

client = genai.Client(api_key=GEMINI_API_KEY)

def evaluate_response(transcript: str, skill_matrix: SkillsMatrix, original_question: str ) -> ResponseAssesment:
    prompt = RESPONSE_EVALUATOR_PROMPT.format(
        transcript=transcript, 
        skill_matrix=skill_matrix, 
        original_question=original_question
    )
    
    response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    response_text = response.text.strip()
    
    if response_text.startswith("```"):
        response_text = response_text.split("```")[1]
    if response_text.startswith("json"):
        response_text = response_text[4:]

    try:
        data = json.loads(response_text)
        assessment = ResponseAssesment(**data)
        print("✅ Response Assessment Generated!")
        return assessment
    except json.JSONDecodeError as e:
        print("❌ Failed to parse JSON:", e)
        return None 
    except ValidationError as e:
        print("❌ Pydantic validation error:", e)
        return None