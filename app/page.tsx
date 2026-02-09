"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

type InputMode = "file" | "text";

export default function Home() {
  const router = useRouter();
  const [cvMode, setCvMode] = useState<InputMode>("file");
  const [jdMode, setJdMode] = useState<InputMode>("text");
  const [cvFile, setCvFile] = useState<File | null>(null);
  const [jdFile, setJdFile] = useState<File | null>(null);
  const [cvText, setCvText] = useState("");
  const [jdText, setJdText] = useState("");
  const [cvSalaryMin, setCvSalaryMin] = useState("");
  const [cvSalaryMax, setCvSalaryMax] = useState("");
  const [jdSalaryMin, setJdSalaryMin] = useState("");
  const [jdSalaryMax, setJdSalaryMax] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAnalyze = async () => {
    setError(null);

    if (cvMode === "file" && !cvFile) {
      setError("Please upload a resume file.");
      return;
    }
    if (cvMode === "text" && !cvText.trim()) {
      setError("Please paste your resume text.");
      return;
    }
    if (jdMode === "file" && !jdFile) {
      setError("Please upload a JD file.");
      return;
    }
    if (jdMode === "text" && !jdText.trim()) {
      setError("Please paste the JD text.");
      return;
    }

    const formData = new FormData();
    if (cvMode === "file" && cvFile) formData.append("cvFile", cvFile);
    if (cvMode === "text") formData.append("cvText", cvText);
    if (jdMode === "file" && jdFile) formData.append("jdFile", jdFile);
    if (jdMode === "text") formData.append("jdText", jdText);
    if (cvSalaryMin) formData.append("cvSalaryMin", cvSalaryMin);
    if (cvSalaryMax) formData.append("cvSalaryMax", cvSalaryMax);
    if (jdSalaryMin) formData.append("jdSalaryMin", jdSalaryMin);
    if (jdSalaryMax) formData.append("jdSalaryMax", jdSalaryMax);

    try {
      setLoading(true);
      const response = await fetch("/api/analyze", {
        method: "POST",
        body: formData
      });
      const data = await response.json();
      if (!response.ok) {
        setError(data?.error || "Analysis failed.");
      } else {
        localStorage.setItem("resume_analysis_payload", JSON.stringify(data));
        router.push("/results");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unexpected error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen overflow-hidden bg-slate-950 text-white">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(109,87,255,0.5),_transparent_60%)]" />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_30%,_rgba(243,87,168,0.35),_transparent_55%)]" />
      <div className="absolute inset-0 bg-gradient-to-br from-[#4b3cf5] via-[#6d50ff] to-[#f357a8] opacity-90" />
      <div className="noise" />

      <div className="relative">
        <header className="mx-auto flex max-w-6xl flex-col items-center px-6 pb-12 pt-16 text-center sm:px-10">
          <div className="inline-flex items-center gap-2 rounded-full border border-white/30 bg-white/10 px-4 py-2 text-xs uppercase tracking-[0.2em]">
            Resume Analyser · Premium insights
          </div>
          <h1 className="mt-6 font-display text-4xl font-semibold sm:text-6xl">
            Analyze your resume against any job
          </h1>
          <p className="mt-4 max-w-2xl text-base text-white/80 sm:text-lg">
            Upload a resume, paste text, or drop a file — then match it against
            any job description instantly with actionable next steps.
          </p>
          <div className="mt-6 flex flex-wrap justify-center gap-3 text-xs">
            <span className="rounded-full border border-white/20 bg-white/15 px-4 py-2">
              PDF · DOCX · TXT
            </span>
            <span className="rounded-full border border-white/20 bg-white/15 px-4 py-2">
              Unlimited analyses
            </span>
            <span className="rounded-full border border-white/20 bg-white/15 px-4 py-2">
              Skill gap mapping
            </span>
            <span className="rounded-full border border-white/20 bg-white/15 px-4 py-2">
              Actionable rewrites
            </span>
          </div>
          <a
            href="#inputs"
            className="mt-8 inline-flex items-center justify-center rounded-full bg-white px-6 py-3 text-sm font-semibold text-[#4b3cf5] shadow-lg"
          >
            Start analysis
          </a>
        </header>

        <main id="inputs" className="mx-auto max-w-6xl px-6 pb-20 sm:px-10">
          <div className="rounded-[36px] border border-white/40 bg-white text-slate-900 shadow-2xl">
            <div className="grid gap-6 p-6 lg:grid-cols-2 lg:p-8">
              <div className="overflow-hidden rounded-3xl border border-slate-200 bg-white">
                <div className="bg-gradient-to-r from-[#5b5bf0] to-[#8b5cf6] px-5 py-4 text-white">
                  <div className="flex items-center gap-2 text-sm font-semibold">
                    <span className="flex h-8 w-8 items-center justify-center rounded-full bg-white/20">
                      📄
                    </span>
                    Your Resume
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2 text-xs">
                    <button
                      onClick={() => setCvMode("file")}
                      className={`rounded-full px-4 py-1.5 ${
                        cvMode === "file"
                          ? "bg-white text-[#5b5bf0]"
                          : "border border-white/40 text-white/80"
                      }`}
                    >
                      Upload File
                    </button>
                    <button
                      onClick={() => setCvMode("text")}
                      className={`rounded-full px-4 py-1.5 ${
                        cvMode === "text"
                          ? "bg-white text-[#5b5bf0]"
                          : "border border-white/40 text-white/80"
                      }`}
                    >
                      Paste Text
                    </button>
                    <span className="rounded-full border border-white/30 px-4 py-1.5 text-white/60">
                      LinkedIn URL (soon)
                    </span>
                  </div>
                </div>
                <div className="p-6">
                  {cvMode === "file" ? (
                    <div className="rounded-2xl border-2 border-dashed border-slate-200 bg-slate-50/70 p-6 text-center">
                      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-200 text-lg">
                        ⬆️
                      </div>
                      <p className="mt-3 text-sm font-medium text-slate-700">
                        Drop a file or click to browse
                      </p>
                      <p className="text-xs text-slate-500">
                        PDF, DOCX, or TXT (max 6 MB)
                      </p>
                      <input
                        type="file"
                        accept=".pdf,.docx,.txt"
                        onChange={(event) =>
                          setCvFile(event.target.files?.[0] || null)
                        }
                        className="mt-4 w-full text-sm"
                      />
                      {cvFile && (
                        <p className="mt-2 text-xs text-slate-500">
                          {cvFile.name}
                        </p>
                      )}
                    </div>
                  ) : (
                    <textarea
                      value={cvText}
                      onChange={(event) => setCvText(event.target.value)}
                      placeholder="Paste resume content here..."
                      rows={7}
                      className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm"
                    />
                  )}
                </div>
              </div>

              <div className="overflow-hidden rounded-3xl border border-slate-200 bg-white">
                <div className="bg-gradient-to-r from-[#a855f7] to-[#ec4899] px-5 py-4 text-white">
                  <div className="flex items-center gap-2 text-sm font-semibold">
                    <span className="flex h-8 w-8 items-center justify-center rounded-full bg-white/20">
                      💼
                    </span>
                    Job Description
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2 text-xs">
                    <button
                      onClick={() => setJdMode("file")}
                      className={`rounded-full px-4 py-1.5 ${
                        jdMode === "file"
                          ? "bg-white text-[#a855f7]"
                          : "border border-white/40 text-white/80"
                      }`}
                    >
                      Upload File
                    </button>
                    <button
                      onClick={() => setJdMode("text")}
                      className={`rounded-full px-4 py-1.5 ${
                        jdMode === "text"
                          ? "bg-white text-[#a855f7]"
                          : "border border-white/40 text-white/80"
                      }`}
                    >
                      Paste Text
                    </button>
                    <span className="rounded-full border border-white/30 px-4 py-1.5 text-white/60">
                      Job URL (soon)
                    </span>
                  </div>
                </div>
                <div className="p-6">
                  {jdMode === "file" ? (
                    <div className="rounded-2xl border-2 border-dashed border-slate-200 bg-slate-50/70 p-6 text-center">
                      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-200 text-lg">
                        ⬆️
                      </div>
                      <p className="mt-3 text-sm font-medium text-slate-700">
                        Drop a file or click to browse
                      </p>
                      <p className="text-xs text-slate-500">
                        PDF, DOCX, or TXT (max 6 MB)
                      </p>
                      <input
                        type="file"
                        accept=".pdf,.docx,.txt"
                        onChange={(event) =>
                          setJdFile(event.target.files?.[0] || null)
                        }
                        className="mt-4 w-full text-sm"
                      />
                      {jdFile && (
                        <p className="mt-2 text-xs text-slate-500">
                          {jdFile.name}
                        </p>
                      )}
                    </div>
                  ) : (
                    <textarea
                      value={jdText}
                      onChange={(event) => setJdText(event.target.value)}
                      placeholder="Paste job description here..."
                      rows={7}
                      className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm"
                    />
                  )}
                </div>
              </div>
            </div>

            <div className="border-t border-slate-200 px-6 pb-8 pt-6 lg:px-8">
              <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
                <div className="rounded-3xl bg-slate-50 p-5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 className="text-lg font-semibold">
                      Compensation (optional)
                    </h3>
                    <span className="text-xs text-slate-500">Annual USD</span>
                  </div>
                  <p className="text-xs text-slate-500">
                    Add ranges to compute a salary‑fit score. Leave empty if not
                    applicable.
                  </p>
                  <div className="mt-4 grid gap-4 sm:grid-cols-2">
                    <div className="rounded-2xl border border-slate-200 bg-white p-4">
                      <p className="text-sm font-semibold">Candidate expectations</p>
                      <div className="mt-3 grid gap-3 sm:grid-cols-2">
                        <input
                          type="number"
                          min="0"
                          value={cvSalaryMin}
                          onChange={(event) => setCvSalaryMin(event.target.value)}
                          placeholder="Min (e.g. 80000)"
                          className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
                        />
                        <input
                          type="number"
                          min="0"
                          value={cvSalaryMax}
                          onChange={(event) => setCvSalaryMax(event.target.value)}
                          placeholder="Max (e.g. 110000)"
                          className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
                        />
                      </div>
                    </div>
                    <div className="rounded-2xl border border-slate-200 bg-white p-4">
                      <p className="text-sm font-semibold">Role range</p>
                      <div className="mt-3 grid gap-3 sm:grid-cols-2">
                        <input
                          type="number"
                          min="0"
                          value={jdSalaryMin}
                          onChange={(event) => setJdSalaryMin(event.target.value)}
                          placeholder="Min (e.g. 90000)"
                          className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
                        />
                        <input
                          type="number"
                          min="0"
                          value={jdSalaryMax}
                          onChange={(event) => setJdSalaryMax(event.target.value)}
                          placeholder="Max (e.g. 120000)"
                          className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
                        />
                      </div>
                    </div>
                  </div>
                </div>

                <div className="flex flex-col justify-between rounded-3xl border border-slate-200 bg-white p-5">
                  <div>
                    <h3 className="text-lg font-semibold">What you’ll get</h3>
                    <p className="text-xs text-slate-500">
                      A modern, action‑first results page.
                    </p>
                    <ul className="mt-4 space-y-2 text-sm text-slate-600">
                      <li>Overall match percentage</li>
                      <li>Skill gaps + bonus skills</li>
                      <li>Rewrite recommendations</li>
                      <li>ATS and compensation tips</li>
                    </ul>
                  </div>
                  <div className="mt-6">
                    {error && (
                      <div className="rounded-2xl bg-rose-50 p-3 text-sm text-rose-600">
                        {error}
                      </div>
                    )}
                    <button
                      onClick={handleAnalyze}
                      disabled={loading}
                      className="mt-4 w-full rounded-full bg-gradient-to-r from-[#4b3cf5] to-[#f357a8] px-6 py-3 text-sm font-semibold text-white shadow-lg disabled:opacity-60"
                    >
                      {loading ? "Analyzing..." : "Analyze Resume"}
                    </button>
                    <p className="mt-3 text-xs text-slate-500">
                      Results open in a dedicated analysis view.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
