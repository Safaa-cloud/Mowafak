from settings import GEMINI_API_KEY, GEMINI_MODEL
from pydantic import BaseModel, Field
import json
from google import genai
from src.cv_parser import CVData
from prompts import QUESTION_GENERATOR_PROMPT

client = genai.Client(api_key=GEMINI_API_KEY)

class SkillsMatrix(BaseModel):
    required_skills: list[str] = Field(description="List of required skills for the position")
    nice_to_have_skills : list[str] = Field(description="List of nice-to-have skills for the position")

class InterviewQuestions(BaseModel):
    questions : list[str] = Field(description="List of 3-5 tailored interview questions based on the CV and skills matrix")

def GenerateQuestions(cv_data: CVData, skills_matrix: SkillsMatrix):
    prompt = QUESTION_GENERATOR_PROMPT.format(
        cv_data=cv_data, 
        skills_matrix=skills_matrix
    )
    
    response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    response_text = response.text.strip()
    
    if response_text.startswith("```"):
        response_text = response_text.split("```")[1]
    if response_text.startswith("json"):
        response_text = response_text[4:]

    try:
        data = json.loads(response_text)
        questions = InterviewQuestions(**data)
        print("✅ Questions Generated!")
        return questions
    except json.JSONDecodeError as e:
        print("❌ Failed to parse JSON:", e)
        return None