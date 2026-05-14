import json
from settings import GEMINI_API_KEY, GEMINI_MODEL
from agents.response_evaluator import evaluate_response, ResponseAssesment
from google import genai
from agents.question_generator import SkillsMatrix
from pydantic import BaseModel, Field, ValidationError
from prompts import REPORT_GENERATOR_PROMPT

# Define the structure of the final report using a pydantic model
class Report(BaseModel):
    overall_score: float = Field(description="Overall score for the candidate (1-5)")
    per_skill_ratings: dict[str, float] = Field(description="Per-skill ratings for the candidate")
    recommendation: str = Field(description="Final recommendation for the candidate (strong_yes / weak_yes / weak_no / strong_no)")
    summary: str = Field(description="Written summary of the candidate's performance in the interview")

# define the client to interact with Gemini API
client = genai.Client(api_key=GEMINI_API_KEY)


# function to generate the final report based on the assessments of the candidate's responses and the skills matrix for the position
def generate_report(assessments: list[ResponseAssesment], skills_matrix: SkillsMatrix) -> Report:
    prompt = REPORT_GENERATOR_PROMPT
    
    response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)

    response_text = response.text.strip()  # remove leading/trailing whitespace
    # remove markdown backticks if present
    if response_text.startswith("```"):
        response_text = response_text.split("```")[1]
    if response_text.startswith("json"):
        response_text = response_text[4:]   
    try:
        data = json.loads(response_text)
        report = Report(**data)
        print("Report Generated!")
        return report
    except json.JSONDecodeError as e:
        print("Failed to parse JSON:", e)
    except ValidationError as ve:
        print("Validation error while creating Report object:", ve)

