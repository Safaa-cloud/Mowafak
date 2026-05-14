from settings import GEMINI_API_KEY, GEMINI_MODEL     #defined in settings.py
from pypdf import PdfReader
from pydantic import BaseModel, Field
from google import genai
import json
from prompts import CV_PARSER_PROMPT


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
    prompt = CV_PARSER_PROMPT.format(text=text)
    # 5. send the prompt to the Gemini API and get the response
    response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)

    response_text = response.text.strip()  # remove leading/trailing whitespace
    
    # remove markdown backticks if present
    if response_text.startswith("```"):
        response_text = response_text.split("```")[1]
    if response_text.startswith("json"):
        response_text = response_text[4:]

    try:
        data = json.loads(response_text)
        cv_data = CVData(**data)
        return cv_data
    except json.JSONDecodeError as e:
        print("Failed to parse JSON:", e)
        return None
