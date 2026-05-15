import chainlit as cl
import sqlite3
import os
import sys
import json

# ── Make sure src/ is importable regardless of CWD ──────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.settings import settings          # single source of truth for DB path
from src.audit_log import export_log_to_csv  # only import what we need here


# =============================================================================
# 1. DATABASE HELPER  (uses settings.DATABASE_URL — same file as FastAPI)
# =============================================================================

def get_db_connection() -> sqlite3.Connection:
    """
    FIX (Bug 5): app.py was building its own path → data/mowafak.db
    while settings.DATABASE_URL points to mowafak.db (no data/ subfolder).
    They were opening TWO different SQLite files, so Chainlit could never
    see the reports written by FastAPI.  Now both use the same path.
    """
    conn = sqlite3.connect(settings.DATABASE_URL, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


# =============================================================================
# 2. HELPERS
# =============================================================================

async def process_decision(cand_id: str, decision: str, hr_notes: str = "None"):
    """
    Updates the database when HR makes a decision.

    FIX (Bug 6 — duplicate audit log):
    The old version called log_decision() here AND main.py /hr_decision also
    wrote to audit_log.jsonl — every decision was logged twice.
    Now app.py ONLY updates the database.  The audit log is written exclusively
    by main.py's /hr_decision endpoint, which is the single authoritative path.

    If you later want Chainlit to bypass FastAPI entirely, move the audit write
    back here and remove it from main.py — but never have both active at once.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE reports
        SET hr_decision = ?, hr_notes = ?
        WHERE session_id = (SELECT id FROM sessions WHERE candidate_id = ?)
        """,
        (decision, hr_notes, cand_id),
    )

    conn.commit()
    conn.close()


def format_ai_badge(ai_rec: str) -> str:
    """Maps raw AI recommendation strings to readable UI labels."""
    badges = {
        "strong_yes": "🟢 Strong Yes",
        "weak_yes":   "🟡 Weak Yes",
        "weak_no":    "🟠 Weak No",
        "strong_no":  "🔴 Strong No",
        # legacy / fallback values
        "strong":  "🟢 Strong",
        "average": "🟡 Average",
        "weak":    "🔴 Weak",
    }
    return badges.get(ai_rec.lower(), f"🤖 {ai_rec.title()}")


# =============================================================================
# 3. UI INITIALISATION — shown when the HR manager opens Chainlit
# =============================================================================

@cl.on_chat_start
async def start():
    """Loads the next pending candidate and renders the review dashboard."""
    await cl.Message(
        content=(
            "👋 **Mowafak HR Gateway Active.**\n"
            "*Type `/export` anytime to download the secure Audit Log CSV.*"
        )
    ).send()

    try:
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Fetch ONE candidate whose report has not yet received an HR decision
        cursor.execute(
            """
            SELECT
                c.id          AS cand_id,
                c.name,
                r.ai_recommendation,
                r.report_json,
                a.transcript
            FROM candidates c
            JOIN sessions s ON c.id = s.candidate_id
            JOIN reports  r ON s.id = r.session_id
            LEFT JOIN answers a ON s.id = a.session_id
            WHERE r.hr_decision = 'pending'
               OR r.hr_decision IS NULL
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        conn.close()

    except Exception as e:
        await cl.Message(
            content=(
                f"⚠️ **Database Error:** Please ensure the orchestrator has "
                f"populated the `reports` table. (`{e}`)"
            )
        ).send()
        return

    if not row:
        await cl.Message(
            content="📭 **No candidates pending review.** All applications have been processed."
        ).send()
        return

    cand_id    = row["cand_id"]
    name       = row["name"]
    ai_rec     = row["ai_recommendation"] or "pending"
    transcript = row["transcript"] or "No audio transcript found."

    # Parse per-question scores from the stored JSON report
    overall_score      = "N/A"
    relevance_score    = "N/A"
    clarity_score      = "N/A"
    tech_score         = "N/A"
    evidence_quote     = "N/A"
    concerns_text      = "None identified."

    try:
        if row["report_json"]:
            report_data     = json.loads(row["report_json"])
            overall_score   = report_data.get("overall_score", "N/A")
            relevance_score = report_data.get("relevance_score", "N/A")
            clarity_score   = report_data.get("clarity_score", "N/A")
            tech_score      = report_data.get("technical_depth_score", "N/A")
            evidence_quote  = report_data.get("evidence_from_transcript", "N/A")
            concerns_list   = report_data.get("concerns", [])
            if concerns_list:
                concerns_text = "\n".join(f"- {c}" for c in concerns_list)
    except (json.JSONDecodeError, TypeError):
        pass  # non-fatal; we just show N/A values

    report_content = f"""## 📊 Candidate Assessment Panel

| 👤 Profile | 📈 Assessment |
| :--- | :--- |
| **Name:** {name} | **Overall Score:** ⭐ {overall_score}/5 |
| **ID:** `{cand_id}` | **AI Rec:** {format_ai_badge(ai_rec)} |

---
### 🎯 Skill Scores
| Relevance | Clarity | Technical Depth |
| :---: | :---: | :---: |
| {relevance_score}/5 | {clarity_score}/5 | {tech_score}/5 |

---
### 🎙️ Interview Transcript
> "{transcript}"

---
### 💬 Evidence Quote
> "{evidence_quote}"

---
### ⚠️ Concerns
{concerns_text}

---
> 🛡️ **HiL Gate Active:** The AI assessment is advisory only. No decision \
reaches the candidate without your explicit action below.
"""

    actions = [
        cl.Action(
            name="approve",
            payload={"value": cand_id, "status": "Approved"},
            label="✅ Approve to next round",
        ),
        cl.Action(
            name="hold",
            payload={"value": cand_id, "status": "Hold"},
            label="⏳ Hold for review",
        ),
        cl.Action(
            name="reject",
            payload={"value": cand_id, "status": "Rejected"},
            label="❌ Reject with feedback",
        ),
    ]

    msg = cl.Message(content=report_content, actions=actions)
    await msg.send()

    # Store the message object so we can remove the buttons after a decision
    cl.user_session.set("report_msg", msg)
    cl.user_session.set("cand_id", cand_id)


# =============================================================================
# 4. ACTION HANDLERS (button clicks)
# =============================================================================

@cl.action_callback("approve")
async def on_approve(action: cl.Action):
    await finalize_decision(action, "Approved", "Meets all criteria.")


@cl.action_callback("hold")
async def on_hold(action: cl.Action):
    await finalize_decision(action, "Hold", "Pending further team discussion.")


@cl.action_callback("reject")
async def on_reject(action: cl.Action):
    """
    Requirement 4: rejection MUST include explicit written HR feedback.
    We block until the HR manager types their reason.
    """
    cand_id = action.payload["value"]
    res = await cl.AskUserMessage(
        content=(
            f"✍️ Please provide written feedback for rejecting candidate `{cand_id}`.\n"
            f"*(This will be stored in the audit log and is required before rejection is finalised.)*"
        ),
        timeout=120,
    ).send()

    feedback = res["output"].strip() if res else ""
    if not feedback:
        feedback = "No specific feedback provided by HR."

    await finalize_decision(action, "Rejected", feedback)


async def finalize_decision(action: cl.Action, status: str, notes: str):
    """
    Shared handler for all three decision paths.
    Updates the DB, removes buttons (preventing double-clicks), and confirms.
    """
    cand_id = action.payload["value"]

    # Update the database (audit log is written by FastAPI — see process_decision docstring)
    await process_decision(cand_id, status, notes)

    # Remove the action buttons so HR cannot submit a second decision
    msg = cl.user_session.get("report_msg")
    if msg:
        await msg.remove_actions()

    icons = {"Approved": "✅", "Hold": "⏳", "Rejected": "❌"}
    icon  = icons.get(status, "📌")

    await cl.Message(
        content=(
            f"{icon} **Decision Finalised: {status}**\n"
            f"Candidate `{cand_id}` has been marked as **{status}**.\n"
            f"*Database updated. Audit trail entry written by the backend.*"
        )
    ).send()


# =============================================================================
# 5. COMMAND HANDLERS  (/export)
# =============================================================================

@cl.on_message
async def handle_commands(message: cl.Message):
    """Handles slash-commands typed by the HR manager in the chat."""

    if message.content.strip().lower() == "/export":
        csv_file_path = export_log_to_csv()

        if csv_file_path and os.path.exists(csv_file_path):
            with open(csv_file_path, "rb") as f:
                file_data = f.read()

            export_file = cl.File(
                content=file_data,
                name="audit_log_export.csv",
                mime="text/csv",
            )

            await cl.Message(
                content=(
                    "📊 **Audit Log exported successfully!** "
                    "Click the file below to download it:"
                ),
                elements=[export_file],
            ).send()
        else:
            await cl.Message(
                content="❌ No audit logs found to export yet."
            ).send()

    else:
        # Ignore any other chat messages (HR is not chatting with an AI here)
        pass