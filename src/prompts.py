CV_PARSER_PROMPT = f"""
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
###############################################################################################################################
QUESTION_GENERATOR_PROMPT = f"""
    You are an expert HR interviewer. Given the candidate's CV and the required and nice-to-have skills for the position,
    generate 3-5 tailored interview questions that will validate the candidate's suitability to the position.

    CRITICAL INSTRUCTION: Questions MUST explicitly reference specific items from the candidate's CV."

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
############################################################################################################################

RESPONSE_EVALUATOR_PROMPT = f"""
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

###########################################################################################################################
REPORT_GENERATOR_PROMPT = f"""
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