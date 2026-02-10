import pdf from "pdf-parse";
import mammoth from "mammoth";
import { FieldValue } from "firebase-admin/firestore";
import { getAdmin } from "@/lib/firebaseAdmin";

export const runtime = "nodejs";

const MAX_FILE_MB = 6;
const MAX_CHARS = 12000;

type SalaryRange = { min: number; max: number } | null;
type ScoreInput = number | null | undefined;

type AnalysisPayload = {
  matchScore?: number;
  overallScore?: number | null;
  summary?: string;
  gapAnalysis?: string[];
  improvements?: string[];
  suggestions?: string[];
  keywordMatches?: string[];
  missingKeywords?: string[];
  bulletRewrites?: string[];
  atsNotes?: string[];
  compensationFit?: number | null;
  compensationNotes?: string[];
  keyCategories?: string[];
  matchedCategories?: string[];
  missingCategories?: string[];
  bonusCategories?: string[];
  raw?: string;
};

const STOPWORDS = new Set([
  "the",
  "and",
  "for",
  "with",
  "that",
  "this",
  "from",
  "your",
  "you",
  "our",
  "are",
  "will",
  "can",
  "able",
  "ability",
  "work",
  "works",
  "working",
  "role",
  "responsible",
  "responsibilities",
  "requirements",
  "qualification",
  "qualifications",
  "skills",
  "skill",
  "years",
  "year",
  "experience",
  "including",
  "strong",
  "good",
  "great",
  "excellent",
  "knowledge",
  "understanding",
  "proficient",
  "preferred",
  "plus",
  "bonus",
  "day",
  "team",
  "teams",
  "collaborate",
  "collaboration",
  "develop",
  "design",
  "build",
  "building",
  "deliver",
  "delivery",
  "ensure",
  "using",
  "use",
  "used",
  "within",
  "across",
  "multiple",
  "ability",
  "self",
  "starter",
  "must",
  "nice"
]);

function normalizeCategory(name: string) {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

function formatCategory(name: string) {
  const cleaned = name
    .replace(/[_/]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return cleaned.replace(/\b\w/g, (match) => match.toUpperCase());
}

function ensureStringArray(value: unknown) {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => (typeof item === "string" ? item : ""))
    .map((item) => item.trim())
    .filter(Boolean);
}

function normalizeWeight(value: number, fallback: number) {
  if (!Number.isFinite(value) || value <= 0 || value >= 1) return fallback;
  return value;
}

function computeOverallScore(
  matchScore: ScoreInput,
  compensationFit: ScoreInput
) {
  if (typeof matchScore !== "number") return null;
  if (compensationFit === null || compensationFit === undefined) return matchScore;

  const skillWeight = normalizeWeight(
    Number(process.env.SKILL_WEIGHT ?? "0.8"),
    0.8
  );
  const compWeight = 1 - skillWeight;

  return Math.round(matchScore * skillWeight + compensationFit * compWeight);
}

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

function normalizeTech(text: string) {
  return text
    .replace(/c\+\+/gi, "cplusplus")
    .replace(/c#/gi, "csharp")
    .replace(/\.net/gi, "dotnet")
    .replace(/node\.js/gi, "nodejs")
    .replace(/react\.js/gi, "react");
}

function tokenize(text: string) {
  return normalizeTech(text)
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .map((word) => word.trim())
    .filter((word) => word.length > 2 && !STOPWORDS.has(word));
}

function uniqueTokens(text: string) {
  return Array.from(new Set(tokenize(text)));
}

function computeCategoryMatchScore(matched: string[], total: number) {
  if (!total) return 0;
  return Math.round((matched.length / total) * 100);
}

function fallbackCategoryAnalysis(cvText: string, jdText: string) {
  const jdTokens = uniqueTokens(jdText).slice(0, 6);
  const keyCategories = jdTokens.map(formatCategory);
  const cvTokens = new Set(tokenize(cvText));
  const keyNormalized = new Map<string, string>();
  for (const category of keyCategories) {
    keyNormalized.set(normalizeCategory(category), category);
  }

  const matchedCategories = keyCategories.filter((category) =>
    cvTokens.has(normalizeCategory(category))
  );
  const missingCategories = keyCategories.filter(
    (category) => !cvTokens.has(normalizeCategory(category))
  );
  const bonusCandidates = uniqueTokens(jdText).filter(
    (token) => !keyNormalized.has(normalizeCategory(token))
  );
  const bonusCategories = bonusCandidates
    .filter((token) => cvTokens.has(token))
    .slice(0, 6)
    .map(formatCategory);

  return {
    keyCategories,
    matchedCategories,
    missingCategories,
    bonusCategories
  };
}

function extractKeywordStats(jdText: string, cvText: string) {
  const jdTokens = tokenize(jdText);
  const cvTokens = new Set(tokenize(cvText));
  const freq = new Map<string, number>();

  for (const token of jdTokens) {
    freq.set(token, (freq.get(token) || 0) + 1);
  }

  const sortedTokens = Array.from(freq.entries())
    .sort((a, b) => b[1] - a[1] || b[0].length - a[0].length)
    .map(([token]) => token);

  const keywordMatches: string[] = [];
  const missingKeywords: string[] = [];

  for (const token of sortedTokens) {
    if (cvTokens.has(token)) {
      keywordMatches.push(token);
    } else {
      missingKeywords.push(token);
    }
  }

  return {
    keywordMatches: keywordMatches.slice(0, 30),
    missingKeywords: missingKeywords.slice(0, 30)
  };
}

function heuristicAnalysis(cvText: string, jdText: string): AnalysisPayload {
  const categories = fallbackCategoryAnalysis(cvText, jdText);
  const keywords = extractKeywordStats(jdText, cvText);
  const matchScore = computeCategoryMatchScore(
    categories.matchedCategories,
    categories.keyCategories.length
  );

  return {
    matchScore,
    keyCategories: categories.keyCategories,
    matchedCategories: categories.matchedCategories,
    missingCategories: categories.missingCategories,
    bonusCategories: categories.bonusCategories,
    summary:
      "Heuristic analysis (Gemini not configured). Add GEMINI_API_KEY for deeper insights.",
    gapAnalysis: categories.missingCategories.map(
      (category) => `Missing category: ${category}`
    ),
    improvements: [
      "Add missing category keywords from the job description.",
      "Quantify impact in bullet points (metrics, outcomes, scale).",
      "Align your summary with the role's core responsibilities."
    ],
    suggestions: [
      "Highlight top two projects that demonstrate the missing categories.",
      "Mirror the JD keywords in your summary and skills section.",
      "Lead each bullet with a strong action verb and a measurable outcome."
    ],
    keywordMatches: keywords.keywordMatches,
    missingKeywords: keywords.missingKeywords,
    bulletRewrites: [],
    atsNotes: [
      "Use standard section headings (Experience, Skills, Education).",
      "Avoid tables or complex formatting in the resume file."
    ]
  };
}

async function requestGemini(
  apiKey: string,
  model: string,
  systemPrompt: string,
  userPrompt: string
) {
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      systemInstruction: {
        parts: [{ text: systemPrompt }]
      },
      generationConfig: {
        temperature: 0.2
      },
      contents: [
        {
          role: "user",
          parts: [{ text: userPrompt }]
        }
      ]
    })
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(`Gemini error: ${message}`);
  }

  const data = await response.json();
  const parts = data?.candidates?.[0]?.content?.parts || [];
  return parts.map((part: { text?: string }) => part.text || "").join("");
}

async function getLLMCategories(apiKey: string, model: string, jdText: string) {
  const systemPrompt =
    "You are a senior recruiter. Return ONLY valid JSON with this schema: " +
    "{ keyCategories: string[] }. " +
    "Provide exactly 6 key skill categories from the JD. " +
    "Each category should be 1-4 words, title case, and represent a skill cluster.";

  const userPrompt = `JOB DESCRIPTION:\n\"\"\"\n${jdText}\n\"\"\"`;

  const text = await requestGemini(apiKey, model, systemPrompt, userPrompt);
  const parsed = safeJsonParse(text);
  const keyCategories = ensureStringArray(parsed?.keyCategories)
    .map(formatCategory)
    .slice(0, 6);

  return keyCategories;
}

async function getLLMAssessment(
  apiKey: string,
  model: string,
  cvText: string,
  jdText: string,
  keyCategories: string[]
) {
  const systemPrompt =
    "You are a senior recruiter and ATS specialist. Return ONLY valid JSON with this schema: " +
    "{ summary: string, matchedCategories: string[], missingCategories: string[], bonusCategories: string[], " +
    "suggestions: string[], bulletRewrites: string[], atsNotes: string[] }. " +
    "Rules: matchedCategories and missingCategories must be subsets of the provided key categories. " +
    "bonusCategories are relevant categories found in the CV that are not in keyCategories. " +
    "Suggestions must be actionable and specific (include an example action).";

  const userPrompt = `KEY CATEGORIES:\n${keyCategories.join(", ")}\n\nRESUME:\n\"\"\"\n${cvText}\n\"\"\"\n\nJOB DESCRIPTION:\n\"\"\"\n${jdText}\n\"\"\"`;

  const text = await requestGemini(apiKey, model, systemPrompt, userPrompt);
  const parsed = safeJsonParse(text);
  return parsed || {};
}

async function analyzeWithGemini(
  cvText: string,
  jdText: string
): Promise<AnalysisPayload> {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    return heuristicAnalysis(cvText, jdText);
  }

  const model = process.env.GEMINI_MODEL || "gemini-1.5-flash";

  const keyCategories = await getLLMCategories(apiKey, model, jdText);
  if (keyCategories.length < 3) {
    return heuristicAnalysis(cvText, jdText);
  }

  const assessment = await getLLMAssessment(
    apiKey,
    model,
    cvText,
    jdText,
    keyCategories
  );

  const keyMap = new Map<string, string>();
  for (const category of keyCategories) {
    keyMap.set(normalizeCategory(category), category);
  }

  const matchedRaw = ensureStringArray(assessment?.matchedCategories);
  const matchedNormalized = new Set(
    matchedRaw
      .map((item) => normalizeCategory(item))
      .filter((item) => keyMap.has(item))
  );
  const matchedCategories = Array.from(matchedNormalized).map(
    (item) => keyMap.get(item) || formatCategory(item)
  );

  const missingCategories = keyCategories.filter(
    (category) => !matchedNormalized.has(normalizeCategory(category))
  );

  const bonusRaw = ensureStringArray(assessment?.bonusCategories)
    .map(formatCategory)
    .filter((item) => !keyMap.has(normalizeCategory(item)));
  const bonusCategories = Array.from(new Set(bonusRaw)).slice(0, 8);

  return {
    summary: assessment?.summary,
    suggestions: ensureStringArray(assessment?.suggestions),
    improvements: ensureStringArray(assessment?.suggestions),
    bulletRewrites: ensureStringArray(assessment?.bulletRewrites),
    atsNotes: ensureStringArray(assessment?.atsNotes),
    keyCategories,
    matchedCategories,
    missingCategories,
    bonusCategories
  };
}

export async function POST(req: Request) {
  try {
    const authHeader = req.headers.get("authorization") || "";
    const token = authHeader.startsWith("Bearer ")
      ? authHeader.slice(7)
      : null;

    if (!token) {
      return Response.json(
        { error: "Please sign in with Google to analyze." },
        { status: 401 }
      );
    }

    const { auth, db } = getAdmin();
    const decoded = await auth.verifyIdToken(token);
    const userId = decoded.uid;

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

    const analysis: AnalysisPayload = await analyzeWithGemini(cvText, jdText);

    const keywordStats = extractKeywordStats(jdText, cvText);
    const keyCategories = Array.isArray(analysis.keyCategories)
      ? analysis.keyCategories
      : [];
    const matchedCategories = Array.isArray(analysis.matchedCategories)
      ? analysis.matchedCategories
      : [];
    const missingCategories = Array.isArray(analysis.missingCategories)
      ? analysis.missingCategories
      : keyCategories.filter(
          (category) =>
            !matchedCategories.some(
              (item) => normalizeCategory(item) === normalizeCategory(category)
            )
        );

    analysis.matchScore = computeCategoryMatchScore(
      matchedCategories,
      keyCategories.length
    );
    analysis.missingCategories = missingCategories;

    if (!Array.isArray(analysis.keywordMatches) || analysis.keywordMatches.length === 0) {
      analysis.keywordMatches = keywordStats.keywordMatches;
    }
    if (!Array.isArray(analysis.missingKeywords) || analysis.missingKeywords.length === 0) {
      analysis.missingKeywords = keywordStats.missingKeywords;
    }

    if (!Array.isArray(analysis.gapAnalysis) || analysis.gapAnalysis.length === 0) {
      analysis.gapAnalysis = missingCategories.map(
        (category) => `Missing category: ${category}`
      );
    }

    if (analysis.compensationFit === undefined || analysis.compensationFit === null) {
      analysis.compensationFit = compensation.score;
    }
    const existingNotes = Array.isArray(analysis.compensationNotes)
      ? analysis.compensationNotes
      : [];
    if (existingNotes.length === 0) {
      analysis.compensationNotes = compensation.notes;
    }

    analysis.overallScore = computeOverallScore(
      analysis.matchScore,
      analysis.compensationFit
    );

    await db.collection("analyses").add({
      userId,
      createdAt: FieldValue.serverTimestamp(),
      matchScore: analysis.matchScore ?? null,
      overallScore: analysis.overallScore ?? null,
      keyCategories,
      matchedCategories,
      missingCategories,
      bonusCategories: analysis.bonusCategories || [],
      summary: analysis.summary || null
    });

    await db.collection("users").doc(userId).set(
      {
        email: decoded.email || null,
        lastAnalysisAt: FieldValue.serverTimestamp(),
        totalAnalyses: FieldValue.increment(1)
      },
      { merge: true }
    );

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
    const status = message.includes("verify") || message.includes("sign in") ? 401 : 500;
    return Response.json({ error: message }, { status });
  }
}
