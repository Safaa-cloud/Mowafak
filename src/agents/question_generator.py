from settings import GEMINI_API_KEY, GEMINI_MODEL  # defined in settings.py
from pydantic import BaseModel, Field
import json
from google import genai
from cv_parser import CVData

# 1. define the client to interact with Gemini API
client = genai.Client(api_key=GEMINI_API_KEY)


# 2. define the structure of the skills matrix and interview questions using pydantic models
class SkillsMatrix(BaseModel):
    required_skills: list[str] = Field(description="List of required skills for the position")
    nice_to_have_skills : list[str] = Field(description="List of nice-to-have skills for the position")


class InterviewQuestions(BaseModel):
    questions : list[str] = Field(description="List of 3-5 tailored interview questions based on the CV and skills matrix")



# 3. function to generate interview questions based on the candidate's CV and the skills matrix for the position
def GenerateQuestions(cv_data: CVData, skills_matrix: SkillsMatrix):
    prompt = f"""
    You are an expert HR interviewer. Given the candidate's CV and the required and nice-to-have skills for the position,
    generate 3-5 tailored interview questions that will validate the candidate's suitability to the position.

    Candidate's info from CV:
    - name = {cv_data.name}
    - education = {cv_data.education}
    - skills = {cv_data.skills}
    - experience = {cv_data.experience}

    Position requirements:
    - required skills = {skills_matrix.required_skills}
    - nice-to-have skills = {skills_matrix.nice_to_have_skills}

    Return the questions in a JSON format as follows:
    {{
        "questions": ["queston 1", "question 2", "question 3"]
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
        questions = InterviewQuestions(**data)
        print("Questions Generated!")
        return questions
    except json.JSONDecodeError as e:
        print("Failed to parse JSON:", e)
        return None 

#TEST
if __name__ == "__main__":
    skills_matrix = SkillsMatrix(
        required_skills=["Python", "Machine Learning", "SQL"],
        nice_to_have_skills=["TensorFlow", "Docker", "FastAPI"]
    )

    # sample cv_data to test with (replace with real parsed CV later)
    sample_cv = CVData(
        name="Ahmed Mohamed",
        email="ahmed@gmail.com",
        education=["BSc Computer Science - Ain Shams University 2024"],
        experience=["ML Engineer Intern at XYZ Company - built recommendation system"],
        skills=["Python", "TensorFlow", "SQL", "scikit-learn"]
    )

    result = GenerateQuestions(sample_cv, skills_matrix)
    if result:
        for i, q in enumerate(result.questions, 1):
            print(f"Q{i}: {q}")
            print("="*120)
