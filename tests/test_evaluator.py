import asyncio
import json
from pathlib import Path

from src.agents.question_generator import SkillsMatrix
from src.agents.response_evaluator import evaluate_response
from src.audit_log import log_decision
from src.hil_gate import HILGate
from responsible_ai.bias_audit import BiasAuditor


def test_evaluator_returns_transcript_evidence():
    matrix = SkillsMatrix(
        required_skills=["Python", "SQL"],
        nice_to_have_skills=["Docker"],
    )
    transcript = (
        "First I reproduced the payment bug, then I checked logs and found "
        "a SQL transaction race condition. I fixed it with an idempotent "
        "Python worker and added regression tests because reliability mattered."
    )

    result = evaluate_response(
        transcript=transcript,
        skill_matrix=matrix,
        original_question="Describe a production debugging problem.",
    )

    assert result is not None
    assert 1 <= result.relevance_score <= 5
    assert 1 <= result.clarity_score <= 5
    assert 1 <= result.technical_depth_score <= 5
    assert result.evidence_from_transcript
    assert "SQL" in result.evidence_from_transcript or "Python" in result.evidence_from_transcript


def test_hil_gate_does_not_expose_feedback_without_hr_action():
    gate = HILGate()

    assert not hasattr(gate, "auto_reject")
    assert not hasattr(gate, "send_decision")
    assert gate.verify_clearance("missing-candidate") is False


def test_audit_log_signed_entry(tmp_path, monkeypatch):
    audit_path = tmp_path / "audit_log.jsonl"
    monkeypatch.setattr("src.audit_log.get_log_paths", lambda: (str(audit_path), str(tmp_path / "audit.csv")))

    log_decision(
        candidate_id="cand-test",
        ai_recommendation="weak_yes",
        hr_decision="hold",
        hr_notes="Needs another reviewer.",
        hr_user_id="hr_mariam",
    )

    entry = json.loads(audit_path.read_text(encoding="utf-8").strip())
    assert entry["candidate_id"] == "cand-test"
    assert entry["hr_decision"] == "hold"
    assert entry["hr_notes_hash"]
    assert "hr_notes" not in entry
    assert entry["signature"]


def test_bias_audit_generates_name_variants():
    auditor = BiasAuditor()
    cases = auditor.generate_test_cases([
        {
            "question_id": "Q1",
            "base_name": "Ahmed Hassan",
            "question": "Tell me about your Python project.",
            "transcript": "Ahmed Hassan built a Python API with SQL persistence and tests.",
        }
    ])

    assert len(cases) == 4
    assert {case.gender for case in cases} == {"male", "female"}
    assert {case.ethnicity for case in cases} == {"egyptian", "western"}


def test_bias_audit_report_shape():
    auditor = BiasAuditor()
    report = auditor.run_quick_audit()

    assert report["total_cases_tested"] >= 1
    assert report["total_variants"] >= 4
    assert "threshold_used" in report
    assert Path("responsible_ai/bias_audit_report.json").exists()


def test_async_bias_audit_runs_with_local_evaluator():
    async def run():
        auditor = BiasAuditor()
        cases = auditor.generate_test_cases([
            {
                "question_id": "Q1",
                "base_name": "Mona Ibrahim",
                "question": "How do you debug a Python service?",
                "transcript": "I reproduce the issue, inspect Python logs, write a failing test, and ship a small fix.",
            }
        ])
        return await auditor.run_audit(cases)

    results = asyncio.run(run())
    assert len(results) == 1
    assert results[0].variant_scores
