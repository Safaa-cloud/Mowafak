import json
from pydantic import BaseModel, Field
from cv_parser import CVData
from question_generator import InterviewQuestions, SkillsMatrix
from google import genai
from settings import GEMINI_API_KEY, GEMINI_MODEL

# pydantic model to structure the evaluation of the candidate's response
class ResponseAssesment(BaseModel):
    relevance_score : int = Field(description="Relevance of the candidate's answer to the question on a scale of 1-5")
    clarity_score : int = Field(description="Clarity of the candidate's answer on a scale of 1-5")
    technical_depth_score : int = Field(description="Technical depth of the candidate's answer on a scale of 1-5")
    evidence_from_transcript : str = Field(description="Specific evidence from the candidate's answer transcript that supports the assigned scores")
    concerns: list[str] = Field(description="List of any concerns or red flags raised by the candidate's answer")

# define the client to interact with Gemini API
client = genai.Client(api_key=GEMINI_API_KEY)

# function to evaluate the candidate's response to an interview question based on the transcript of their answer, the skills matrix for the position, and the original question asked
def evaluate_response(transcript: str, skill_matrix: SkillsMatrix, original_question: str ) -> ResponseAssesment:
    prompt = f"""
    You are an expert HR interviewer. Given a Question, the candidate's answer on it and a skills matrix containing the required 
    skills and the good-to-have skills, evaluate the candidates answer.

    - Candidate's transcript: {transcript}
    - Skills matrix: {skill_matrix}
    - Original question: {original_question}

    Evaluate the candidate's answer based on the following criteria:
    1. Relevance: How relevant is the candidate's answer to the original question? (1-5)
    2. Clarity: How clear and well-structured is the candidate's answer? (1-5)
    3. Technical Depth: How technically deep and insightful is the candidate's answer? (1-5)
    4. Evidence from Transcript: Provide specific evidence from the candidate's answer transcript that supports the assigned scores.
    5. Concerns: List any concerns or red flags raised by the candidate's answer.

    Return the evaluation in a JSON format as follows:
    {{
    
    "relevance_score": 1-5,
    "clarity_score": 1-5,
    "technical_depth_score": 1-5,
    "evidence_from_transcript": "quote from transcript",
    "concerns": ["concern 1", "concern 2"]
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
        assessment = ResponseAssesment(**data)
        print("Response Assessment Generated!")
        return assessment
    except json.JSONDecodeError as e:
        print("Failed to parse JSON:", e)
        return None 
    


#TEST
if __name__ == "__main__":
    sample_transcript = r"I used TensorFlow to build a CNN model that achieved 95% accuracy on image classification"
    sample_question = "Tell me about your experience with TensorFlow"
    sample_skills = SkillsMatrix(
        required_skills=["Python", "TensorFlow", "SQL"],
        nice_to_have_skills=["Docker", "FastAPI"]
    )
    
    result = evaluate_response(sample_transcript, sample_skills, sample_question)
    print(result)
