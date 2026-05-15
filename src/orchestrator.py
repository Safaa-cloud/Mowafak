import os
import sys
import sqlite3
import logging
import json
from typing import TypedDict, List
from langgraph.graph import StateGraph, END

# Add the parent directory to the path so 'src' module can be found
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Import unified settings to prevent database fragmentation
from src.settings import settings
from src.cv_parser import parse_cv, extract_text_from_pdf, CVData
from src.agents.question_generator import generate_questions, SkillsMatrix
from src.agents.response_evaluator import evaluate_response
from src.report_generator import generate_report, Report

logger = logging.getLogger(__name__)

# ==========================================
# 1. Define the Graph State
# ==========================================
class InterviewState(TypedDict):
    candidate_id: str
    session_id: str
    cv_path: str
    skills_matrix: dict
    cv_data: dict
    questions: List[str]
    transcripts: List[str]
    assessments: List[any]
    final_report: dict
    status: str

# ==========================================
# 2. Define the Nodes (The AI Workers)
# ==========================================

def parsing_node(state: InterviewState):
    raw_text = extract_text_from_pdf(state['cv_path'])
    cv_results = parse_cv(raw_text)
    return {"cv_data": cv_results.model_dump() if cv_results else CVData().model_dump()}

def question_generation_node(state: InterviewState):
    matrix = SkillsMatrix(**state['skills_matrix'])
    cv_data_obj = CVData(**(state.get('cv_data') or {}))
    questions_obj = generate_questions(cv_data_obj, matrix)
    questions = questions_obj.questions if questions_obj else []
    
    if questions and state['session_id']:
        # Pointing to the unified database URL
        conn = sqlite3.connect(settings.DATABASE_URL)
        conn.execute(
            "UPDATE sessions SET questions_json=? WHERE id=?",
            (json.dumps(questions), state['session_id'])
        )
        conn.commit()
        conn.close()
    
    return {"questions": questions}

def evaluation_node(state: InterviewState):
    results = []
    matrix = SkillsMatrix(**state['skills_matrix'])
    
    for i, transcript in enumerate(state['transcripts']):
        if i < len(state['questions']):
            eval_res = evaluate_response(
                transcript=transcript,
                skill_matrix=matrix,
                original_question=state['questions'][i]
            )
            if eval_res:
                results.append(eval_res)
    
    return {"assessments": results}

def report_generation_node(state: InterviewState):
    matrix = SkillsMatrix(**state['skills_matrix'])
    report = generate_report(state['assessments'], matrix)
    
    if report:
        save_to_db(state['session_id'], report)
        return {"final_report": report.model_dump(), "status": "Awaiting HR"}
    return {"status": "Failed"}

# ==========================================
# 3. Database Helper
# ==========================================
def _report_json(report: Report) -> str:
    return report.model_dump_json()


def save_to_db(session_id, report):
    conn = sqlite3.connect(settings.DATABASE_URL)
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE reports 
        SET report_json = ?, ai_recommendation = ?, hr_decision = COALESCE(hr_decision, 'pending')
        WHERE session_id = ?
    ''', (report.model_dump_json(), report.recommendation, session_id))

    if cursor.rowcount == 0:
        cursor.execute(
            '''
            INSERT INTO reports
                (id, session_id, report_json, ai_recommendation, hr_decision)
            VALUES (?, ?, ?, ?, 'pending')
            ''',
            (
                f"report_{session_id}",
                session_id,
                _report_json(report),
                report.recommendation,
            ),
        )
    
    conn.commit()
    conn.close()

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
orchestrator_app = workflow.compile()


class MowafakOrchestrator:
    """Small compatibility facade around the LangGraph workflow."""

    def run(self, initial_state: InterviewState):
        return orchestrator_app.invoke(initial_state)

    async def evaluate_response(self, question: str, transcript: str, candidate_name: str = ""):
        matrix = SkillsMatrix(required_skills=["Python", "Machine Learning", "SQL"], nice_to_have_skills=[])
        return evaluate_response(transcript=transcript, skill_matrix=matrix, original_question=question)
