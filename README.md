# Resume Analyser (Google Stack)

This app analyzes a CV against a job description, generates dynamic key skill categories, highlights gaps, and provides recruiter-style suggestions using **Gemini** or **local Ollama**.

## Stack
- Flask + Tailwind (templates)
- Gemini API (free tier) or local Ollama
- Firebase Auth (Google Sign-In, optional in local mode)
- Firestore (optional)
- PDF/DOCX parsing with pdfplumber + python‑docx

## Setup

### 1) Install deps
```bash
pip install -r requirements.txt
```

### 2) LLM provider

#### Option A: Gemini
Create an API key in Google AI Studio and set:
```bash
LLM_PROVIDER=gemini
GEMINI_API_KEY=YOUR_KEY
GEMINI_MODEL=gemini-2.0-flash
GEMINI_TIMEOUT=45
LLM_ONLY=true
```

#### Option B: Local Ollama (no internet LLM calls)
Install Ollama and pull a model:
```bash
ollama serve
ollama pull llama3.1:8b
```

Set:
```bash
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.1:8b
OLLAMA_TIMEOUT=120
LLM_ONLY=true
DISABLE_AUTH=true
FIRESTORE_ENABLED=false
```

### 3) Firebase (Auth, optional)
- Create Firebase project (Spark/free)
- Enable **Google** provider in Auth
- Create **Web App** to get client config

Set these env vars:
```bash
NEXT_PUBLIC_FIREBASE_API_KEY=
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=
NEXT_PUBLIC_FIREBASE_PROJECT_ID=
NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=
NEXT_PUBLIC_FIREBASE_APP_ID=
```

### 4) Firebase service account
Generate a private key JSON and set it as a **single‑line** env var:
```bash
FIREBASE_SERVICE_ACCOUNT_KEY={"type":"service_account",...}
```

### 4b) Optional Firestore logging
If you want to store analysis metadata, enable Firestore and set:
```bash
FIRESTORE_ENABLED=true
```
If you want to skip Firestore (no billing), leave it unset or set `false`.

### 5) Run
```bash
python app.py
```

Local URL:
```bash
http://127.0.0.1:5050
```

### 6) Local test checklist (Ollama mode)
1. Start Ollama: `ollama serve`
2. Verify model works: `ollama run llama3.1:8b "return json: {\"ok\":true}"`
3. Start Flask app: `python app.py`
4. Open local URL and run one CV/JD analysis.

## Deploy (Render)
- Use `render.yaml` blueprint
- Build: `./build.sh`
- Start: `gunicorn app:app`
- Add Gemini or Firebase env vars as needed

## Notes
- Uploaded files are processed in memory.
- Sign-in is required only when `DISABLE_AUTH=false`.
- Analysis metadata is stored in Firestore only if `FIRESTORE_ENABLED=true`.
