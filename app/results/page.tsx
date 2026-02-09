"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { PDFDocument, StandardFonts } from "pdf-lib";

type ScorePart = {
  matched: number;
  total: number;
  ratio: number;
  weight: number;
};

type ScoreBreakdown = {
  requirements?: ScorePart;
  responsibilities?: ScorePart;
  preferred?: ScorePart;
  other?: ScorePart;
};

type Analysis = {
  matchScore?: number;
  summary?: string;
  gapAnalysis?: string[];
  improvements?: string[];
  keywordMatches?: string[];
  missingKeywords?: string[];
  bulletRewrites?: string[];
  atsNotes?: string[];
  compensationFit?: number | null;
  compensationNotes?: string[];
  overallScore?: number | null;
  scoreBreakdown?: ScoreBreakdown;
  raw?: string;
};

type Meta = {
  cvChars: number;
  jdChars: number;
  scoreBreakdown?: ScoreBreakdown;
  skillBuckets?: {
    keySkills?: string[];
    bonusSkills?: string[];
  };
};

type Payload = {
  analysis: Analysis;
  meta: Meta;
};

const STORAGE_KEY = "resume_analysis_payload";

const CATEGORY_KEYWORDS: Record<string, string[]> = {
  Languages: [
    "javascript",
    "typescript",
    "python",
    "java",
    "csharp",
    "cplusplus",
    "go",
    "golang",
    "ruby",
    "php",
    "swift",
    "kotlin",
    "scala",
    "rust",
    "sql"
  ],
  Frontend: [
    "react",
    "next",
    "vue",
    "angular",
    "svelte",
    "html",
    "css",
    "tailwind",
    "redux",
    "webpack",
    "vite",
    "storybook",
    "jquery"
  ],
  Backend: [
    "nodejs",
    "express",
    "nestjs",
    "django",
    "flask",
    "fastapi",
    "spring",
    "rails",
    "graphql",
    "rest",
    "grpc",
    "microservices",
    "api",
    "backend"
  ],
  "Cloud & DevOps": [
    "aws",
    "gcp",
    "azure",
    "docker",
    "kubernetes",
    "terraform",
    "ci",
    "cd",
    "github",
    "gitlab",
    "jenkins",
    "helm",
    "cloud",
    "devops"
  ],
  "Data & AI": [
    "postgres",
    "mysql",
    "mongodb",
    "redis",
    "elasticsearch",
    "kafka",
    "spark",
    "hadoop",
    "pandas",
    "numpy",
    "tensorflow",
    "pytorch",
    "ml",
    "ai",
    "llm",
    "vector",
    "snowflake"
  ],
  "Product & Leadership": [
    "stakeholder",
    "communication",
    "leadership",
    "mentoring",
    "roadmap",
    "agile",
    "scrum",
    "product",
    "design",
    "collaboration",
    "ownership",
    "strategy"
  ]
};

const CATEGORY_ORDER = [
  "Languages",
  "Frontend",
  "Backend",
  "Cloud & DevOps",
  "Data & AI",
  "Product & Leadership",
  "Other"
];

const cleanGap = (item: string) =>
  item.replace(/^Missing keyword:\s*/i, "").replace(/\.$/, "").trim();

const buildActionItems = (analysis: Analysis) => {
  const items: string[] = [];

  for (const improvement of analysis.improvements || []) {
    items.push(`Do: ${improvement}`);
  }

  for (const gap of (analysis.gapAnalysis || []).slice(0, 6)) {
    const keyword = cleanGap(gap);
    if (keyword) {
      items.push(`Add evidence for ${keyword} (project, metric, or tool).`);
    } else {
      items.push(`Close gap: ${gap}`);
    }
  }

  for (const rewrite of (analysis.bulletRewrites || []).slice(0, 3)) {
    items.push(`Rewrite a bullet: ${rewrite}`);
  }

  return Array.from(new Set(items)).slice(0, 8);
};

const formatCoverage = (part?: ScorePart) => {
  if (!part || part.total === 0) return "N/A";
  return `${Math.round(part.ratio * 100)}% (${part.matched}/${part.total})`;
};

const prettySkill = (skill: string) => {
  const map: Record<string, string> = {
    nodejs: "Node.js",
    csharp: "C#",
    cplusplus: "C++",
    dotnet: ".NET",
    aws: "AWS",
    gcp: "GCP",
    ai: "AI",
    ml: "ML",
    llm: "LLM"
  };

  if (map[skill]) return map[skill];
  if (skill.length <= 3) return skill.toUpperCase();
  return skill.charAt(0).toUpperCase() + skill.slice(1);
};

const buildCategoryMap = () => {
  const map = new Map<string, string>();
  for (const [category, keywords] of Object.entries(CATEGORY_KEYWORDS)) {
    for (const keyword of keywords) {
      map.set(keyword, category);
    }
  }
  return map;
};

const categorizeSkills = (skills: string[]) => {
  const map = buildCategoryMap();
  const buckets: Record<string, string[]> = {};
  for (const category of CATEGORY_ORDER) {
    buckets[category] = [];
  }

  for (const skill of skills) {
    const key = skill.toLowerCase();
    const category = map.get(key) || "Other";
    if (!buckets[category].includes(skill)) {
      buckets[category].push(skill);
    }
  }

  return buckets;
};

const buildMarkdown = (analysis: Analysis, meta?: Meta) => {
  const actionItems = buildActionItems(analysis);
  const lines = [
    "# Resume Analyser Report",
    "",
    `Overall Score: ${
      analysis.overallScore === null || analysis.overallScore === undefined
        ? "N/A"
        : `${analysis.overallScore}%`
    }`,
    `Match Score: ${analysis.matchScore ?? "N/A"}%`,
    `Compensation Fit: ${
      analysis.compensationFit === null || analysis.compensationFit === undefined
        ? "N/A"
        : `${analysis.compensationFit}%`
    }`,
    analysis.summary ? `Summary: ${analysis.summary}` : "",
    "",
    meta ? `Resume chars: ${meta.cvChars} | JD chars: ${meta.jdChars}` : "",
    "",
    "## Score Breakdown",
    `Requirements coverage: ${formatCoverage(meta?.scoreBreakdown?.requirements)}`,
    `Responsibilities coverage: ${formatCoverage(
      meta?.scoreBreakdown?.responsibilities
    )}`,
    `Preferred coverage: ${formatCoverage(meta?.scoreBreakdown?.preferred)}`,
    "",
    "## Action Plan",
    ...actionItems.map((item) => `- ${item}`),
    "",
    "## Compensation Notes",
    ...(Array.isArray(analysis.compensationNotes)
      ? analysis.compensationNotes
      : []
    ).map((item) => `- ${item}`),
    "",
    "## Gap Analysis",
    ...(analysis.gapAnalysis || []).map((item) => `- ${item}`),
    "",
    "## Improvements",
    ...(analysis.improvements || []).map((item) => `- ${item}`),
    "",
    "## Keyword Matches",
    ...(analysis.keywordMatches || []).map((item) => `- ${item}`),
    "",
    "## Missing Keywords",
    ...(analysis.missingKeywords || []).map((item) => `- ${item}`),
    "",
    "## Bullet Rewrites",
    ...(analysis.bulletRewrites || []).map((item) => `- ${item}`),
    "",
    "## ATS Notes",
    ...(analysis.atsNotes || []).map((item) => `- ${item}`)
  ];

  return lines.filter(Boolean).join("\n");
};

const ProgressRing = ({ value }: { value: number }) => {
  const size = 140;
  const stroke = 10;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = Math.max(0, Math.min(100, value));
  const offset = circumference - (progress / 100) * circumference;

  return (
    <div className="relative flex h-36 w-36 items-center justify-center">
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke="rgba(255,255,255,0.2)"
          strokeWidth={stroke}
          fill="transparent"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke="url(#scoreGradient)"
          strokeWidth={stroke}
          fill="transparent"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
        />
        <defs>
          <linearGradient id="scoreGradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#ff9a7b" />
            <stop offset="50%" stopColor="#ffd36b" />
            <stop offset="100%" stopColor="#7dd3fc" />
          </linearGradient>
        </defs>
      </svg>
      <div className="absolute text-center text-white">
        <p className="text-3xl font-semibold">{progress}%</p>
        <p className="text-xs uppercase tracking-[0.2em] text-white/70">
          Match
        </p>
      </div>
    </div>
  );
};

export default function ResultsPage() {
  const router = useRouter();
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) {
      setError("No analysis data found. Start a new analysis.");
      return;
    }

    try {
      const payload = JSON.parse(stored) as Payload;
      setAnalysis(payload.analysis);
      setMeta(payload.meta);
    } catch {
      setError("Unable to read analysis data. Please run a new analysis.");
    }
  }, []);

  const handleReset = () => {
    localStorage.removeItem(STORAGE_KEY);
    router.push("/");
  };

  const actionItems = useMemo(
    () => (analysis ? buildActionItems(analysis) : []),
    [analysis]
  );

  const keySkills = meta?.skillBuckets?.keySkills || [];
  const bonusSkills = meta?.skillBuckets?.bonusSkills || [];

  const matchedSet = new Set(analysis?.keywordMatches || []);
  const missingSet = new Set(analysis?.missingKeywords || []);

  const matchingSkills = keySkills.filter((skill) => matchedSet.has(skill));
  const missingKeySkills = keySkills.filter((skill) => missingSet.has(skill));
  const bonusMatched = bonusSkills.filter((skill) => matchedSet.has(skill));
  const bonusMissing = bonusSkills.filter((skill) => missingSet.has(skill));

  const matchingByCategory = useMemo(
    () => categorizeSkills(matchingSkills),
    [matchingSkills]
  );
  const missingByCategory = useMemo(
    () => categorizeSkills(missingKeySkills),
    [missingKeySkills]
  );
  const bonusByCategory = useMemo(
    () => categorizeSkills([...bonusMatched, ...bonusMissing]),
    [bonusMatched, bonusMissing]
  );

  const rewriteSuggestions = useMemo(() => {
    if (!analysis) return [];
    const rewrites = analysis.bulletRewrites || [];
    if (rewrites.length > 0) return rewrites.slice(0, 5);
    return (analysis.improvements || []).slice(0, 5);
  }, [analysis]);

  const scoreValue =
    analysis?.overallScore ?? analysis?.matchScore ?? analysis?.compensationFit ?? 0;

  const suggestionBlocks = useMemo(() => {
    const blocks = [] as {
      title: string;
      description: string;
      items: string[];
      tone: "alert" | "warn" | "good";
    }[];

    if (missingKeySkills.length > 0) {
      blocks.push({
        title: "Close critical gaps",
        description:
          "Prioritize these missing skills to immediately raise your match score.",
        items: missingKeySkills.slice(0, 4).map((skill) =>
          `Add ${prettySkill(skill)} with a concrete project example.`
        ),
        tone: "alert"
      });
    }

    if (rewriteSuggestions.length > 0) {
      blocks.push({
        title: "Rewrite for impact",
        description:
          "Sharper bullets make your fit obvious to both ATS and recruiters.",
        items: rewriteSuggestions,
        tone: "warn"
      });
    }

    if ((analysis?.atsNotes || []).length > 0) {
      blocks.push({
        title: "Polish for ATS",
        description:
          "Small formatting tweaks improve parsing and recruiter readability.",
        items: analysis?.atsNotes?.slice(0, 3) || [],
        tone: "good"
      });
    }

    return blocks;
  }, [analysis, missingKeySkills, rewriteSuggestions]);

  const downloadReport = () => {
    if (!analysis) return;
    const content = buildMarkdown(analysis, meta || undefined);
    const blob = new Blob([content], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "resume-analysis-report.md";
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const downloadReportPdf = async () => {
    if (!analysis) return;
    const content = buildMarkdown(analysis, meta || undefined);
    const pdfDoc = await PDFDocument.create();
    const pageSize: [number, number] = [612, 792];
    let page = pdfDoc.addPage(pageSize);
    const font = await pdfDoc.embedFont(StandardFonts.Helvetica);
    const fontSize = 11;
    const lineHeight = 16;
    const margin = 48;
    const maxWidth = page.getWidth() - margin * 2;

    const wrapText = (text: string) => {
      const lines: string[] = [];
      for (const paragraph of text.split("\n")) {
        if (!paragraph.trim()) {
          lines.push("");
          continue;
        }
        let line = "";
        for (const word of paragraph.split(" ")) {
          const testLine = line ? `${line} ${word}` : word;
          const width = font.widthOfTextAtSize(testLine, fontSize);
          if (width > maxWidth) {
            if (line) lines.push(line);
            line = word;
          } else {
            line = testLine;
          }
        }
        if (line) lines.push(line);
      }
      return lines;
    };

    const lines = wrapText(content);
    let y = page.getHeight() - margin;

    for (const line of lines) {
      if (y < margin + lineHeight) {
        page = pdfDoc.addPage(pageSize);
        y = page.getHeight() - margin;
      }

      if (line) {
        page.drawText(line, { x: margin, y, size: fontSize, font });
      }

      y -= line ? lineHeight : lineHeight * 0.7;
    }

    const pdfBytes = await pdfDoc.save();
    const blob = new Blob([new Uint8Array(pdfBytes)], {
      type: "application/pdf"
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "resume-analysis-report.pdf";
    anchor.click();
    URL.revokeObjectURL(url);
  };

  if (error) {
    return (
      <div className="min-h-screen bg-slate-950 px-6 pb-16 pt-16 sm:px-10">
        <div className="mx-auto max-w-3xl rounded-3xl bg-white/90 p-8 text-center">
          <h1 className="font-display text-3xl">No analysis found</h1>
          <p className="mt-3 text-sm text-ink/60">{error}</p>
          <button
            onClick={handleReset}
            className="mt-6 rounded-full bg-ink px-5 py-2 text-sm text-white"
          >
            Start a new analysis
          </button>
        </div>
      </div>
    );
  }

  if (!analysis) {
    return (
      <div className="min-h-screen bg-slate-950 px-6 pb-16 pt-16 sm:px-10">
        <div className="mx-auto max-w-3xl rounded-3xl bg-white/90 p-8 text-center">
          <p className="text-sm text-ink/60">Loading your analysis...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="relative min-h-screen overflow-hidden bg-slate-950 text-white">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(109,87,255,0.45),_transparent_55%)]" />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_40%,_rgba(243,87,168,0.3),_transparent_50%)]" />
      <div className="absolute inset-0 bg-gradient-to-br from-[#4b3cf5] via-[#6d50ff] to-[#f357a8] opacity-90" />
      <div className="relative">
        <div className="mx-auto max-w-6xl px-6 pb-20 pt-12 sm:px-10">
          <header className="flex flex-col gap-8">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-4 py-2 text-xs uppercase tracking-[0.2em]">
                Resume Analyser · Results
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={downloadReport}
                  className="rounded-full border border-white/30 bg-white/10 px-4 py-2 text-xs"
                >
                  Download MD
                </button>
                <button
                  onClick={downloadReportPdf}
                  className="rounded-full border border-white/30 bg-white/10 px-4 py-2 text-xs"
                >
                  Download PDF
                </button>
                <button
                  onClick={handleReset}
                  className="rounded-full bg-white px-4 py-2 text-xs text-[#4b3cf5]"
                >
                  New analysis
                </button>
              </div>
            </div>

            <div className="grid gap-8 lg:grid-cols-[auto_1fr]">
              <div className="rounded-[32px] border border-white/15 bg-white/10 p-6 shadow-2xl">
                <ProgressRing value={scoreValue} />
                <p className="mt-4 text-center text-xs uppercase tracking-[0.2em] text-white/70">
                  Match score
                </p>
              </div>
              <div className="space-y-4">
                <h1 className="font-display text-4xl font-semibold sm:text-5xl">
                  Analysis Complete
                </h1>
                <p className="max-w-2xl text-sm text-white/80">
                  Your match score is calibrated against the JD requirements,
                  responsibilities, and preferred skills. Use the action plan to
                  close gaps quickly.
                </p>
                <div className="flex flex-wrap gap-3 text-xs">
                  <span className="rounded-full bg-white/15 px-4 py-2">
                    Requirements: {formatCoverage(meta?.scoreBreakdown?.requirements)}
                  </span>
                  <span className="rounded-full bg-white/15 px-4 py-2">
                    Responsibilities: {formatCoverage(
                      meta?.scoreBreakdown?.responsibilities
                    )}
                  </span>
                  <span className="rounded-full bg-white/15 px-4 py-2">
                    Preferred: {formatCoverage(meta?.scoreBreakdown?.preferred)}
                  </span>
                </div>
              </div>
            </div>
          </header>

          <section className="mt-10 grid gap-4 md:grid-cols-4">
            <div className="rounded-3xl bg-white/95 p-4 text-slate-900 shadow-xl">
              <p className="text-xs uppercase tracking-[0.2em] text-slate-500">
                Overall
              </p>
              <p className="mt-2 text-2xl font-semibold">
                {analysis.overallScore ?? analysis.matchScore ?? "--"}%
              </p>
              <span className="mt-2 inline-flex rounded-full bg-emerald-100 px-3 py-1 text-xs text-emerald-700">
                Calibrated
              </span>
            </div>
            <div className="rounded-3xl bg-white/95 p-4 text-slate-900 shadow-xl">
              <p className="text-xs uppercase tracking-[0.2em] text-slate-500">
                Skill match
              </p>
              <p className="mt-2 text-2xl font-semibold">
                {analysis.matchScore ?? "--"}%
              </p>
              <span className="mt-2 inline-flex rounded-full bg-blue-100 px-3 py-1 text-xs text-blue-600">
                Requirements + responsibilities
              </span>
            </div>
            <div className="rounded-3xl bg-white/95 p-4 text-slate-900 shadow-xl">
              <p className="text-xs uppercase tracking-[0.2em] text-slate-500">
                Key gaps
              </p>
              <p className="mt-2 text-2xl font-semibold">
                {missingKeySkills.length}
              </p>
              <span className="mt-2 inline-flex rounded-full bg-amber-100 px-3 py-1 text-xs text-amber-700">
                Focus these first
              </span>
            </div>
            <div className="rounded-3xl bg-white/95 p-4 text-slate-900 shadow-xl">
              <p className="text-xs uppercase tracking-[0.2em] text-slate-500">
                Bonus skills
              </p>
              <p className="mt-2 text-2xl font-semibold">
                {bonusMatched.length}
              </p>
              <span className="mt-2 inline-flex rounded-full bg-purple-100 px-3 py-1 text-xs text-purple-700">
                Differentiators
              </span>
            </div>
          </section>

          <section className="mt-10 grid gap-6 lg:grid-cols-3">
            <div className="rounded-3xl bg-white/95 p-6 text-slate-900 shadow-xl">
              <div className="flex items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-emerald-100 text-emerald-600">
                  ✓
                </span>
                <div>
                  <p className="text-lg font-semibold">Matched skills</p>
                  <p className="text-xs text-slate-500">
                    Skills from the JD already shown in your resume.
                  </p>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                {matchingSkills.length === 0 && (
                  <span className="text-xs text-slate-500">
                    No matching skills detected.
                  </span>
                )}
                {matchingSkills.slice(0, 20).map((skill) => (
                  <span
                    key={`match-${skill}`}
                    className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs text-emerald-700"
                  >
                    {prettySkill(skill)}
                  </span>
                ))}
              </div>
            </div>
            <div className="rounded-3xl bg-white/95 p-6 text-slate-900 shadow-xl">
              <div className="flex items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-rose-100 text-rose-600">
                  ✕
                </span>
                <div>
                  <p className="text-lg font-semibold">Missing key skills</p>
                  <p className="text-xs text-slate-500">
                    Skills required by the JD but missing in your resume.
                  </p>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                {missingKeySkills.length === 0 && (
                  <span className="text-xs text-slate-500">
                    No missing skills detected.
                  </span>
                )}
                {missingKeySkills.slice(0, 20).map((skill) => (
                  <span
                    key={`missing-${skill}`}
                    className="rounded-full border border-rose-200 bg-rose-50 px-3 py-1 text-xs text-rose-700"
                  >
                    {prettySkill(skill)}
                  </span>
                ))}
              </div>
            </div>
            <div className="rounded-3xl bg-white/95 p-6 text-slate-900 shadow-xl">
              <div className="flex items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-blue-100 text-blue-600">
                  +
                </span>
                <div>
                  <p className="text-lg font-semibold">Bonus skills</p>
                  <p className="text-xs text-slate-500">
                    Nice‑to‑have skills that boost differentiation.
                  </p>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                {bonusSkills.length === 0 && (
                  <span className="text-xs text-slate-500">
                    No bonus skills found.
                  </span>
                )}
                {bonusSkills.slice(0, 20).map((skill) => (
                  <span
                    key={`bonus-${skill}`}
                    className={`rounded-full border px-3 py-1 text-xs ${
                      bonusMatched.includes(skill)
                        ? "border-blue-200 bg-blue-50 text-blue-700"
                        : "border-slate-200 bg-slate-100 text-slate-700"
                    }`}
                  >
                    {prettySkill(skill)}
                  </span>
                ))}
              </div>
            </div>
          </section>

          <section className="mt-10 rounded-[32px] bg-white/95 p-8 text-slate-900 shadow-xl">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-display text-2xl">Skill categories</h2>
              <span className="text-xs text-slate-500">
                5–6 focused buckets for clearer targeting.
              </span>
            </div>
            <div className="mt-6 grid gap-4 md:grid-cols-2">
              {CATEGORY_ORDER.map((category) => {
                const matched = matchingByCategory[category] || [];
                const missing = missingByCategory[category] || [];
                const bonus = bonusByCategory[category] || [];
                const totalCount = matched.length + missing.length + bonus.length;
                if (category === "Other" && totalCount === 0) return null;

                return (
                  <div
                    key={category}
                    className="rounded-2xl border border-slate-200 bg-white p-4"
                  >
                    <div className="flex items-center justify-between">
                      <p className="font-semibold">{category}</p>
                      <span className="text-xs text-slate-500">
                        {matched.length} matched · {missing.length} missing
                      </span>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {matched.slice(0, 8).map((skill) => (
                        <span
                          key={`cat-match-${category}-${skill}`}
                          className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs text-emerald-700"
                        >
                          {prettySkill(skill)}
                        </span>
                      ))}
                      {missing.slice(0, 8).map((skill) => (
                        <span
                          key={`cat-miss-${category}-${skill}`}
                          className="rounded-full border border-rose-200 bg-rose-50 px-3 py-1 text-xs text-rose-700"
                        >
                          {prettySkill(skill)}
                        </span>
                      ))}
                      {bonus.slice(0, 6).map((skill) => (
                        <span
                          key={`cat-bonus-${category}-${skill}`}
                          className="rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs text-blue-700"
                        >
                          {prettySkill(skill)}
                        </span>
                      ))}
                      {totalCount === 0 && (
                        <span className="text-xs text-slate-500">
                          No skills detected in this category.
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          <section className="mt-10 grid gap-6">
            <div className="rounded-[32px] bg-white/95 p-8 text-slate-900 shadow-xl">
              <div className="flex items-center gap-3">
                <span className="text-xl">✨</span>
                <h2 className="font-display text-2xl">Improvement suggestions</h2>
              </div>

              <div className="mt-6 grid gap-4">
                {suggestionBlocks.length === 0 && (
                  <div className="rounded-2xl border border-slate-200 bg-white p-4">
                    <p className="text-sm text-slate-600">
                      Run another analysis to generate tailored suggestions.
                    </p>
                  </div>
                )}
                {suggestionBlocks.map((block, index) => (
                  <div
                    key={`${block.title}-${index}`}
                    className={`rounded-2xl border p-5 ${
                      block.tone === "alert"
                        ? "border-rose-200 bg-rose-50"
                        : block.tone === "warn"
                        ? "border-amber-200 bg-amber-50"
                        : "border-emerald-200 bg-emerald-50"
                    }`}
                  >
                    <div className="flex items-start gap-4">
                      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-white text-sm font-semibold text-slate-800">
                        {index + 1}
                      </div>
                      <div className="space-y-2">
                        <p className="text-lg font-semibold text-slate-900">
                          {block.title}
                        </p>
                        <p className="text-sm text-slate-600">
                          {block.description}
                        </p>
                        <div className="grid gap-2">
                          {block.items.map((item, itemIndex) => (
                            <div
                              key={`${block.title}-${itemIndex}`}
                              className="rounded-xl border border-white/80 bg-white/70 px-4 py-3 text-sm text-slate-700"
                            >
                              {item}
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="grid gap-6 lg:grid-cols-2">
              <div className="rounded-[32px] bg-white/95 p-6 text-slate-900 shadow-xl">
                <h2 className="font-display text-2xl">Action plan</h2>
                <p className="text-xs text-slate-500">
                  Focus on these steps to raise your score quickly.
                </p>
                <ol className="mt-4 list-decimal space-y-2 pl-5 text-sm text-slate-700">
                  {actionItems.length === 0 && (
                    <li>Run another analysis to get a full action list.</li>
                  )}
                  {actionItems.map((item, index) => (
                    <li key={`action-${index}`}>{item}</li>
                  ))}
                </ol>
              </div>

              <div className="rounded-[32px] bg-white/95 p-6 text-slate-900 shadow-xl">
                <h2 className="font-display text-2xl">Rewrite playbook</h2>
                <p className="text-xs text-slate-500">
                  Direct bullet updates you can paste into the resume.
                </p>
                <ul className="mt-4 list-disc space-y-2 pl-5 text-sm text-slate-700">
                  {rewriteSuggestions.length === 0 && (
                    <li>No rewrite suggestions yet. Try again with more detail.</li>
                  )}
                  {rewriteSuggestions.map((item, index) => (
                    <li key={`rewrite-${index}`}>{item}</li>
                  ))}
                </ul>
              </div>
            </div>

            <div className="grid gap-6 lg:grid-cols-2">
              <div className="rounded-[32px] bg-white/95 p-6 text-slate-900 shadow-xl">
                <h2 className="font-display text-2xl">Other tips</h2>
                <p className="text-xs text-slate-500">
                  ATS and recruiter tips that improve readability.
                </p>
                <ul className="mt-4 list-disc space-y-2 pl-5 text-sm text-slate-700">
                  {(analysis.atsNotes || []).length === 0 && (
                    <li>Keep sections clear with standard headings.</li>
                  )}
                  {(analysis.atsNotes || []).map((note, index) => (
                    <li key={`note-${index}`}>{note}</li>
                  ))}
                </ul>
              </div>

              <div className="rounded-[32px] bg-white/95 p-6 text-slate-900 shadow-xl">
                <h2 className="font-display text-2xl">Compensation notes</h2>
                <p className="text-xs text-slate-500">
                  Salary alignment insights based on the ranges provided.
                </p>
                <ul className="mt-4 list-disc space-y-2 pl-5 text-sm text-slate-700">
                  {(analysis.compensationNotes || []).length === 0 && (
                    <li>Add ranges to view salary fit insights.</li>
                  )}
                  {(analysis.compensationNotes || []).map((note, index) => (
                    <li key={`comp-${index}`}>{note}</li>
                  ))}
                </ul>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
