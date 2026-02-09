import pdf from "pdf-parse";
import mammoth from "mammoth";
import crypto from "crypto";
import { getServerSession } from "next-auth/next";
import { authOptions } from "@/lib/auth";
import { prisma } from "@/lib/db";

export const runtime = "nodejs";

const MAX_FILE_MB = 6;
const MAX_CHARS = 12000;

type SalaryRange = { min: number; max: number } | null;

function parseSalary(input: FormDataEntryValue | null) {
  if (!input) return null;
  const raw = String(input).replace(/[^0-9.]/g, "");
  if (!raw) return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

function normalizeRange(min: number | null, max: number | null): SalaryRange {
  if (min === null && max === null) return null;
  const minValue = min ?? max;
  const maxValue = max ?? min;
  if (minValue === null || maxValue === null) return null;
  const low = Math.min(minValue, maxValue);
  const high = Math.max(minValue, maxValue);
  return { min: low, max: high };
}

function computeCompensationFit(
  candidate: SalaryRange,
  role: SalaryRange
): { score: number | null; notes: string[] } {
  if (!candidate || !role) {
    return {
      score: null,
      notes: ["Compensation info missing for one or both inputs."]
    };
  }

  const span = Math.max(1, role.max - role.min);
  const overlap = Math.max(
    0,
    Math.min(candidate.max, role.max) - Math.max(candidate.min, role.min)
  );

  let score = 0;
  if (overlap > 0) {
    score = Math.round((overlap / span) * 100);
  } else {
    const gap =
      candidate.min > role.max
        ? candidate.min - role.max
        : role.min - candidate.max;
    score = Math.max(0, Math.round(100 - (gap / span) * 100));
  }

  const notes: string[] = [];
  if (overlap > 0) {
    notes.push("Salary expectations overlap with the JD range.");
  } else {
    notes.push("Salary expectations do not overlap with the JD range.");
  }
  if (candidate.min > role.max) {
    notes.push("Candidate expectations sit above the role's stated range.");
  }
  if (candidate.max < role.min) {
    notes.push("Candidate expectations sit below the role's stated range.");
  }

  return { score: Math.max(0, Math.min(100, score)), notes };
}

function getClientIp(req: Request) {
  const forwarded = req.headers.get("x-forwarded-for");
  if (forwarded) {
    return forwarded.split(",")[0]?.trim();
  }
  return req.headers.get("x-real-ip") || req.headers.get("cf-connecting-ip");
}

function hashIp(ip: string) {
  const salt = process.env.RATE_LIMIT_SALT;
  if (!salt) {
    throw new Error("RATE_LIMIT_SALT is not configured.");
  }
  return crypto.createHmac("sha256", salt).update(ip).digest("hex");
}

function getExtension(name: string) {
  const parts = name.split(".");
  if (parts.length < 2) return "";
  return parts[parts.length - 1].toLowerCase();
}

async function extractTextFromFile(file: File) {
  if (file.size > MAX_FILE_MB * 1024 * 1024) {
    throw new Error(`File too large. Max ${MAX_FILE_MB}MB.`);
  }

  const arrayBuffer = await file.arrayBuffer();
  const buffer = Buffer.from(arrayBuffer);
  const ext = getExtension(file.name);
  const type = file.type;

  if (type === "application/pdf" || ext === "pdf") {
    const parsed = await pdf(buffer);
    return parsed.text || "";
  }

  if (
    type ===
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document" ||
    ext === "docx"
  ) {
    const parsed = await mammoth.extractRawText({ buffer });
    return parsed.value || "";
  }

  if (type.startsWith("text/") || ext === "txt") {
    return buffer.toString("utf-8");
  }

  throw new Error("Unsupported file type. Use PDF, DOCX, or TXT.");
}

function clampText(input: string) {
  const trimmed = input.replace(/\s+/g, " ").trim();
  if (trimmed.length <= MAX_CHARS) return trimmed;
  return trimmed.slice(0, MAX_CHARS) + "...";
}

function safeJsonParse(text: string) {
  try {
    return JSON.parse(text);
  } catch {
    const start = text.indexOf("{");
    const end = text.lastIndexOf("}");
    if (start !== -1 && end !== -1 && end > start) {
      try {
        return JSON.parse(text.slice(start, end + 1));
      } catch {
        return null;
      }
    }
    return null;
  }
}

function tokenize(text: string) {
  return text
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((word) => word.length > 2);
}

function heuristicAnalysis(cvText: string, jdText: string) {
  const jdTokens = new Set(tokenize(jdText));
  const cvTokens = new Set(tokenize(cvText));
  const matches: string[] = [];
  const missing: string[] = [];

  for (const token of jdTokens) {
    if (cvTokens.has(token)) {
      matches.push(token);
    } else {
      missing.push(token);
    }
  }

  const score = Math.round((matches.length / Math.max(1, jdTokens.size)) * 100);

  return {
    matchScore: score,
    summary:
      "Heuristic analysis (no LLM key found). Configure GROQ_API_KEY for deeper insights.",
    gapAnalysis: missing.slice(0, 10).map((word) => `Missing keyword: ${word}`),
    improvements: [
      "Add missing role-specific keywords from the job description.",
      "Quantify impact in bullet points (metrics, outcomes, scale).",
      "Align your summary with the role's core responsibilities."
    ],
    keywordMatches: matches.slice(0, 30),
    missingKeywords: missing.slice(0, 30),
    bulletRewrites: [],
    atsNotes: [
      "Use standard section headings (Experience, Skills, Education).",
      "Avoid tables or complex formatting in the resume file."
    ]
  };
}

async function analyzeWithLLM(
  cvText: string,
  jdText: string,
  salaryContext: string
) {
  const apiKey = process.env.GROQ_API_KEY;
  if (!apiKey) {
    return heuristicAnalysis(cvText, jdText);
  }

  const model = process.env.GROQ_MODEL || "llama-3.1-8b-instant";

  const systemPrompt =
    "You are a senior recruiter and ATS specialist. Return ONLY valid JSON with this schema: " +
    "{ matchScore: number (0-100), summary: string, gapAnalysis: string[], improvements: string[], " +
    "keywordMatches: string[], missingKeywords: string[], bulletRewrites: string[], atsNotes: string[], " +
    "compensationFit: number | null, compensationNotes: string[] }." +
    "Match score is a percentage based on fit to the JD.";

  const userPrompt = `RESUME:\n"""\n${cvText}\n"""\n\nJOB DESCRIPTION:\n"""\n${jdText}\n"""\n\nSALARY CONTEXT:\n${salaryContext}`;

  const response = await fetch("https://api.groq.com/openai/v1/chat/completions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`
    },
    body: JSON.stringify({
      model,
      temperature: 0.2,
      messages: [
        { role: "system", content: systemPrompt },
        { role: "user", content: userPrompt }
      ]
    })
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(`LLM error: ${message}`);
  }

  const data = await response.json();
  const text = data?.choices?.[0]?.message?.content || "";
  const parsed = safeJsonParse(text);

  if (parsed) return parsed;

  return {
    matchScore: 0,
    summary: "Unable to parse LLM response. See raw output.",
    gapAnalysis: [],
    improvements: [],
    keywordMatches: [],
    missingKeywords: [],
    bulletRewrites: [],
    atsNotes: [],
    raw: text
  };
}

export async function POST(req: Request) {
  try {
    const session = await getServerSession(authOptions);
    let ipHash: string | null = null;

    if (!session) {
      if (!process.env.DATABASE_URL) {
        return Response.json(
          { error: "DATABASE_URL is not configured for usage limits." },
          { status: 500 }
        );
      }

      const ip = getClientIp(req);
      if (!ip) {
        return Response.json(
          { error: "Unable to verify usage limit. Missing client IP." },
          { status: 400 }
        );
      }

      ipHash = hashIp(ip);
      const usage = await prisma.usage.findUnique({ where: { ipHash } });
      if (usage && usage.count >= 1) {
        return Response.json(
          { error: "Free analysis used. Sign in with GitHub to continue." },
          { status: 403 }
        );
      }
    }

    const formData = await req.formData();

    const cvTextInput = (formData.get("cvText") as string | null) || "";
    const jdTextInput = (formData.get("jdText") as string | null) || "";

    const cvSalaryMin = parseSalary(formData.get("cvSalaryMin"));
    const cvSalaryMax = parseSalary(formData.get("cvSalaryMax"));
    const jdSalaryMin = parseSalary(formData.get("jdSalaryMin"));
    const jdSalaryMax = parseSalary(formData.get("jdSalaryMax"));

    const cvFile = formData.get("cvFile") as File | null;
    const jdFile = formData.get("jdFile") as File | null;

    const cvText = cvTextInput.trim()
      ? clampText(cvTextInput)
      : cvFile
      ? clampText(await extractTextFromFile(cvFile))
      : "";

    const jdText = jdTextInput.trim()
      ? clampText(jdTextInput)
      : jdFile
      ? clampText(await extractTextFromFile(jdFile))
      : "";

    if (!cvText || !jdText) {
      return Response.json(
        { error: "Please provide both a resume and a Job Description." },
        { status: 400 }
      );
    }

    const candidateRange = normalizeRange(cvSalaryMin, cvSalaryMax);
    const roleRange = normalizeRange(jdSalaryMin, jdSalaryMax);
    const compensation = computeCompensationFit(candidateRange, roleRange);

    const salaryContextParts = [
      `Candidate expected range: ${
        candidateRange ? `$${candidateRange.min} - $${candidateRange.max}` : "not provided"
      }`,
      `Role range: ${
        roleRange ? `$${roleRange.min} - $${roleRange.max}` : "not provided"
      }`
    ];

    const analysis = await analyzeWithLLM(
      cvText,
      jdText,
      salaryContextParts.join("\n")
    );

    if (analysis.compensationFit === undefined || analysis.compensationFit === null) {
      analysis.compensationFit = compensation.score;
    }
    const existingNotes = Array.isArray(analysis.compensationNotes)
      ? analysis.compensationNotes
      : [];
    if (existingNotes.length === 0) {
      analysis.compensationNotes = compensation.notes;
    }

    if (!session && ipHash) {
      await prisma.usage.upsert({
        where: { ipHash },
        update: { count: { increment: 1 } },
        create: { ipHash, count: 1 }
      });
    }

    return Response.json({
      analysis,
      meta: {
        cvChars: cvText.length,
        jdChars: jdText.length
      }
    });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unexpected server error";
    return Response.json({ error: message }, { status: 500 });
  }
}
