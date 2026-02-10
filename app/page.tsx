"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  GoogleAuthProvider,
  User,
  onAuthStateChanged,
  signInWithPopup,
  signOut
} from "firebase/auth";
import { auth } from "@/lib/firebaseClient";

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
  const [authUser, setAuthUser] = useState<User | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (user) => {
      setAuthUser(user);
      setAuthReady(true);
    });

    return () => unsubscribe();
  }, []);

  const handleSignIn = async () => {
    setAuthError(null);
    try {
      const provider = new GoogleAuthProvider();
      await signInWithPopup(auth, provider);
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : "Unable to sign in.");
    }
  };

  const handleSignOut = async () => {
    setAuthError(null);
    try {
      await signOut(auth);
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : "Unable to sign out.");
    }
  };

  const handleAnalyze = async () => {
    setError(null);

    if (!authUser) {
      setError("Please sign in with Google to analyze.");
      return;
    }

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
      const token = await authUser.getIdToken();
      const response = await fetch("/api/analyze", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`
        },
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
    <div className="min-h-screen px-6 pb-16 pt-16 sm:px-10">
      <div className="mx-auto flex max-w-6xl justify-end">
        {!authReady ? (
          <span className="text-xs text-slate-500">Checking sign-in…</span>
        ) : authUser ? (
          <div className="flex items-center gap-3 text-xs text-slate-600">
            <span>
              Signed in as{" "}
              <span className="font-semibold text-slate-800">
                {authUser.email || "Google user"}
              </span>
            </span>
            <button
              onClick={handleSignOut}
              className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-700"
            >
              Sign out
            </button>
          </div>
        ) : (
          <button
            onClick={handleSignIn}
            className="rounded-full bg-blue-600 px-4 py-2 text-xs font-semibold text-white"
          >
            Sign in with Google
          </button>
        )}
      </div>

      {authError && (
        <div className="mx-auto mt-3 max-w-6xl rounded-2xl bg-rose-50 px-4 py-3 text-xs text-rose-600">
          {authError}
        </div>
      )}

      <div className="mx-auto max-w-6xl text-center">
        <h1 className="font-display text-4xl font-semibold text-slate-900 sm:text-5xl">
          CV & Job Description Matcher
        </h1>
        <p className="mt-3 text-base text-slate-600 sm:text-lg">
          Upload your CV and Job Description to get a detailed compatibility
          analysis
        </p>
      </div>

      <main className="mx-auto mt-10 grid max-w-6xl gap-6 lg:grid-cols-2">
        <section className="soft-card p-6">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-blue-100 text-blue-600">
              📄
            </span>
            <h2 className="text-xl font-semibold text-slate-900">Your CV</h2>
          </div>

          <div className="mt-4 flex rounded-full bg-slate-100 p-1 text-sm">
            <button
              onClick={() => setCvMode("file")}
              className={`flex-1 rounded-full px-3 py-2 font-medium ${
                cvMode === "file"
                  ? "bg-blue-600 text-white"
                  : "text-slate-600"
              }`}
            >
              Upload File
            </button>
            <button
              onClick={() => setCvMode("text")}
              className={`flex-1 rounded-full px-3 py-2 font-medium ${
                cvMode === "text"
                  ? "bg-blue-600 text-white"
                  : "text-slate-600"
              }`}
            >
              Paste Text
            </button>
          </div>

          <div className="mt-5 rounded-2xl border-2 border-dashed border-slate-200 bg-slate-50 p-6 text-center">
            {cvMode === "file" ? (
              <>
                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-200 text-lg">
                  ⬆️
                </div>
                <p className="mt-3 text-sm font-medium text-slate-700">
                  Click to upload or drag and drop
                </p>
                <p className="text-xs text-slate-500">
                  TXT, PDF, DOC up to 10MB
                </p>
                <input
                  type="file"
                  accept=".pdf,.docx,.txt"
                  onChange={(event) => setCvFile(event.target.files?.[0] || null)}
                  className="mt-4 w-full text-sm"
                />
                {cvFile && (
                  <p className="mt-2 text-xs text-slate-500">{cvFile.name}</p>
                )}
              </>
            ) : (
              <textarea
                value={cvText}
                onChange={(event) => setCvText(event.target.value)}
                placeholder="Paste your CV here..."
                rows={7}
                className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700"
              />
            )}
          </div>
        </section>

        <section className="soft-card p-6">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-purple-100 text-purple-600">
              🔗
            </span>
            <h2 className="text-xl font-semibold text-slate-900">
              Job Description
            </h2>
          </div>

          <div className="mt-4 flex rounded-full bg-slate-100 p-1 text-sm">
            <button
              onClick={() => setJdMode("file")}
              className={`flex-1 rounded-full px-3 py-2 font-medium ${
                jdMode === "file"
                  ? "bg-purple-600 text-white"
                  : "text-slate-600"
              }`}
            >
              Upload File
            </button>
            <button
              onClick={() => setJdMode("text")}
              className={`flex-1 rounded-full px-3 py-2 font-medium ${
                jdMode === "text"
                  ? "bg-purple-600 text-white"
                  : "text-slate-600"
              }`}
            >
              Paste Text
            </button>
          </div>

          <div className="mt-5 rounded-2xl border-2 border-dashed border-slate-200 bg-slate-50 p-6 text-center">
            {jdMode === "file" ? (
              <>
                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-200 text-lg">
                  ⬆️
                </div>
                <p className="mt-3 text-sm font-medium text-slate-700">
                  Click to upload or drag and drop
                </p>
                <p className="text-xs text-slate-500">
                  TXT, PDF, DOC up to 10MB
                </p>
                <input
                  type="file"
                  accept=".pdf,.docx,.txt"
                  onChange={(event) => setJdFile(event.target.files?.[0] || null)}
                  className="mt-4 w-full text-sm"
                />
                {jdFile && (
                  <p className="mt-2 text-xs text-slate-500">{jdFile.name}</p>
                )}
              </>
            ) : (
              <textarea
                value={jdText}
                onChange={(event) => setJdText(event.target.value)}
                placeholder="Paste the job description here..."
                rows={7}
                className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700"
              />
            )}
          </div>
        </section>
      </main>

      <div className="mx-auto mt-8 max-w-6xl">
        <div className="soft-card px-6 py-5">
          <div className="grid gap-4 md:grid-cols-[1.2fr_0.8fr]">
            <div>
              <h3 className="text-lg font-semibold text-slate-900">
                Compensation (optional)
              </h3>
              <p className="text-xs text-slate-500">
                Add ranges to compute a salary‑fit score. Leave empty if not
                applicable.
              </p>
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <p className="text-sm font-semibold text-slate-700">
                    Candidate expectations
                  </p>
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
                  <p className="text-sm font-semibold text-slate-700">Role range</p>
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
            <div className="flex flex-col justify-between">
              <div>
                <h3 className="text-lg font-semibold text-slate-900">
                  Analyze Match
                </h3>
                <p className="text-xs text-slate-500">
                  Get your compatibility score in seconds.
                </p>
              </div>
              <div className="mt-4">
                {error && (
                  <div className="rounded-2xl bg-rose-50 p-3 text-sm text-rose-600">
                    {error}
                  </div>
                )}
                <button
                  onClick={handleAnalyze}
                  disabled={loading || !authUser}
                  className="mt-4 w-full rounded-full bg-blue-600 px-6 py-3 text-sm font-semibold text-white shadow disabled:opacity-60"
                >
                  {loading
                    ? "Analyzing..."
                    : authUser
                    ? "Analyze Match"
                    : "Sign in to Analyze"}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
