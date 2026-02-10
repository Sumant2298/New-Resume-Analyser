# Resume Analyser (Google Stack)

Upload a resume + JD, get a match score, dynamic skill categories, and action‑oriented improvements powered by **Google Gemini**, with **Google Sign‑In** and **Firestore** tracking.

## Stack
- Next.js (App Router)
- Tailwind CSS
- Google Gemini API (free tier)
- Firebase Auth (Google Sign‑In)
- Firestore (free tier)
- PDF/DOCX parsing via `pdf-parse` + `mammoth`

## Setup

1) Install deps
```bash
npm install
```

2) Create a Google Gemini API key
- Go to Google AI Studio and create an API key.
- Set:
```bash
GEMINI_API_KEY=YOUR_KEY
GEMINI_MODEL=gemini-1.5-flash
```

3) Create a Firebase project (free tier)
- Firebase Console → Create project (Spark free plan).
- **Authentication** → Sign‑in method → Enable **Google**.
- **Firestore Database** → Create database (start in production or test).
- **Project settings → Your apps** → Create a **Web app**.
- Copy the Firebase config values into env vars:
```bash
NEXT_PUBLIC_FIREBASE_API_KEY=...
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=...
NEXT_PUBLIC_FIREBASE_PROJECT_ID=...
NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=...
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=...
NEXT_PUBLIC_FIREBASE_APP_ID=...
```

4) Create a Firebase service account key
- Project settings → Service accounts → Generate new private key.
- Set it as a **single‑line JSON string** in env:
```bash
FIREBASE_SERVICE_ACCOUNT_KEY={"type":"service_account",...}
```
Tip: Use `JSON.stringify()` to make it one line.

5) Optional score weighting
```bash
SKILL_WEIGHT=0.8
```

6) Run
```bash
npm run dev
```

## Notes
- Resume/JD files are processed in memory only and **not** stored.
- We only store lightweight analysis metadata in Firestore (scores & categories).
- Downloads are generated locally (Markdown + PDF).

## Deploy (Render)
- Create a new Web Service from this repo.
- Build: `npm run build`
- Start: `npm run start`
- Add all env vars from above in Render.
- Use the included `render.yaml` blueprint for easy deployment.

## Env Summary
```bash
GEMINI_API_KEY=
GEMINI_MODEL=gemini-1.5-flash
SKILL_WEIGHT=0.8
FIREBASE_SERVICE_ACCOUNT_KEY=
NEXT_PUBLIC_FIREBASE_API_KEY=
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=
NEXT_PUBLIC_FIREBASE_PROJECT_ID=
NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=
NEXT_PUBLIC_FIREBASE_APP_ID=
```
