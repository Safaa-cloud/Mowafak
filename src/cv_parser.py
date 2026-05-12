from settings import GEMINI_API_KEY, GEMINI_MODEL     #defined in settings.py
from pypdf import PdfReader
from pydantic import BaseModel, Field
from google import genai
import json

# local path to the CV PDF file for testing
file = r"E:\VS Code stuff\LangChain\Graduation_Project\testind pypdf.pdf"

# 1. Extract text from PDF: read file -> extract -> return raw text
def extract_text_from_pdf(file):
    reader = PdfReader(file)
    text = ""
    pages = reader.pages
    for page in pages:
        text += page.extract_text()
    print("Extraction Done!")
    return text
    
    
# 2. define CV template using pydantic    
class CVData(BaseModel):
    name: str = Field(description="The name of the candidate")
    email: str = Field(description="The email address of the candidate")
    education: list[str] = Field(description="A list of the candidate education history")
    experience: list[str] = Field(description="A list of the candidate work experience")
    skills: list[str] = Field(description="A list of the candidate skills")


# 3. define the client to interact with Gemini API
client = genai.Client(api_key=GEMINI_API_KEY)



def parse_cv(text):
    #4. define prompt to instruct the model to extract the required information from the CV text 
    # then return it in a JSON format that matches the CVData structure
    prompt = f"""
            You are a helpful assistant for parsing CVs. Extract the following information from the CV text:
            1. Candidate's name
            2. Candidate's email address
            3. Candidate's education history as a list
            4. Candidate's work experience as a list
            5. Candidate's skills as a list
            Here is the CV text: {text}
            Return the extracted information in a JSON format with the following structure:
            {{
                "name": "extracted name",
                "email": "extracted email",
                "education": ["education item 1", "education item 2", ...],
                "experience": ["experience item 1", "experience item 2", ...],
                "skills": ["skill 1", "skill 2", ...]
            }}

            Return ONLY the JSON. No markdown, no backticks, no explanation.

"""
    # 5. send the prompt to the Gemini API and get the response
    response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)

    response_text = response.text
    try:
        data = json.loads(response_text)
        cv_data = CVData(**data)
        return cv_data
    except json.JSONDecodeError as e:
        print("Failed to parse JSON:", e)
        return None

# test the whole pipeline
if __name__ == "__main__":
    raw_text = extract_text_from_pdf(file)
    cv_data = parse_cv(raw_text)
    print(cv_data)
