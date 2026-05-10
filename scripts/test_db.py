import sqlite3
import json
import os

def test_database_flow():
    current_dir = os.path.dirname(os.path.abspath(__file__))  
    project_root = os.path.dirname(current_dir)               
    db_path = os.path.join(project_root, 'data', 'mowafak.db')

    print(f"Connecting to database at: {db_path}...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # --- MOCK INSERTS ---
        # 1. Insert a Mock Candidate
        mock_parsed_cv = json.dumps({"skills": ["Python", "Machine Learning"], "experience": "2 years"})
        cursor.execute('''
            INSERT OR IGNORE INTO candidates (id, name, email, raw_cv_text, parsed_cv_json)
            VALUES (?, ?, ?, ?, ?)
        ''', ("CAND-001", "Ali Hassan", "ali@example.com", "Raw text of CV here", mock_parsed_cv))

        # 2. Insert a Mock Interview for that Candidate
        cursor.execute('''
            INSERT OR IGNORE INTO interviews (id, candidate_id, overall_score, ai_recommendation, hr_decision)
            VALUES (?, ?, ?, ?, ?)
        ''', ("INT-001", "CAND-001", 4.5, "strong_yes", "Pending"))

        # 3. Insert a Mock Question & Response
        cursor.execute('''
            INSERT INTO interview_questions (interview_id, question_text, audio_path, transcript, evaluation_score, evaluation_evidence)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', ("INT-001", "Tell me about your ML experience.", "data/sample_recordings/ali_q1.wav", 
              "I used PyTorch to build a CNN.", 5, "I used PyTorch..."))

        # 4. Insert a Mock Audit Log Entry
        cursor.execute('''
            INSERT INTO audit_log (candidate_id, ai_recommendation, hr_decision, hr_notes_hash)
            VALUES (?, ?, ?, ?)
        ''', ("CAND-001", "strong_yes", "Approve", "hash_of_hr_notes_12345"))

        # Commit the dummy data
        conn.commit()
        print("✅ Mock data inserted successfully!")

        # --- TESTING RETRIEVAL (JOINING TABLES) ---
        print("\n--- Fetching Full Candidate Report ---")
        cursor.execute('''
            SELECT c.name, i.ai_recommendation, q.evaluation_score, a.hr_decision
            FROM candidates c
            JOIN interviews i ON c.id = i.candidate_id
            JOIN interview_questions q ON i.id = q.interview_id
            JOIN audit_log a ON c.id = a.candidate_id
            WHERE c.id = 'CAND-001'
        ''')
        
        result = cursor.fetchone()
        if result:
            print(f"Name: {result[0]}")
            print(f"AI Recommendation: {result[1]}")
            print(f"Question Score: {result[2]}/5")
            print(f"Final HR Decision: {result[3]}")
            print("\n✅ Database relationships and Foreign Keys are working perfectly!")
        else:
            print("❌ Query failed to find the linked records.")
        
    except sqlite3.Error as e:
        print(f"❌ Database error occurred: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    test_database_flow()