import sqlite3
import os
import logging

# Configure logging for security and audit trailing
logging.basicConfig(level=logging.INFO, format='%(asctime)s - HiL GATE - %(levelname)s - %(message)s')

def get_db_connection() -> sqlite3.Connection:
    """Establish a secure connection to the central SQLite database."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    db_path = os.path.join(project_root, 'data', 'mowafak.db')
    
    return sqlite3.connect(db_path)

def verify_hil_clearance(candidate_id: str) -> bool:
    """
    Security Lock: Verifies if the HR decision has been finalized.
    Returns True ONLY if HR has explicitly marked the status as 'Approved' or 'Rejected'.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # FIXED: Joined 'reports' and 'sessions' to find the HR decision by candidate_id
        cursor.execute('''
            SELECT r.hr_decision 
            FROM reports r
            JOIN sessions s ON r.session_id = s.id
            WHERE s.candidate_id = ?
        ''', (candidate_id,))
        
        row = cursor.fetchone()
        conn.close()

        if not row:
            logging.error(f"Blocked: No report records found for candidate '{candidate_id}'.")
            return False
        
        decision = row[0]
        if decision in ["approve", "reject", "Approved", "Rejected"]: # Adjusted to match both backend/UI formats
            logging.info(f"Cleared: Candidate '{candidate_id}' has an explicit HR decision: {decision}.")
            return True
        else:
            logging.warning(f"Blocked: Candidate '{candidate_id}' status is '{decision}'. Awaiting explicit HR action.")
            return False
            
    except Exception as e:
        logging.error(f"Database error during HiL clearance check: {e}")
        return False

def get_final_feedback(candidate_id: str) -> dict:
    """
    Retrieves the final result to be sent to the candidate.
    Strictly enforces the Human-in-the-Loop requirement by raising an error if unapproved.
    """
    # Strict enforcement: Absolute prevention of Auto-Reject or Auto-Approve
    if not verify_hil_clearance(candidate_id):
        raise PermissionError(
            f"🚨 HiL Gate Violation: Cannot release AI recommendations for '{candidate_id}' without explicit HR approval."
        )
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # FIXED: Querying the reports table via the session link
    cursor.execute('''
        SELECT r.hr_decision, r.hr_notes 
        FROM reports r
        JOIN sessions s ON r.session_id = s.id
        WHERE s.candidate_id = ?
    ''', (candidate_id,))
    
    row = cursor.fetchone()
    conn.close()

    return {
        "candidate_id": candidate_id,
        "final_status": row[0],
        "hr_feedback": row[1] if row[1] else "No specific feedback provided by HR."
    }