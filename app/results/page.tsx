"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { PDFDocument, StandardFonts } from "pdf-lib";

type Analysis = {
  matchScore?: number;
  summary?: string;
  gapAnalysis?: string[];
  improvements?: string[];
  suggestions?: string[];
  bulletRewrites?: string[];
  atsNotes?: string[];
  compensationFit?: number | null;
  compensationNotes?: string[];
  overallScore?: number | null;
  keyCategories?: string[];
  matchedCategories?: string[];
  missingCategories?: string[];
  bonusCategories?: string[];
  raw?: string;
};

type Meta = {
  cvChars: number;
  jdChars: number;
};

type Payload = {
  analysis: Analysis;
  meta: Meta;
};

const STORAGE_KEY = "resume_analysis_payload";

const formatCategory = (category: string) =>
  category
    .replace(/[_/]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();

const buildMarkdown = (analysis: Analysis, meta?: Meta) => {
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
    "## Key Skill Categories",
    ...(analysis.keyCategories || []).map((item) => `- ${item}`),
    "",
    "## Matched Categories",
    ...(analysis.matchedCategories || []).map((item) => `- ${item}`),
    "",
    "## Missing Categories",
    ...(analysis.missingCategories || []).map((item) => `- ${item}`),
    "",
    "## Bonus Categories",
    ...(analysis.bonusCategories || []).map((item) => `- ${item}`),
    "",
    "## Improvement Suggestions",
    ...(analysis.suggestions || analysis.improvements || []).map(
      (item) => `- ${item}`
    ),
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

  const keyCategories = analysis?.keyCategories || [];
  const matchedCategories = analysis?.matchedCategories || [];
  const missingCategories = analysis?.missingCategories || [];
  const bonusCategories = analysis?.bonusCategories || [];

  const suggestions = useMemo(() => {
    if (!analysis) return [];
    return analysis.suggestions?.length
      ? analysis.suggestions
      : analysis.improvements || [];
  }, [analysis]);

  const rewriteSuggestions = useMemo(() => {
    if (!analysis) return [];
    const rewrites = analysis.bulletRewrites || [];
    if (rewrites.length > 0) return rewrites.slice(0, 5);
    return (analysis.improvements || []).slice(0, 5);
  }, [analysis]);

  const scoreValue = analysis?.overallScore ?? analysis?.matchScore ?? 0;

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
                  Your match score is based on the top 6 skill categories from
                  the JD. Use the plan below to close gaps quickly.
                </p>
                <div className="flex flex-wrap gap-3 text-xs">
                  <span className="rounded-full bg-white/15 px-4 py-2">
                    Key categories: {matchedCategories.length}/{keyCategories.length}
                  </span>
                  <span className="rounded-full bg-white/15 px-4 py-2">
                    Missing: {missingCategories.length}
                  </span>
                  <span className="rounded-full bg-white/15 px-4 py-2">
                    Bonus: {bonusCategories.length}
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
                Category match
              </p>
              <p className="mt-2 text-2xl font-semibold">
                {analysis.matchScore ?? "--"}%
              </p>
              <span className="mt-2 inline-flex rounded-full bg-blue-100 px-3 py-1 text-xs text-blue-600">
                Top 6 categories
              </span>
            </div>
            <div className="rounded-3xl bg-white/95 p-4 text-slate-900 shadow-xl">
              <p className="text-xs uppercase tracking-[0.2em] text-slate-500">
                Key gaps
              </p>
              <p className="mt-2 text-2xl font-semibold">
                {missingCategories.length}
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
                {bonusCategories.length}
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
                  <p className="text-lg font-semibold">Matched categories</p>
                  <p className="text-xs text-slate-500">
                    Top categories already demonstrated in your resume.
                  </p>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                {matchedCategories.length === 0 && (
                  <span className="text-xs text-slate-500">
                    No matching categories detected.
                  </span>
                )}
                {matchedCategories.map((category) => (
                  <span
                    key={`match-${category}`}
                    className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs text-emerald-700"
                  >
                    {formatCategory(category)}
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
                  <p className="text-lg font-semibold">Missing key categories</p>
                  <p className="text-xs text-slate-500">
                    Categories required by the JD but missing in your resume.
                  </p>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                {missingCategories.length === 0 && (
                  <span className="text-xs text-slate-500">
                    No missing categories detected.
                  </span>
                )}
                {missingCategories.map((category) => (
                  <span
                    key={`missing-${category}`}
                    className="rounded-full border border-rose-200 bg-rose-50 px-3 py-1 text-xs text-rose-700"
                  >
                    {formatCategory(category)}
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
                  <p className="text-lg font-semibold">Bonus categories</p>
                  <p className="text-xs text-slate-500">
                    Extra strengths beyond the top 6 categories.
                  </p>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                {bonusCategories.length === 0 && (
                  <span className="text-xs text-slate-500">
                    No bonus categories found.
                  </span>
                )}
                {bonusCategories.map((category) => (
                  <span
                    key={`bonus-${category}`}
                    className="rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs text-blue-700"
                  >
                    {formatCategory(category)}
                  </span>
                ))}
              </div>
            </div>
          </section>

          <section className="mt-10 rounded-[32px] bg-white/95 p-8 text-slate-900 shadow-xl">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-display text-2xl">Skill categories (top 6)</h2>
              <span className="text-xs text-slate-500">
                Dynamic categories extracted from the JD.
              </span>
            </div>
            <div className="mt-6 grid gap-4 md:grid-cols-2">
              {keyCategories.map((category) => {
                const isMatched = matchedCategories.some(
                  (item) => item.toLowerCase() === category.toLowerCase()
                );

                return (
                  <div
                    key={category}
                    className="rounded-2xl border border-slate-200 bg-white p-4"
                  >
                    <div className="flex items-center justify-between">
                      <p className="font-semibold">{formatCategory(category)}</p>
                      <span
                        className={`rounded-full px-3 py-1 text-xs ${
                          isMatched
                            ? "bg-emerald-100 text-emerald-700"
                            : "bg-rose-100 text-rose-700"
                        }`}
                      >
                        {isMatched ? "Matched" : "Missing"}
                      </span>
                    </div>
                    <p className="mt-2 text-xs text-slate-500">
                      {isMatched
                        ? "Evidence found in your resume."
                        : "Add evidence or keywords to cover this category."}
                    </p>
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
                {suggestions.length === 0 && (
                  <div className="rounded-2xl border border-slate-200 bg-white p-4">
                    <p className="text-sm text-slate-600">
                      Run another analysis to generate tailored suggestions.
                    </p>
                  </div>
                )}
                {suggestions.map((item, index) => (
                  <div
                    key={`suggestion-${index}`}
                    className="rounded-2xl border border-slate-200 bg-slate-50 p-4"
                  >
                    <div className="flex items-start gap-4">
                      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-white text-sm font-semibold text-slate-800">
                        {index + 1}
                      </div>
                      <div className="space-y-2">
                        <p className="text-sm text-slate-700">{item}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="grid gap-6 lg:grid-cols-2">
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
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
