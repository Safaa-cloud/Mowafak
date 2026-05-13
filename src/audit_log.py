import os
import json
import csv
from datetime import datetime
import logging

# Configure logging for audit system operations
logging.basicConfig(level=logging.INFO, format='%(asctime)s - AUDIT - %(message)s')

def get_log_paths() -> tuple:
    """
    Determines and returns the absolute paths for the audit log files.
    Ensures the 'responsible_ai' directory exists at the project root.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    rai_dir = os.path.join(project_root, 'responsible_ai')
    
    # Create the directory if it does not exist
    os.makedirs(rai_dir, exist_ok=True)
    
    jsonl_path = os.path.join(rai_dir, 'audit_log.jsonl')
    csv_path = os.path.join(rai_dir, 'audit_export.csv')
    
    return jsonl_path, csv_path

def log_decision(candidate_id: str, ai_recommendation: str, hr_decision: str, hr_notes: str, hr_user_id: str = "HR_Manager_Mariam"):
    """
    Records an HR decision into a JSON Lines (.jsonl) file.
    This acts as an append-only ledger for compliance with Responsible AI standards.
    """
    jsonl_path, _ = get_log_paths()
    
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "candidate_id": candidate_id,
        "ai_recommendation": ai_recommendation,
        "hr_decision": hr_decision,
        "hr_notes": hr_notes,
        "hr_user_id": hr_user_id
    }

    try:
        # 'a' mode ensures we only append, preventing accidental overwriting of past audits
        with open(jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
        logging.info(f"Audit log securely recorded for candidate '{candidate_id}'.")
    except Exception as e:
        logging.error(f"Critical System Error - Failed to write to audit log: {e}")

def export_log_to_csv() -> str:
    """
    Converts the append-only JSONL audit log into a readable CSV format for HR export.
    Uses a robust two-pass approach to handle evolving data schemas.
    """
    jsonl_path, csv_path = get_log_paths()
    
    if not os.path.exists(jsonl_path):
        logging.warning("Export requested, but no audit log file exists yet.")
        return None

    try:
        # Pass 1: Gather all unique headers across all log entries
        all_headers = set()
        with open(jsonl_path, 'r', encoding="utf-8") as f_in:
            for line in f_in:
                data = json.loads(line)
                all_headers.update(data.keys())
        
        # Sort headers to ensure consistent column order
        headers = list(all_headers)
        if "timestamp" in headers: headers.insert(0, headers.pop(headers.index("timestamp")))
        if "candidate_id" in headers: headers.insert(1, headers.pop(headers.index("candidate_id")))

        # Pass 2: Write the CSV with all discovered headers
        with open(jsonl_path, 'r', encoding="utf-8") as f_in, open(csv_path, 'w', newline='', encoding="utf-8") as f_out:
            writer = csv.DictWriter(f_out, fieldnames=headers)
            writer.writeheader()
            
            for line in f_in:
                data = json.loads(line)
                writer.writerow(data)
                
        logging.info("Audit log successfully exported to CSV.")
        return csv_path
    except Exception as e:
        logging.error(f"Failed to export CSV: {e}")
        return None