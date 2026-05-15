import sqlite3
import json
import os

def initialize_db():
    current_dir = os.path.dirname(os.path.abspath(__file__))  
    project_root = os.path.dirname(current_dir)               
    db_path = os.path.join(project_root, 'data', 'mowafak.db') 

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 3. Candidates Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS candidates (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE,
            raw_cv_text TEXT,
            parsed_cv_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 4. Interviews Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS interviews (
            id TEXT PRIMARY KEY,
            candidate_id TEXT,
            overall_score REAL,
            ai_recommendation TEXT,
            hr_decision TEXT DEFAULT 'Pending',
            hr_notes TEXT,
            final_report_path TEXT,
            FOREIGN KEY (candidate_id) REFERENCES candidates (id)
        )
    ''')

    # 5. Questions & Responses Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS interview_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            interview_id TEXT,
            question_text TEXT NOT NULL,
            audio_path TEXT,
            transcript TEXT,
            evaluation_score INTEGER,
            evaluation_evidence TEXT,
            FOREIGN KEY (interview_id) REFERENCES interviews (id)
        )
    ''')

    # 6. Audit Log Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            candidate_id TEXT,
            ai_recommendation TEXT,
            hr_decision TEXT,
            hr_notes_hash TEXT,
            FOREIGN KEY (candidate_id) REFERENCES candidates (id)
        )
    ''')

    conn.commit()
    conn.close()
    print(f"✅ Database initialized successfully at: {db_path}")

if __name__ == "__main__":
    initialize_db()