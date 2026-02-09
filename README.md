# CV Analyzer (MVP)

Upload a CV + JD, get a match score, compensation fit, gap analysis, and actionable CV improvements. Includes a one‑free‑analysis gate and GitHub OAuth for additional analyses.

## Stack
- Next.js (App Router)
- Tailwind CSS
- NextAuth (GitHub OAuth)
- Groq API (free tier, OpenAI‑compatible)
- PDF/DOCX parsing via `pdf-parse` + `mammoth`
- Postgres + Prisma (server‑side usage limits)

## Setup

1) Install deps
```bash
npm install
```

2) Create `.env.local`
```bash
GROQ_API_KEY=YOUR_GROQ_KEY
GROQ_MODEL=llama-3.1-8b-instant
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=REPLACE_ME
GITHUB_ID=YOUR_GITHUB_OAUTH_CLIENT_ID
GITHUB_SECRET=YOUR_GITHUB_OAUTH_CLIENT_SECRET
DATABASE_URL=postgresql://user:pass@host:5432/dbname
RATE_LIMIT_SALT=LONG_RANDOM_STRING
```

3) Run migrations + generate Prisma client
```bash
npm run prisma:generate
npm run prisma:migrate
```

4) Run
```bash
npm run dev
```

## Notes
- CV/JD files are processed in memory only and not stored on the server.
- One free analysis is enforced server‑side by IP hash. Authenticated users are unlimited.
- Report downloads are available in Markdown and PDF.
- Render deployment: set the env vars above and use `npm run build` + `npm run start`.

## Deploy (Render)
- Create a new Web Service from this repo.
- Build command: `npm run build`
- Start command: `npm run start`
- Add env vars from `.env.local` in the Render dashboard.
- Add a Postgres instance in Render and copy its `DATABASE_URL`.
- Run `npx prisma migrate deploy` in Render (or add as a build step).

### Render Blueprint
This repo includes a `render.yaml` blueprint. You can deploy with it and then fill in the secret env vars in the Render UI.
