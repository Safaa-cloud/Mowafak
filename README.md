# Mowafak (مُوَفَّق) — Async AI Interview Pre-Screen

![Project Status](https://img.shields.io/badge/Status-Active-success)
![Tech Stack](https://img.shields.io/badge/Tech_Stack-FastAPI%20%7C%20LangGraph%20%7C%20Whisper%20%7C%20Chainlit-blue)
![Compliance](https://img.shields.io/badge/Compliance-Responsible_AI_%7C_EU_AI_Act_Aligned-purple)

**Mowafak** is an asynchronous voice-based AI interview pre-screening tool designed to assist HR teams while strictly adhering to Responsible AI principles. Built as a Graduation Project, this system utilizes a multi-agent LLM architecture to process applicant CVs, conduct voice interviews, and draft evaluation reports. 

**Crucially, Mowafak enforces a strict "Human-in-the-Loop" (HiL) policy: the system makes auto-rejection impossible by design.** Every AI recommendation must be reviewed and approved by a human HR professional.

## 🚀 Project Demo
src="https://github.com/Safaa-cloud/Mowafak/blob/main/Mowafak_Project_demo.mp4" 
---

## 🌟 Key Features

* **CV Parsing & Dynamic Questioning:** Extracts applicant skills via PDF parsing and generates tailored interview questions using a LangGraph multi-agent system.
* **Async Voice Interviews:** Candidates record their answers via a browser-based audio interface. Audio is transcribed locally using OpenAI's Whisper (Batch STT).
* **Multi-Agent Evaluation:** Uses Google Gemini to score responses based on relevance, clarity, and technical depth, always citing evidence directly from the transcript.
* **Mandatory Human-in-the-Loop (HiL):** An HR dashboard built in Chainlit ensures no automated rejections are ever sent to candidates.
* **Append-Only Audit Logging:** Every HR decision is cryptographically logged for compliance and accountability.
* **Automated Bias Auditing:** Integrated DeepEval test suites ensure the AI evaluator does not show variance based on candidate demographics (Name/Gender swaps).

---

## 🏗️ System Architecture

1. **Frontend (Candidate):** Static HTML/JS utilizing the browser `MediaRecorder` API.
2. **Frontend (HR):** Interactive dashboard powered by Chainlit.
3. **Backend Engine:** FastAPI handling routing, audio uploads, and SQLite database management.
4. **AI Pipeline:** LangGraph orchestrating three primary agents:
   * *Question Generator Agent*
   * *Response Evaluator Agent*
   * *Report Drafter Agent*

---

## ⚙️ Setup & Installation

**Prerequisites:**
* Python 3.10+
* A free Google AI Studio API Key (Gemini)

**1. Clone the repository:**
```bash
git clone [https://github.com/Safaa-cloud/Mowafak.git](https://github.com/Safaa-cloud/Mowafak.git)
cd Mowafak
```

**2. Create a virtual environment and install dependencies:**
```bash
python -m venv venv
# On Windows: venv\Scripts\activate
# On Mac/Linux: source venv/bin/activate

pip install -r requirements.txt
```

**3. Configure Environment Variables:**
Create a `.env` file in the root directory and add your API key:
```env
GEMINI_API_KEY="your_google_ai_studio_key_here"
```

---

## 🚀 Running the Project

Because Mowafak is decoupled, you need to run the Backend and the HR UI simultaneously.

**Start the FastAPI Backend:**
```bash
uvicorn backend.main:app --reload --port 8001
# Runs on http://localhost:8001
```

**Start the Chainlit HR UI:**
```bash
chainlit run app.py -w --port 8000
# Runs on http://localhost:8000 (Chainlit port)
```

**Launch the Candidate App:**
Open `candidate_app/index.html` in a modern browser, upload a PDF CV, accept consent, then continue to the generated `record.html?session_id=...` interview link.

---

## 🛡️ Responsible AI & Compliance

Mowafak is built to align with the NYC AEDT and EU AI Act guidelines for high-risk employment tools. 
* **Bias Audit:** Run `python -m responsible_ai.bias_audit` to test the evaluator agent for demographic bias. Results are saved to `outputs/eval_report.json`.
* **DeepEval Tests:** Run `pytest tests/test_evaluator.py` to assert Faithfulness (all AI claims must have transcript evidence) and HiLRespect.
* **Audit Log:** Located at `responsible_ai/audit_log.jsonl`.

---

## 👥 The Team

* **MALAK HISHAM** - AI Agent Architect
* **ROAA** - Responsible AI & Eval Specialist
* **NOURAN** - Voice & Data Engineer
* **MALAK IBRAHIM** - Backend Developer
* **MENNA** - Frontend UI Developer
* **SAFAA** - Compliance & Integration Lead
