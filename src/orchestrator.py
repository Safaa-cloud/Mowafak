import os
import sqlite3
from typing import TypedDict, List
from langgraph.graph import StateGraph, END

# Importing the AI modules we've reviewed and fixed
from src.agents.cv_parser import parse_cv, extract_text_from_pdf
from src.agents.question_generator import GenerateQuestions, SkillsMatrix
from src.agents.response_evaluator import evaluate_response
from src.agents.report_generator import generate_report
# ==========================================
# 1. Define the Graph State
# ==========================================
class InterviewState(TypedDict):
    """Represents the system state at any point in the pipeline."""
    candidate_id: str
    cv_path: str
    skills_matrix: dict
    cv_data: dict
    questions: List[str]
    transcripts: List[str]  # Whisper outputs (from the Audio Engineer)
    assessments: List[dict] # Evaluation results for each question
    final_report: dict
    status: str

# ==========================================
# 2. Define the Nodes (The AI Workers)
# ==========================================

def parsing_node(state: InterviewState):
    """Step 1: Convert the PDF CV into structured data."""
    print("--- STEP 1: PARSING CV ---")
    raw_text = extract_text_from_pdf(state['cv_path'])
    cv_results = parse_cv(raw_text)
    return {"cv_data": cv_results}

def question_generation_node(state: InterviewState):
    """Step 2: Generate tailored questions based on the parsed CV."""
    print("--- STEP 2: GENERATING QUESTIONS ---")
    matrix = SkillsMatrix(**state['skills_matrix'])
    questions_obj = GenerateQuestions(state['cv_data'], matrix)
    return {"questions": questions_obj.questions}

def evaluation_node(state: InterviewState):
    """Step 3: Evaluate each answer transcript against its question."""
    print("--- STEP 3: EVALUATING RESPONSES ---")
    results = []
    matrix = SkillsMatrix(**state['skills_matrix'])
    
    # Evaluate each transcript provided by the Audio module
    for i, transcript in enumerate(state['transcripts']):
        eval_res = evaluate_response(
            transcript=transcript,
            skill_matrix=matrix,
            original_question=state['questions'][i]
        )
        results.append(eval_res.dict())
    
    return {"assessments": results}

def report_generation_node(state: InterviewState):
    """Step 4: Summarize the entire interview into a final recommendation."""
    print("--- STEP 4: GENERATING FINAL REPORT ---")
    matrix = SkillsMatrix(**state['skills_matrix'])
    report = generate_report(state['assessments'], matrix)
    
    # Sync the AI results with the database for the HR UI (app.py)
    save_to_db(state['candidate_id'], report)
    
    return {"final_report": report.dict(), "status": "Awaiting HR"}

# ==========================================
# 3. Database Helper
# ==========================================
def save_to_db(cand_id, report):
    """Saves AI findings to mowafak.db so the HR dashboard can see them."""
    db_path = os.path.join(os.getcwd(), 'data', 'mowafak.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE interviews 
        SET ai_recommendation = ?, ai_score = ?
        WHERE candidate_id = ?
    ''', (report.recommendation, report.overall_score, cand_id))
    
    conn.commit()
    conn.close()
    print(f"✅ Data saved for Candidate {cand_id}. Ready for HR review.")

# ==========================================
# 4. Build the Graph
# ==========================================
workflow = StateGraph(InterviewState)

# Add Nodes
workflow.add_node("parser", parsing_node)
workflow.add_node("questioner", question_generation_node)
workflow.add_node("evaluator", evaluation_node)
workflow.add_node("reporter", report_generation_node)

# Set the flow (Edges)
workflow.set_entry_point("parser")
workflow.add_edge("parser", "questioner")
workflow.add_edge("questioner", "evaluator")
workflow.add_edge("evaluator", "reporter")
workflow.add_edge("reporter", END)

# Compile the final application
app = workflow.compile()