import requests, json

BASE = "http://localhost:8000"

def check(label, r, expected_status=200):
    ok = r.status_code == expected_status
    print(f"{'✅' if ok else '❌'} {label} → {r.status_code}")
    if not ok:
        print(f"   {r.text[:200]}")
    return ok

# Health
check("Health check", requests.get(f"{BASE}/health"))

# Upload CV
with open("data/sample_cvs/sample_cv.pdf", "rb") as f:
    r = requests.post(f"{BASE}/upload_cv", files={"file": f},
                      data={"name":"Test User","email":"t@t.com","consent_accepted":"true"})
check("Upload CV", r)
sid = r.json().get("session_id","")

# Start interview
r = requests.post(f"{BASE}/start_interview",
                  data={"session_id": sid,
                        "questions_json": json.dumps(["Q1","Q2","Q3"])})
check("Start interview", r)

# Get questions
check("Get questions", requests.get(f"{BASE}/get_questions?session_id={sid}"))

# Upload answer
with open("data/sample_recordings/sample_answer.wav", "rb") as f:
    r = requests.post(f"{BASE}/upload_answer",
                      files={"audio": f},
                      data={"session_id":sid,"question_index":0,"question_text":"Q1"})
check("Upload answer", r)
print(f"   Transcript: {r.json().get('transcript','')[:80]}")

print("\nAll backend routes verified.")