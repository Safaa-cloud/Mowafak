import chainlit as cl
import sqlite3
import os
import json
from src.audit_log import log_decision, export_log_to_csv

# ==========================================
# 1. Database & Utility Functions
# ==========================================

def get_db_connection() -> sqlite3.Connection:
    """Establish connection to the central database."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(current_dir, 'data', 'mowafak.db')
    
    # Ensure data directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return sqlite3.connect(db_path)

async def process_decision(cand_id: str, decision: str, hr_notes: str = "None"):
    """Handles the backend updates when HR makes a decision."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Update Database (Clearing the HiL Gate using the correct reports/sessions schema)
    cursor.execute('''
        UPDATE reports 
        SET hr_decision = ?, hr_notes = ? 
        WHERE session_id = (SELECT id FROM sessions WHERE candidate_id = ?)
    ''', (decision, hr_notes, cand_id))
    
    # 2. Fetch AI Recommendation to complete the Audit Log
    cursor.execute('''
        SELECT ai_recommendation 
        FROM reports 
        WHERE session_id = (SELECT id FROM sessions WHERE candidate_id = ?)
    ''', (cand_id,))
    
    ai_rec_row = cursor.fetchone()
    ai_rec = ai_rec_row[0] if ai_rec_row else "N/A"

    conn.commit()
    conn.close()

    # 3. Save to JSONL using your secure Audit Log module
    log_decision(cand_id, ai_rec, decision, hr_notes)

def format_ai_badge(ai_rec: str) -> str:
    """Helper to make the UI look professional."""
    badges = {
        "strong": "🟢 Strong",
        "average": "🟡 Average",
        "weak": "🔴 Weak",
    }
    return badges.get(ai_rec.lower(), f"🤖 {ai_rec.title()}")

# ==========================================
# 2. UI Initialization & Dashboard
# ==========================================

@cl.on_chat_start
async def start():
    """Initializes the HR Dashboard when the browser loads."""
    await cl.Message(content="👋 **Mowafak HR Gateway Active.** \n*Type `/export` anytime to download the secure Audit Log CSV.*").send()

    try:
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row # Allows us to access columns by name
        cursor = conn.cursor()
        
        # Fetch ONE pending candidate to review using the correct schema
        cursor.execute('''
            SELECT c.id as cand_id, c.name, r.ai_recommendation, r.report_json, a.transcript
            FROM candidates c
            JOIN sessions s ON c.id = s.candidate_id
            JOIN reports r ON s.id = r.session_id
            LEFT JOIN answers a ON s.id = a.session_id
            WHERE r.hr_decision = 'pending' OR r.hr_decision IS NULL
            LIMIT 1
        ''')
        row = cursor.fetchone()
        conn.close()

        if not row:
            await cl.Message(content="📭 **No candidates pending review.** All applications have been processed.").send()
            return

        cand_id = row['cand_id']
        name = row['name']
        ai_rec = row['ai_recommendation']
        transcript = row['transcript']
        
        # Safely parse the report JSON to get the score
        score = "N/A"
        try:
            if row['report_json']:
                report_data = json.loads(row['report_json'])
                score = report_data.get("overall_score", "N/A")
        except:
            pass

        # Build the Markdown Report for the UI
        report_content = f"""## 📊 Candidate Assessment Panel
            
| 👤 Profile Details | 📈 Assessment Results |
| :--- | :--- |
| **Name:** {name} <br> **ID:** `{cand_id}` | **Overall Score:** ⭐ {score}/5 <br> **AI Rec:** {format_ai_badge(ai_rec if ai_rec else 'pending')} |

---
### 🎙️ Latest Interview Transcript
**Candidate Response:** > "{transcript if transcript else 'No audio transcript found.'}"

---
> 🛡️ **Final HR Approval (HiL Gate):** *The AI screening is complete. Awaiting final human confirmation to finalize the status. No candidate is rejected automatically.*
"""

        # Interactive Buttons for the HR Manager
        actions = [
            cl.Action(name="approve", payload={"value": cand_id, "status": "Approved"}, label="✅ Approve"),
            cl.Action(name="hold", payload={"value": cand_id, "status": "Hold"}, label="⏳ Hold"),
            cl.Action(name="reject", payload={"value": cand_id, "status": "Rejected"}, label="❌ Reject with Feedback"),
        ]

        msg = cl.Message(content=report_content, actions=actions)
        await msg.send()
        
        # Store the message in session to remove buttons later
        cl.user_session.set("report_msg", msg)

    except Exception as e:
        await cl.Message(content=f"⚠️ Database Error: Please ensure the orchestrator has populated the `reports` table. ({e})").send()

# ==========================================
# 3. Action Handlers (Button Clicks)
# ==========================================

@cl.action_callback("approve")
async def on_approve(action: cl.Action):
    await finalize_decision(action, "Approved", "Meets all criteria.")

@cl.action_callback("hold")
async def on_hold(action: cl.Action):
    await finalize_decision(action, "Hold", "Pending further team discussion.")

@cl.action_callback("reject")
async def on_reject(action: cl.Action):
    # Requirement: Ask for explicit feedback if rejected
    res = await cl.AskUserMessage(content=f"Please provide specific feedback for candidate `{action.payload['value']}` rejection:", timeout=120).send()
    feedback = res['output'] if res else "No specific feedback provided."
    await finalize_decision(action, "Rejected", feedback)

async def finalize_decision(action: cl.Action, status: str, notes: str):
    cand_id = action.payload["value"]
    
    # Process backend updates
    await process_decision(cand_id, status, notes)

    # Remove buttons so HR can't click twice
    msg = cl.user_session.get("report_msg")
    if msg:
        await msg.remove_actions()

    status_icons = {"Approved": "✅", "Hold": "⏳", "Rejected": "❌"}
    icon = status_icons.get(status, "📌")

    await cl.Message(
        content=(
            f"{icon} **Decision Finalized: {status}** \n"
            f"Candidate `{cand_id}` has been marked as **{status}**.  \n"
            f"*All records successfully updated in the Database and securely logged in the Audit Trail.*"
        )
    ).send()

# ==========================================
# 4. Command Handlers (e.g., /export)
# ==========================================

@cl.on_message
async def handle_commands(message: cl.Message):
    if message.content.strip().lower() == "/export":
        csv_file_path = export_log_to_csv()
        
        if csv_file_path and os.path.exists(csv_file_path):
            # FIXED: Read file into memory as bytes to avoid Chainlit absolute path UI bugs
            with open(csv_file_path, "rb") as f:
                file_data = f.read()
                
            export_file = cl.File(
                content=file_data, 
                name="audit_log_export.csv", 
                mime="text/csv"
            )
            
            await cl.Message(
                content="📊 **Audit Log exported successfully!** Click the file below to download it:", 
                elements=[export_file]
            ).send()
        else:
            await cl.Message(content="❌ No audit logs found to export.").send()