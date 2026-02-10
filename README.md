# Resume Analyser (Google Stack)

This app analyzes a CV against a job description, generates dynamic key skill categories, highlights gaps, and provides recruiter‑style suggestions using **Gemini**. Google Sign‑In is required. Firestore logging is optional (disable if you don’t want billing).

## Stack
- Flask + Tailwind (templates)
- Gemini API (free tier)
- Firebase Auth (Google Sign‑In)
- Firestore (optional)
- PDF/DOCX parsing with pdfplumber + python‑docx

## Setup

### 1) Install deps
```bash
pip install -r requirements.txt
```

### 2) Gemini API key
Create an API key in Google AI Studio and set:
```bash
GEMINI_API_KEY=YOUR_KEY
GEMINI_MODEL=gemini-1.5-pro
GEMINI_TIMEOUT=45
LLM_ONLY=true
```

### 3) Firebase (Auth)
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

## Deploy (Render)
- Use `render.yaml` blueprint
- Build: `./build.sh`
- Start: `gunicorn app:app`
- Add all env vars above

## Notes
- Uploaded files are processed in memory.
- Sign in with Google is required to analyze.
- Analysis metadata is stored in Firestore only if `FIRESTORE_ENABLED=true`.
