import chainlit as cl
import sqlite3
import os
import json
import csv
from datetime import datetime

# ==========================================
# Database & Utility Functions
# ==========================================

def get_db_connection():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(current_dir, 'data', 'mowafak.db')
    return sqlite3.connect(db_path)

async def process_decision(cand_id, decision, hr_notes="None"):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('UPDATE interviews SET hr_decision = ?, hr_notes = ? WHERE candidate_id = ?', (decision, hr_notes, cand_id))
    cursor.execute('SELECT ai_recommendation FROM interviews WHERE candidate_id = ?', (cand_id,))
    ai_rec_row = cursor.fetchone()
    ai_rec = ai_rec_row[0] if ai_rec_row else "N/A"

    cursor.execute('''
        INSERT INTO audit_log (candidate_id, ai_recommendation, hr_decision, hr_notes_hash)
        VALUES (?, ?, ?, ?)
    ''', (cand_id, ai_rec, decision, hr_notes))

    conn.commit()
    conn.close()

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "candidate_id": cand_id,
        "ai_recommendation": ai_rec,
        "hr_decision": decision,
        "hr_notes": hr_notes,
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

# ==========================================
# UI & Chainlit Logic
# ==========================================

@cl.on_chat_start
async def start():
    await cl.Message(content="👋 **Mowafak HR Gateway Active.** Type `/export` anytime to download the Audit Log CSV.").send()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT c.id, c.name, i.ai_recommendation, q.evaluation_score, q.question_text, q.transcript, q.evaluation_evidence
        FROM candidates c
        JOIN interviews i ON c.id = i.candidate_id
        LEFT JOIN interview_questions q ON i.id = q.interview_id
        WHERE i.hr_decision = 'Pending'
        LIMIT 1
    ''')
    row = cursor.fetchone()
    conn.close()

    if not row:
        await cl.Message(content="📭 No candidates pending review. All applications processed.").send()
        return

    cand_id, name, ai_rec, score, question, transcript, evidence = row
    report_content = f"""## 📊 Candidate Assessment Panel
        
| 👤 Profile Details | 📈 Assessment Results |
| :--- | :--- |
| **Name:** {name} <br> **ID:** `{cand_id}` | **Score:** ⭐ {score}/5 <br> **AI Rec:** {format_ai_badge(ai_rec)} |

---
### 🎙️ Interview Transcript & Evidence
**Question:** *"{question if question else 'N/A'}"*

**Candidate Response:** > "{transcript if transcript else 'No audio transcript found.'}"

**AI Evidence for Score:** > "*{evidence if evidence else 'No specific evidence quoted by AI.'}*"

---
> 🛡️ **Final HR Approval (HiL Gate):** *The AI screening is complete. Awaiting final human confirmation to finalize the status.*
"""

    actions = [
        cl.Action(name="approve", payload={"value": cand_id, "status": "Approved"}, label="✅ Approve"),
        cl.Action(name="hold", payload={"value": cand_id, "status": "Hold"}, label="⏳ Hold"),
        cl.Action(name="reject", payload={"value": cand_id, "status": "Rejected"}, label="❌ Reject with Feedback"),
    ]

    msg = cl.Message(content=report_content, actions=actions)
    await msg.send()
    cl.user_session.set("report_msg", msg)

@cl.on_message
async def handle_commands(message: cl.Message):
    if message.content.strip().lower() == "/export":
        log_file = "responsible_ai/audit_log.jsonl"
        csv_file = "responsible_ai/audit_export.csv"
        
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding="utf-8") as f_in, open(csv_file, 'w', newline='', encoding="utf-8") as f_out:
                writer = None
                for line in f_in:
                    data = json.loads(line)
                    if not writer:
                        writer = csv.DictWriter(f_out, fieldnames=data.keys())
                        writer.writeheader()
                    writer.writerow(data)
            
            await cl.Message(content="📊 Audit Log exported successfully:").send()
            await cl.File(path=csv_file, name="audit_log_export.csv").send()
        else:
            await cl.Message(content="❌ No audit logs found to export.").send()

# ==========================================
# Action Handlers
# ==========================================

@cl.action_callback("approve")
async def on_approve(action: cl.Action):
    await finalize_decision(action, "Approved", "Meets all criteria.")

@cl.action_callback("hold")
async def on_hold(action: cl.Action):
    await finalize_decision(action, "Hold", "Pending further team discussion.")

@cl.action_callback("reject")
async def on_reject(action: cl.Action):
    res = await cl.AskUserMessage(content=f"Please provide specific feedback for candidate `{action.payload['value']}` rejection:", timeout=120).send()
    feedback = res['output'] if res else "No specific feedback provided."
    await finalize_decision(action, "Rejected", feedback)

async def finalize_decision(action, status, notes):
    cand_id = action.payload["value"]
    
    await process_decision(cand_id, status, notes)
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