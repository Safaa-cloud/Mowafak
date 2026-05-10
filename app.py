import chainlit as cl
import sqlite3
import os
import json
from datetime import datetime


def get_db_connection():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(current_dir, 'data', 'mowafak.db')
    return sqlite3.connect(db_path)


def record_decision(cand_id, decision):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('UPDATE interviews SET hr_decision = ? WHERE candidate_id = ?', (decision, cand_id))

    cursor.execute('SELECT ai_recommendation FROM interviews WHERE candidate_id = ?', (cand_id,))
    ai_rec = cursor.fetchone()[0]

    cursor.execute('''
        INSERT INTO audit_log (candidate_id, ai_recommendation, hr_decision)
        VALUES (?, ?, ?)
    ''', (cand_id, ai_rec, decision))

    conn.commit()
    conn.close()

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "candidate_id": cand_id,
        "ai_recommendation": ai_rec,
        "hr_decision": decision,
        "verified_by": "HR_Manager_Mariam"
    }

    os.makedirs("responsible_ai", exist_ok=True)
    with open("responsible_ai/audit_log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")


def format_ai_badge(ai_rec: str) -> str:
    badges = {
        "strong_yes": "🟢 Strong Yes",
        "yes": "🟡 Yes",
        "no": "🟠 No",
        "strong_no": "🔴 Strong No",
    }
    return badges.get(ai_rec, f"🤖 {ai_rec.replace('_', ' ').title()}")


@cl.on_chat_start
async def start():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT c.id, c.name, i.ai_recommendation, q.evaluation_score
        FROM candidates c
        JOIN interviews i ON c.id = i.candidate_id
        JOIN interview_questions q ON i.id = q.interview_id
        LIMIT 1
    ''')
    row = cursor.fetchone()
    conn.close()

    if not row:
        await cl.Message(content="📭 No candidates pending review.").send()
        return

    cand_id, name, ai_rec, score = row

    report_content = f"""## 📊 Candidate Assessment Panel
        
| 👤 Profile Details | 📈 Assessment Results |
| :--- | :--- |
| **Name:** {name} 🔹 **ID:** `{cand_id}` | **Score:** ⭐ {score}/5 🔹 **AI Rec:** {format_ai_badge(ai_rec)} |

> 🛡️ **Final HR Approval (HiL Gate):** *The AI screening is complete. Awaiting final human confirmation to finalize the status.*
"""

    actions = [
        cl.Action(name="decision_btn", payload={"value": cand_id, "status": "Approved"}, label="✅ Approve"),
        cl.Action(name="decision_btn", payload={"value": cand_id, "status": "Hold"}, label="⏳ Hold"),
        cl.Action(name="decision_btn", payload={"value": cand_id, "status": "Rejected"}, label="❌ Reject"),
    ]

    msg = cl.Message(content=report_content, actions=actions)
    await msg.send()
    cl.user_session.set("report_msg", msg)


@cl.action_callback("decision_btn")
async def on_decision(action: cl.Action):
    cand_id = action.payload["value"]
    status = action.payload["status"]

    record_decision(cand_id, status)

    msg = cl.user_session.get("report_msg")
    if msg:
        await msg.remove_actions()

    status_icons = {"Approved": "✅", "Hold": "⏳", "Rejected": "❌"}
    icon = status_icons.get(status, "📌")

    await cl.Message(
        content=(
            f"{icon} **Decision Finalized: {status}** \n"
            f"Candidate `{cand_id}` has been marked as **{status}**.  \n"
            f"*All records successfully updated in the Database and Audit Log.*"
        )
    ).send()