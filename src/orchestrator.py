import os
import sys
import sqlite3
import logging
from typing import TypedDict, List
from langgraph.graph import StateGraph, END
import json

# Add the parent directory to the path so 'src' module can be found
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Synchronized imports from your agents
from src.cv_parser import parse_cv, extract_text_from_pdf, CVData
from src.agents.question_generator import generate_questions, SkillsMatrix
from src.agents.response_evaluator import evaluate_response
from src.report_generator import generate_report

logger = logging.getLogger(__name__)

# ==========================================
# 1. Define the Graph State
# ==========================================
class InterviewState(TypedDict):
    """Represents the system state at any point in the pipeline."""
    candidate_id: str
    session_id: str  # Added to match backend session tracking
    cv_path: str
    skills_matrix: dict
    cv_data: dict
    questions: List[str]
    transcripts: List[str]  # Whisper outputs
    assessments: List[any]  # Evaluation results (Pydantic objects)
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
    # Store as dict for state serializability
    return {"cv_data": cv_results.model_dump() if cv_results else {}}

def question_generation_node(state: InterviewState):
    print("--- STEP 2: GENERATING QUESTIONS ---")
    matrix = SkillsMatrix(**state['skills_matrix'])
    cv_data_obj = CVData(**state['cv_data'])
    questions_obj = generate_questions(cv_data_obj, matrix)
    questions = questions_obj.questions if questions_obj else []
    
    # Save questions to DB for the candidate page
    if questions and state['session_id']:
        db_path = os.path.join(os.getcwd(), 'data', 'mowafak.db')
        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE sessions SET questions_json=? WHERE id=?",
            (json.dumps(questions), state['session_id'])
        )
        conn.commit()
        conn.close()
        print(f"Questions saved to DB for session {state['session_id']}")
    
    return {"questions": questions}

def evaluation_node(state: InterviewState):
    """Step 3: Evaluate each answer transcript against its question."""
    print("--- STEP 3: EVALUATING RESPONSES ---")
    results = []
    matrix = SkillsMatrix(**state['skills_matrix'])
    
    for i, transcript in enumerate(state['transcripts']):
        if i < len(state['questions']):
            eval_res = evaluate_response(
                transcript=transcript,
                skill_matrix=matrix,
                original_question=state['questions'][i]
            )
            results.append(eval_res) # Keep as object for the reporter
    
    return {"assessments": results}

def report_generation_node(state: InterviewState):
    """Step 4: Summarize the entire interview into a final recommendation."""
    print("--- STEP 4: GENERATING FINAL REPORT ---")
    matrix = SkillsMatrix(**state['skills_matrix'])
    report = generate_report(state['assessments'], matrix)
    
    if report:
        # Sync with the 'reports' table for the HR UI
        save_to_db(state['session_id'], report)
        return {"final_report": report.model_dump(), "status": "Awaiting HR"}
    return {"status": "Failed"}

# ==========================================
# 3. Database Helper
# ==========================================
def save_to_db(session_id, report):
    """Saves AI findings to the reports table used by app.py."""
    db_path = os.path.join(os.getcwd(), 'data', 'mowafak.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Updated to match the backend/main.py schema
    cursor.execute('''
        UPDATE reports 
        SET report_json = ?, ai_recommendation = ?
        WHERE session_id = ?
    ''', (report.model_dump_json(), report.recommendation, session_id))
    
    conn.commit()
    conn.close()
    print(f"✅ AI Report saved for Session {session_id}. Ready for HR review.")

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


