import json
from settings import GEMINI_API_KEY, GEMINI_MODEL
from response_evaluator import evaluate_response, ResponseAssesment
from google import genai
from question_generator import SkillsMatrix
from pydantic import BaseModel, Field, ValidationError

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
    prompt = f"""
    You are an expert HR interviewer. Given the assessments of a candidate's responses to the interview questions
    and the skills matrix for the position, generate a final report about the candidate's performance in the interview.

    - Assessments: {assessments}
    - Skills Matrix : {skills_matrix}

    Return the recommendation and the summary in a JSON format as follows:
    {{
    overall_score: "average score across all responses (1-5)",
    per_skill_ratings: {{"skill 1": rating, "skill 2": rating, ...}},
    recommendation: "strong_yes" / "weak_yes" / "weak_no" / "strong_no",
    summary: "written summary of the candidate's performance in the interview"
    }}
    Return ONLY the JSON without any additional text or explanation.
"""
    
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
      

#TEST
if __name__ == "__main__":
    # Example usage
    assessments = [
        ResponseAssesment(
            relevance_score=4,
            clarity_score=5,
            technical_depth_score=4,
            evidence_from_transcript="The candidate provided a clear and relevant answer to the question about their experience with Python.",
            concerns=["The candidate seemed unsure about their experience with machine learning frameworks."]
        ),
        ResponseAssesment(
            relevance_score=3,
            clarity_score=4,
            technical_depth_score=3,
            evidence_from_transcript="The candidate's answer about their experience with cloud platforms was somewhat relevant but lacked depth.",
            concerns=["The candidate did not mention specific cloud platforms they have experience with."]
        )
    ]

    skills_matrix = SkillsMatrix(
        required_skills=["Python", "Machine Learning", "Cloud Platforms"],
        nice_to_have_skills=["Docker", "Kubernetes"]
    )
    report = generate_report(assessments, skills_matrix)
    print(report)
