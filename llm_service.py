"""Gemini-powered recruiter insights for CV analysis.

This module replaces Groq with Google's Gemini API (free tier).
Graceful degradation:
- If GEMINI_API_KEY is not set, functions return empty/heuristic results.
- If the API call fails, the app continues with NLP-only analysis.
"""

import ast
import json
import logging
import os
import re
import time

import requests

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-2.0-flash')
GEMINI_TIMEOUT = int(os.environ.get('GEMINI_TIMEOUT', '45'))
GEMINI_MIN_JSON_CHARS = int(os.environ.get('GEMINI_MIN_JSON_CHARS', '180'))
LLM_ENABLED = bool(GEMINI_API_KEY)
_MODEL_CACHE = {"ts": 0.0, "models": []}
_LAST_WORKING_MODEL = None
_PREFERRED_MODELS = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.0-pro",
    "gemini-2.0-pro",
]

SYSTEM_PROMPT = """You are a strict JSON generator.
Return ONLY valid JSON. No markdown, no code fences, no commentary.
If a value is missing, use "Not specified".
"""

CATEGORY_MATCH_SCHEMA = """{
  "key_categories": ["Category 1", "Category 2", "..."],
  "matched_categories": ["Category 1"],
  "missing_categories": ["Category 2"],
  "bonus_categories": ["Bonus Category A", "Bonus Category B"],
  "skill_groups": [
    {
      "category": "Category 1",
      "skills": ["Skill A", "Skill B"],
      "importance": "Must-have" or "Nice-to-have"
    }
  ]
}"""

SKILL_GROUPS_SCHEMA = """{
  "skill_groups": [
    {
      "category": "Category name",
      "skills": ["Skill 1", "Skill 2"],
      "importance": "Must-have" or "Nice-to-have"
    }
  ]
}"""

RECRUITER_SCHEMA = """{
  "profile_summary": "3-5 sentences. Start with overall assessment. Use you/your.",
  "quick_match_insights": {
    "experience": "One sentence.",
    "education": "One sentence.",
    "skills": "One sentence.",
    "location": "One sentence."
  },
  "enhanced_suggestions": [
    {
      "title": "Short recruiter-style title",
      "body": "Specific, actionable guidance.",
      "examples": ["Example rewrite 1", "Example rewrite 2"]
    }
  ],
  "working_well": ["Specific strength"],
  "needs_improvement": ["Specific gap"],
  "ats_score": 45,
  "skill_gap_tips": {"Skill": "Actionable tip"}
}"""

COMBINED_SCHEMA = """{
  "category_match": {
    "key_categories": ["Category 1", "Category 2", "..."],
    "matched_categories": ["Category 1"],
    "missing_categories": ["Category 2"],
    "bonus_categories": ["Bonus Category A", "Bonus Category B"],
    "skill_groups": [
      {
        "category": "Category 1",
        "skills": ["Skill A", "Skill B"],
        "importance": "Must-have" or "Nice-to-have"
      }
    ]
  },
  "insights": {
    "profile_summary": "3-5 sentences. Start with overall assessment. Use you/your.",
    "quick_match_insights": {
      "experience": "One sentence.",
      "education": "One sentence.",
      "skills": "One sentence.",
      "location": "One sentence."
    },
    "enhanced_suggestions": [
      {
        "title": "Short recruiter-style title",
        "body": "Specific, actionable guidance.",
        "examples": ["Example rewrite 1", "Example rewrite 2"]
      }
    ],
    "working_well": ["Specific strength"],
    "needs_improvement": ["Specific gap"],
    "ats_score": 45,
    "skill_gap_tips": {"Skill": "Actionable tip"}
  }
}"""

FULL_ANALYSIS_SCHEMA = """{
  "scores": {
    "ats": 0,
    "text_similarity": 0,
    "skill_match": 0,
    "verb_alignment": 0
  },
  "quick_match": {
    "experience": {"cv_value": "...", "jd_value": "...", "match_quality": "Strong Match|Good Match|Weak Match|Not a Match"},
    "education": {"cv_value": "...", "jd_value": "...", "match_quality": "Strong Match|Good Match|Weak Match|Not a Match"},
    "skills": {"cv_value": "...", "jd_value": "...", "match_quality": "Strong Match|Good Match|Weak Match|Not a Match"},
    "location": {"cv_value": "...", "jd_value": "...", "match_quality": "Strong Match|Good Match|Weak Match|Not a Match"}
  },
  "category_match": {
    "key_categories": ["Category 1", "Category 2", "Category 3", "Category 4", "Category 5", "Category 6"],
    "matched_categories": ["Category 1"],
    "missing_categories": ["Category 2"],
    "bonus_categories": ["Bonus Category"],
    "skill_groups": [
      {
        "category": "Category 1",
        "importance": "Must-have|Nice-to-have",
        "skills": [
          {"name": "Skill A", "found": true},
          {"name": "Skill B", "found": false}
        ]
      }
    ]
  },
  "experience_analysis": {
    "common_action_verbs": ["built", "led"],
    "missing_action_verbs": ["designed"],
    "section_relevance": [{"section": "Projects", "relevance": 72}]
  },
  "insights": {
    "profile_summary": "3-5 sentences",
    "working_well": ["..."],
    "needs_improvement": ["..."],
    "skill_gap_tips": {"Skill": "Tip"},
    "enhanced_suggestions": [
      {"title": "...", "body": "...", "examples": ["..."]}
    ]
  }
}"""

SCORES_SCHEMA = """{
  "scores": {"ats": 0, "text_similarity": 0, "skill_match": 0, "verb_alignment": 0},
  "quick_match": {
    "experience": {"cv_value": "", "jd_value": "", "match_quality": ""},
    "education": {"cv_value": "", "jd_value": "", "match_quality": ""},
    "skills": {"cv_value": "", "jd_value": "", "match_quality": ""},
    "location": {"cv_value": "", "jd_value": "", "match_quality": ""}
  },
  "keywords": {"jd": [], "cv": []}
}"""

SCORES_MIN_SCHEMA = """{
  "scores": {"ats": 0, "text_similarity": 0, "skill_match": 0, "verb_alignment": 0},
  "quick_match": {
    "experience": {"cv_value": "", "jd_value": "", "match_quality": ""},
    "education": {"cv_value": "", "jd_value": "", "match_quality": ""},
    "skills": {"cv_value": "", "jd_value": "", "match_quality": ""},
    "location": {"cv_value": "", "jd_value": "", "match_quality": ""}
  }
}"""

CATEGORIES_SCHEMA = """{
  "key_categories": ["Category 1", "Category 2", "Category 3", "Category 4", "Category 5", "Category 6"],
  "matched_categories": ["Category 1"],
  "missing_categories": ["Category 2"],
  "bonus_categories": ["Bonus Category"]
}"""

SKILL_GROUPS_MIN_SCHEMA = """{
  "skill_groups": [
    {
      "category": "Category 1",
      "importance": "Must-have|Nice-to-have",
      "skills": [
        {"name": "Skill A", "found": true},
        {"name": "Skill B", "found": false}
      ]
    }
  ]
}"""

INSIGHTS_SCHEMA = """{
  "profile_summary": "",
  "working_well": ["..."],
  "needs_improvement": ["..."],
  "skill_gap_tips": {"Skill": "Tip"},
  "enhanced_suggestions": [
    {"title": "...", "body": "...", "examples": ["Example 1", "Example 2"]}
  ]
}"""



def _safe_json_parse(text: str):
    try:
        return json.loads(text)
    except Exception:
        if not text:
            return None
        cleaned = text.strip()
        cleaned = re.sub(r'```(?:json)?', '', cleaned, flags=re.IGNORECASE).strip()
        start = cleaned.find('{')
        end = cleaned.rfind('}')
        if start != -1 and end != -1 and end > start:
            cleaned = cleaned[start:end + 1]

        # Remove trailing commas
        cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)

        try:
            return json.loads(cleaned)
        except Exception:
            # Last-resort: Python literal eval with JSON bool/null fixups
            py_like = re.sub(r'\btrue\b', 'True', cleaned, flags=re.IGNORECASE)
            py_like = re.sub(r'\bfalse\b', 'False', py_like, flags=re.IGNORECASE)
            py_like = re.sub(r'\bnull\b', 'None', py_like, flags=re.IGNORECASE)
            try:
                return ast.literal_eval(py_like)
            except Exception:
                return None


def _split_items(text: str, max_items: int | None = None) -> list[str]:
    if not text:
        return []
    cleaned = text.strip()
    cleaned = re.sub(r'```(?:json)?', '', cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r'(?i)^(matched|missing|bonus)\\s*[:\\-]\\s*', '', cleaned)
    parts = re.split(r'[\\n,;|]+', cleaned)
    items: list[str] = []
    for part in parts:
        item = re.sub(r'^[\\s\\-\\d\\.)]+', '', part).strip()
        if not item:
            continue
        if item.lower() in ('none', 'n/a', 'na'):
            continue
        items.append(item)
        if max_items and len(items) >= max_items:
            break
    return items


def _validate_scores_quickmatch(data: dict) -> bool:
    if not isinstance(data, dict):
        return False
    scores = data.get("scores")
    if not isinstance(scores, dict):
        return False
    required_scores = {"ats", "text_similarity", "skill_match", "verb_alignment"}
    if not required_scores.issubset(scores.keys()):
        return False

    quick_match = data.get("quick_match")
    if not isinstance(quick_match, dict):
        return False
    for field in ("experience", "education", "skills", "location"):
        item = quick_match.get(field)
        if not isinstance(item, dict):
            return False
        if "cv_value" not in item or "jd_value" not in item:
            return False

    keywords = data.get("keywords")
    if not isinstance(keywords, dict):
        return False
    if not isinstance(keywords.get("jd"), list) or not isinstance(keywords.get("cv"), list):
        return False
    return True


def _coerce_scores_quickmatch(data: dict) -> dict:
    if not isinstance(data, dict):
        data = {}

    scores = data.get("scores") if isinstance(data.get("scores"), dict) else {}
    def _num(val):
        if isinstance(val, (int, float)):
            return max(0, min(100, int(val)))
        if isinstance(val, str) and val.strip().isdigit():
            return max(0, min(100, int(val.strip())))
        return 0

    scores = {
        "ats": _num(scores.get("ats")),
        "text_similarity": _num(scores.get("text_similarity")),
        "skill_match": _num(scores.get("skill_match")),
        "verb_alignment": _num(scores.get("verb_alignment")),
    }

    qm = data.get("quick_match") if isinstance(data.get("quick_match"), dict) else {}
    def _qm_item(raw):
        if not isinstance(raw, dict):
            raw = {}
        cv_val = str(raw.get("cv_value", "Not specified")) if raw.get("cv_value") is not None else "Not specified"
        jd_val = str(raw.get("jd_value", "Not specified")) if raw.get("jd_value") is not None else "Not specified"
        match_quality = str(raw.get("match_quality", "Not a Match"))
        if match_quality not in ("Strong Match", "Good Match", "Weak Match", "Not a Match"):
            match_quality = "Not a Match"
        return {"cv_value": cv_val, "jd_value": jd_val, "match_quality": match_quality}

    quick_match = {
        "experience": _qm_item(qm.get("experience")),
        "education": _qm_item(qm.get("education")),
        "skills": _qm_item(qm.get("skills")),
        "location": _qm_item(qm.get("location")),
    }

    keywords = data.get("keywords") if isinstance(data.get("keywords"), dict) else {}
    jd_kw = keywords.get("jd") if isinstance(keywords.get("jd"), list) else []
    cv_kw = keywords.get("cv") if isinstance(keywords.get("cv"), list) else []
    jd_kw = [str(x) for x in jd_kw if isinstance(x, (str, int, float))][:12]
    cv_kw = [str(x) for x in cv_kw if isinstance(x, (str, int, float))][:12]

    return {
        "scores": scores,
        "quick_match": quick_match,
        "keywords": {"jd": jd_kw, "cv": cv_kw},
    }


def _validate_categories(data: dict) -> bool:
    if not isinstance(data, dict):
        return False
    key_categories = data.get("key_categories")
    if not isinstance(key_categories, list) or len(key_categories) != 6:
        return False
    for name in ("matched_categories", "missing_categories", "bonus_categories"):
        if not isinstance(data.get(name), list):
            return False
    return True


def _validate_skill_groups(data: dict, key_categories: list[str]) -> bool:
    if not isinstance(data, dict):
        return False
    groups = data.get("skill_groups")
    if not isinstance(groups, list) or not groups:
        return False
    valid_categories = {c.strip().lower() for c in key_categories if isinstance(c, str)}
    if not valid_categories:
        return False
    for group in groups:
        if not isinstance(group, dict):
            return False
        cat = str(group.get("category", "")).strip().lower()
        if cat not in valid_categories:
            return False
        skills = group.get("skills")
        if not isinstance(skills, list) or not skills:
            return False
    return True


def _validate_insights(data: dict) -> bool:
    if not isinstance(data, dict):
        return False
    if not isinstance(data.get("profile_summary"), str):
        return False
    if not isinstance(data.get("enhanced_suggestions"), list):
        return False
    if not isinstance(data.get("working_well"), list):
        return False
    if not isinstance(data.get("needs_improvement"), list):
        return False
    return True


def _repair_json(raw_text: str, schema_hint: str, max_output_tokens: int = 700) -> dict | None:
    if not raw_text:
        return None
    snippet = raw_text[:2000]
    prompt = f"""Convert the text below into valid JSON that matches this schema.
Return ONLY JSON. Do not add commentary.

Schema:
{schema_hint}

Text:
\"\"\"
{snippet}
\"\"\"
"""
    try:
        fixed = _call_gemini(
            SYSTEM_PROMPT,
            prompt,
            temperature=0.0,
            max_output_tokens=max_output_tokens,
            response_mime_type="application/json",
        )
        return _safe_json_parse(fixed)
    except Exception:
        return None


def _list_models() -> list[str]:
    if not GEMINI_API_KEY:
        return []
    now = time.time()
    if _MODEL_CACHE["models"] and now - _MODEL_CACHE["ts"] < 300:
        return _MODEL_CACHE["models"]
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
        resp = requests.get(url, timeout=10)
        if not resp.ok:
            return []
        data = resp.json()
        models = []
        for item in data.get("models", []):
            name = item.get("name", "")
            methods = item.get("supportedGenerationMethods", [])
            if "generateContent" in methods and name.startswith("models/"):
                models.append(name.replace("models/", ""))
        if models:
            logger.info("Gemini available models: %s", ", ".join(models[:12]))
        _MODEL_CACHE["models"] = models
        _MODEL_CACHE["ts"] = now
        return models
    except Exception:
        return []


def _candidate_models() -> list[str]:
    candidates: list[str] = []
    if _LAST_WORKING_MODEL:
        candidates.append(_LAST_WORKING_MODEL)
    if GEMINI_MODEL and GEMINI_MODEL not in candidates:
        candidates.append(GEMINI_MODEL)
    # Prefer known good models if available from listModels
    available = set(_list_models())
    for m in _PREFERRED_MODELS:
        if m in available and m not in candidates:
            candidates.append(m)
    # If listModels returned nothing, fall back to preference order
    if not available:
        for m in _PREFERRED_MODELS:
            if m not in candidates:
                candidates.append(m)
    return candidates[:6]


def _call_gemini(system_prompt: str, user_prompt: str,
                 temperature: float = 0.2, max_output_tokens: int = 1500,
                 response_mime_type: str | None = None,
                 min_output_chars: int | None = None) -> str:
    if not LLM_ENABLED:
        return ''

    headers = {
        "Content-Type": "application/json",
    }
    full_prompt = f"{system_prompt}\n\n{user_prompt}"
    logger.info('Gemini request start (model=%s, timeout=%ss, prompt_chars=%s)',
                GEMINI_MODEL, GEMINI_TIMEOUT, len(full_prompt))

    generation_config = {
        "temperature": temperature,
        "maxOutputTokens": max_output_tokens,
    }
    if response_mime_type:
        generation_config["responseMimeType"] = response_mime_type

    payload = {
        "systemInstruction": {
            "role": "system",
            "parts": [{"text": system_prompt}],
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": user_prompt}]
            }
        ],
        "generationConfig": generation_config,
        "safetySettings": [
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ],
    }

    last_error = None
    if min_output_chars is None:
        min_output_chars = GEMINI_MIN_JSON_CHARS

    candidates = _candidate_models()
    if candidates:
        logger.info('Gemini candidates: %s', ', '.join(candidates))
    best_text = ''
    best_model = None

    for model in candidates:
        logger.info('Gemini attempt model=%s', model)
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={GEMINI_API_KEY}"
        )
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=GEMINI_TIMEOUT)
            if response.ok:
                data = response.json()
                cand = data.get('candidates', [{}])[0]
                parts = cand.get('content', {}).get('parts', [])
                finish = cand.get('finishReason')
                if finish:
                    logger.info('Gemini finishReason=%s', finish)
                if not parts:
                    logger.warning('Gemini returned no parts. Candidate=%s', str(cand)[:200])
                text = ''.join(part.get('text', '') for part in parts)
                if len(text) > len(best_text):
                    best_text = text
                    best_model = model
                global _LAST_WORKING_MODEL
                # If output is too short (likely truncated), try next model
                if finish == "MAX_TOKENS" and len(text) < min_output_chars:
                    logger.warning('Gemini output too short (%s chars) on model=%s, trying next.',
                                   len(text), model)
                    last_error = f"short_output_{len(text)}"
                    continue
                _LAST_WORKING_MODEL = model
                logger.info('Gemini response ok (chars=%s, model=%s)', len(text), model)
                return text

            # 404: model not supported, try next
            if response.status_code == 404:
                last_error = f"{response.status_code} {response.text}"
                logger.warning('Gemini model not found: %s', model)
                continue

            # Non-404 errors are fatal
            raise RuntimeError(f"Gemini error: {response.status_code} {response.text}")
        except Exception as exc:
            last_error = str(exc)
            continue

    if best_text:
        logger.warning('Gemini returning short output from model=%s (%s chars)', best_model, len(best_text))
        if best_model:
            _LAST_WORKING_MODEL = best_model
        return best_text

    raise RuntimeError(f"Gemini error: {last_error or 'no supported model found'}")


# ---------------------------------------------------------------------------
# Category matching (JD → 6 key categories, match vs CV)
# ---------------------------------------------------------------------------

def extract_category_match(cv_text: str, jd_text: str) -> dict:
    """Ask Gemini for top 6 key categories and match vs CV.

    Returns dict with key_categories, matched_categories, missing_categories,
    bonus_categories, and optional skill_groups.
    """
    if not LLM_ENABLED:
        logger.info('Gemini disabled (no GEMINI_API_KEY)')
        return {}

    cv_truncated = cv_text[:4000]
    jd_truncated = jd_text[:2500]

    user_prompt = f"""JOB DESCRIPTION:
\"\"\"
{jd_truncated}
\"\"\"

RESUME:
\"\"\"
{cv_truncated}
\"\"\"

Return ONLY valid JSON with this schema:
{CATEGORY_MATCH_SCHEMA}

Rules:
- key_categories must be EXACTLY 6 categories from the JD
- matched_categories and missing_categories must be subsets of key_categories
- bonus_categories are relevant to the JD but NOT in key_categories
- Each category should be 1–4 words, title case
- skill_groups should include the same 6 categories (2–5 skills each)
- Return ONLY valid JSON
"""

    try:
        raw = _call_gemini(
            SYSTEM_PROMPT,
            user_prompt,
            temperature=0.2,
            max_output_tokens=800,
            response_mime_type="application/json",
            min_output_chars=0,
        )
        parsed = _safe_json_parse(raw) or {}
        return parsed
    except Exception as exc:
        logger.warning('Gemini category match failed: %s', exc)
        return {}


# ---------------------------------------------------------------------------
# Top skills extraction (grouped) — optional for UI
# ---------------------------------------------------------------------------

def extract_jd_top_skills(jd_text: str) -> list[dict]:
    if not LLM_ENABLED:
        logger.info('Gemini disabled (no GEMINI_API_KEY)')
        return []

    jd_truncated = jd_text[:2000]
    prompt = f"""Analyze this job description and identify the TOP 6 skill CATEGORIES a recruiter would screen for.
Group related skills together.

JOB DESCRIPTION:
\"\"\"
{jd_truncated}
\"\"\"

Return JSON with this exact structure:
{SKILL_GROUPS_SCHEMA}

Rules:
- Return exactly 6 skill groups
- Each group must have 2-5 specific skills
- Group related skills together (languages, cloud, databases, frameworks, soft skills, etc.)
- Return ONLY valid JSON
"""

    try:
        raw = _call_gemini(
            SYSTEM_PROMPT,
            prompt,
            temperature=0.2,
            max_output_tokens=700,
            response_mime_type="application/json",
            min_output_chars=0,
        )
        data = _safe_json_parse(raw) or {}
        groups = data.get('skill_groups', [])
        validated = []
        for g in groups[:6]:
            if isinstance(g, dict) and g.get('category') and isinstance(g.get('skills'), list):
                skills = [s for s in g['skills'] if isinstance(s, str) and s.strip()][:5]
                if skills:
                    validated.append({
                        'category': g['category'],
                        'skills': skills,
                        'importance': g.get('importance', 'Must-have'),
                    })
        return validated
    except Exception as exc:
        logger.warning('Gemini JD skill extraction failed: %s', exc)
        return []


# ---------------------------------------------------------------------------
# Full LLM analysis (LLM-only mode)
# ---------------------------------------------------------------------------

def generate_full_llm_analysis(cv_text: str, jd_text: str) -> dict:
    if not LLM_ENABLED:
        logger.info('Gemini disabled (no GEMINI_API_KEY)')
        return {}

    meta = {
        'enabled': True,
        'model': GEMINI_MODEL,
        'status': 'pending',
    }

    cv_truncated = cv_text[:3200]
    jd_truncated = jd_text[:2200]

    prompt = f"""You are a recruiter. Analyze the CV against the JD and fill ALL fields in the JSON schema.
Rules:
- Use ONLY the provided CV + JD
- If information is missing, use \"Not specified\"
- key_categories must be EXACTLY 6 categories from the JD
- matched_categories and missing_categories must be subsets of key_categories
- bonus_categories are relevant to the JD but NOT in key_categories
- skill_groups must contain the same 6 categories; include 2–5 skills each with found=true/false
- scores are 0–100 numbers
- keywords.jd and keywords.cv should each have 8–12 items
- Return ONLY JSON (no markdown, no commentary)

JOB DESCRIPTION:
\"\"\"
{jd_truncated}
\"\"\"

RESUME:
\"\"\"
{cv_truncated}
\"\"\"

Schema:
{FULL_ANALYSIS_SCHEMA}
"""

    try:
        raw = _call_gemini(
            SYSTEM_PROMPT,
            prompt,
            temperature=0.1,
            max_output_tokens=1400,
            response_mime_type="application/json",
        )
        parsed = _safe_json_parse(raw) or {}
        if not isinstance(parsed, dict) or not parsed:
            retry_prompt = prompt + "\n\nSTRICT: Return ONLY raw JSON starting with { and ending with }."
            raw_retry = _call_gemini(
                SYSTEM_PROMPT,
                retry_prompt,
                temperature=0.0,
                max_output_tokens=1400,
                response_mime_type="application/json",
            )
            parsed = _safe_json_parse(raw_retry) or {}

        if not isinstance(parsed, dict) or not parsed:
            meta['status'] = 'empty'
            meta['error'] = 'No JSON parsed from Gemini response'
            return {'_meta': meta}

        meta['status'] = 'ok'
        parsed['_meta'] = meta
        return parsed
    except Exception as exc:
        logger.warning('Gemini full analysis failed: %s', exc)
        meta['status'] = 'error'
        meta['error'] = str(exc)[:200]
        return {'_meta': meta}


# ---------------------------------------------------------------------------
# Single-call bundle (categories + recruiter insights)
# ---------------------------------------------------------------------------

def generate_llm_bundle(cv_text: str, jd_text: str) -> dict:
    if not LLM_ENABLED:
        logger.info('Gemini disabled (no GEMINI_API_KEY)')
        return {}

    meta = {
        'enabled': True,
        'model': GEMINI_MODEL,
        'status': 'pending',
    }

    cv_truncated = cv_text[:3500]
    jd_truncated = jd_text[:2200]

    prompt = f"""Analyze the CV against the JD and return BOTH:
1) Top 6 skill categories with matches/missing/bonus, and skill groups
2) Recruiter-style insights + actionable suggestions

JOB DESCRIPTION:
\"\"\"
{jd_truncated}
\"\"\"

RESUME:
\"\"\"
{cv_truncated}
\"\"\"

Return ONLY valid JSON with this schema:
{COMBINED_SCHEMA}

Rules:
- key_categories must be EXACTLY 6 categories from the JD
- matched_categories and missing_categories must be subsets of key_categories
- bonus_categories are relevant to the JD but NOT in key_categories
- Each category should be 1–4 words, title case
- skill_groups should include the same 6 categories (2–5 skills each)
- enhanced_suggestions should be 3-5 items
- Return ONLY valid JSON
"""

    try:
        raw = _call_gemini(
            SYSTEM_PROMPT,
            prompt,
            temperature=0.2,
            max_output_tokens=1200,
            response_mime_type="application/json",
        )
        parsed = _safe_json_parse(raw) or {}
        if not isinstance(parsed, dict) or not parsed:
            # Retry once with stricter instruction and lower temperature
            retry_prompt = prompt + "\n\nSTRICT RULE: Return ONLY raw JSON. Start with { and end with }."
            raw_retry = _call_gemini(
                SYSTEM_PROMPT,
                retry_prompt,
                temperature=0.0,
                max_output_tokens=1200,
                response_mime_type="application/json",
            )
            parsed = _safe_json_parse(raw_retry) or {}

        if not isinstance(parsed, dict) or not parsed:
            meta['status'] = 'empty'
            meta['error'] = 'No JSON parsed from Gemini response'
            return {'_meta': meta}

        has_category = isinstance(parsed.get('category_match'), dict) and bool(parsed.get('category_match'))
        has_insights = isinstance(parsed.get('insights'), dict) and bool(parsed.get('insights'))

        if has_category and has_insights:
            meta['status'] = 'ok'
        else:
            meta['status'] = 'partial'
            meta['details'] = f"category={has_category}, insights={has_insights}"

        parsed['_meta'] = meta
        return parsed
    except Exception as exc:
        logger.warning('Gemini bundle failed: %s', exc)
        meta['status'] = 'error'
        meta['error'] = str(exc)[:200]
        return {'_meta': meta}


# ---------------------------------------------------------------------------
# Recruiter insights (LLM suggestions, ATS score, etc.)
# ---------------------------------------------------------------------------

def generate_llm_scores_quickmatch(cv_text: str, jd_text: str) -> dict:
    if not LLM_ENABLED:
        logger.info('Gemini disabled (no GEMINI_API_KEY)')
        return {}

    meta = {'enabled': True, 'model': GEMINI_MODEL, 'status': 'pending'}
    cv_truncated = cv_text[:1600]
    jd_truncated = jd_text[:1300]

    prompt = f"""Return ONLY JSON. Use ALL keys exactly as shown.
JSON:
{SCORES_SCHEMA}

Rules:
- scores are 0-100 integers
- match_quality must be one of: Strong Match, Good Match, Weak Match, Not a Match
- keywords.jd and keywords.cv must each have 5-8 short items
- Keep all strings short (<=8 words)
- If missing, use "Not specified" or empty list

JOB DESCRIPTION:
\"\"\"
{jd_truncated}
\"\"\"

RESUME:
\"\"\"
{cv_truncated}
\"\"\"
"""

    try:
        raw = _call_gemini(
            SYSTEM_PROMPT,
            prompt,
            temperature=0.1,
            max_output_tokens=600,
            response_mime_type="application/json",
            min_output_chars=0,
        )
        parsed = _safe_json_parse(raw) or {}
        if not _validate_scores_quickmatch(parsed):
            parsed = _repair_json(raw, SCORES_SCHEMA, max_output_tokens=450) or {}

        parsed = _coerce_scores_quickmatch(parsed)

        # If still empty/missing, retry with minimal schema (no keywords)
        missing_all = all(v.get("cv_value") == "Not specified" for v in parsed["quick_match"].values())
        if parsed["scores"]["ats"] == 0 and missing_all:
            min_prompt = f"""Return ONLY JSON. Use ALL keys exactly as shown.
JSON:
{SCORES_MIN_SCHEMA}

Rules:
- scores are 0-100 integers
- match_quality must be one of: Strong Match, Good Match, Weak Match, Not a Match
- If missing, use "Not specified"

JOB DESCRIPTION:
\"\"\"
{jd_truncated}
\"\"\"

RESUME:
\"\"\"
{cv_truncated}
\"\"\"
"""
            raw_min = _call_gemini(
                SYSTEM_PROMPT,
                min_prompt,
                temperature=0.1,
                max_output_tokens=450,
                response_mime_type="application/json",
                min_output_chars=0,
            )
            parsed_min = _safe_json_parse(raw_min) or {}
            if not isinstance(parsed_min, dict) or not parsed_min:
                parsed_min = _repair_json(raw_min, SCORES_MIN_SCHEMA, max_output_tokens=350) or {}
            parsed_min = _coerce_scores_quickmatch(parsed_min)
            parsed_min["keywords"] = parsed.get("keywords", {"jd": [], "cv": []})
            parsed = parsed_min

        missing_all = all(v.get("cv_value") == "Not specified" for v in parsed["quick_match"].values())

        # Final fallback: ask for scores only, then quick_match only
        if parsed["scores"]["ats"] == 0 and missing_all:
            scores_only = _call_gemini(
                SYSTEM_PROMPT,
                f"""Return ONLY JSON:
{{"ats":0,"text_similarity":0,"skill_match":0,"verb_alignment":0}}

Rules:
- integers 0-100
- use best estimate from CV + JD

JOB DESCRIPTION:
\"\"\"
{jd_truncated}
\"\"\"

RESUME:
\"\"\"
{cv_truncated}
\"\"\"
""",
                temperature=0.1,
                max_output_tokens=200,
                response_mime_type=None,
                min_output_chars=0,
            )
            scores_only_parsed = _safe_json_parse(scores_only) or {}
            if isinstance(scores_only_parsed, dict):
                parsed["scores"]["ats"] = int(scores_only_parsed.get("ats", 0) or 0)
                parsed["scores"]["text_similarity"] = int(scores_only_parsed.get("text_similarity", 0) or 0)
                parsed["scores"]["skill_match"] = int(scores_only_parsed.get("skill_match", 0) or 0)
                parsed["scores"]["verb_alignment"] = int(scores_only_parsed.get("verb_alignment", 0) or 0)

            quick_match_only = _call_gemini(
                SYSTEM_PROMPT,
                f"""Return ONLY JSON:
{{"experience":{{"cv_value":"","jd_value":"","match_quality":""}},
 "education":{{"cv_value":"","jd_value":"","match_quality":""}},
 "skills":{{"cv_value":"","jd_value":"","match_quality":""}},
 "location":{{"cv_value":"","jd_value":"","match_quality":""}}}}

Rules:
- match_quality must be one of: Strong Match, Good Match, Weak Match, Not a Match
- if missing, use "Not specified"

JOB DESCRIPTION:
\"\"\"
{jd_truncated}
\"\"\"

RESUME:
\"\"\"
{cv_truncated}
\"\"\"
""",
                temperature=0.1,
                max_output_tokens=300,
                response_mime_type=None,
                min_output_chars=0,
            )
            qm_parsed = _safe_json_parse(quick_match_only) or {}
            if isinstance(qm_parsed, dict):
                parsed["quick_match"] = _coerce_scores_quickmatch({"quick_match": qm_parsed}).get("quick_match", parsed["quick_match"])
                missing_all = all(v.get("cv_value") == "Not specified" for v in parsed["quick_match"].values())

        # If we got here, we have a structured payload
        meta['status'] = 'ok' if parsed["scores"]["ats"] or not missing_all else 'partial'
        parsed['_meta'] = meta
        return parsed
    except Exception as exc:
        logger.warning('Gemini scores/quick-match failed: %s', exc)
        meta['status'] = 'error'
        meta['error'] = str(exc)[:200]
        return {'_meta': meta}


def generate_llm_categories(cv_text: str, jd_text: str) -> dict:
    if not LLM_ENABLED:
        logger.info('Gemini disabled (no GEMINI_API_KEY)')
        return {}

    meta = {'enabled': True, 'model': GEMINI_MODEL, 'status': 'pending'}
    cv_truncated = cv_text[:2000]
    jd_truncated = jd_text[:1700]

    prompt = f"""Return ONLY JSON. Use ALL keys exactly as shown.
JSON:
{CATEGORIES_SCHEMA}

Rules:
- key_categories must be EXACTLY 6 categories from the JD
- matched_categories and missing_categories must be subsets of key_categories
- bonus_categories are relevant to the JD but NOT in key_categories
- Each category 1–3 words, title case
- If unsure, still return 6 categories and best-effort matches

JOB DESCRIPTION:
\"\"\"
{jd_truncated}
\"\"\"

RESUME:
\"\"\"
{cv_truncated}
\"\"\"
"""

    try:
        raw = _call_gemini(
            SYSTEM_PROMPT,
            prompt,
            temperature=0.2,
            max_output_tokens=600,
            response_mime_type="application/json",
            min_output_chars=0,
        )
        parsed = _safe_json_parse(raw) or {}
        if not _validate_categories(parsed):
            parsed = _repair_json(raw, CATEGORIES_SCHEMA, max_output_tokens=500) or {}

        if not _validate_categories(parsed):
            # Fallback: get 6 categories as a simple list, then matched/missing
            try:
                cats_text = _call_gemini(
                    SYSTEM_PROMPT,
                    f"""Return EXACTLY 6 skill categories from this JD.
Format: Category 1 | Category 2 | Category 3 | Category 4 | Category 5 | Category 6
No other text.

JOB DESCRIPTION:
\"\"\"
{jd_truncated}
\"\"\"
""",
                    temperature=0.1,
                    max_output_tokens=120,
                    response_mime_type=None,
                    min_output_chars=0,
                )
                key_categories = _split_items(cats_text, 6)
                if len(key_categories) < 6:
                    # Pad with generic categories to avoid empty UI
                    pads = ["General Skills", "Domain Knowledge", "Tools", "Soft Skills", "Process", "Leadership"]
                    for p in pads:
                        if len(key_categories) >= 6:
                            break
                        if p not in key_categories:
                            key_categories.append(p)

                match_text = _call_gemini(
                    SYSTEM_PROMPT,
                    f"""Given these categories:
{', '.join(key_categories)}

Return ONLY:
MATCHED: a | b | c
MISSING: x | y | z

Use only categories from the list.

JOB DESCRIPTION:
\"\"\"
{jd_truncated}
\"\"\"

RESUME:
\"\"\"
{cv_truncated}
\"\"\"
""",
                    temperature=0.1,
                    max_output_tokens=120,
                    response_mime_type=None,
                    min_output_chars=0,
                )
                matched = []
                missing = []
                for line in match_text.splitlines():
                    if line.upper().startswith("MATCHED"):
                        matched = _split_items(line.split(":", 1)[-1], 6)
                    if line.upper().startswith("MISSING"):
                        missing = _split_items(line.split(":", 1)[-1], 6)

                # If LLM failed, do a simple string fallback
                if not matched and not missing:
                    cv_lower = cv_text.lower()
                    matched = [c for c in key_categories if c.lower() in cv_lower]
                    missing = [c for c in key_categories if c not in matched]

                bonus_text = _call_gemini(
                    SYSTEM_PROMPT,
                    f"""Return up to 3 BONUS categories (not in the list) relevant to the JD.
Format: Bonus1 | Bonus2 | Bonus3
If none, return NONE.

Categories: {', '.join(key_categories)}

JOB DESCRIPTION:
\"\"\"
{jd_truncated}
\"\"\"
""",
                    temperature=0.2,
                    max_output_tokens=80,
                    response_mime_type=None,
                    min_output_chars=0,
                )
                bonus = _split_items(bonus_text, 3)

                parsed = {
                    "key_categories": key_categories[:6],
                    "matched_categories": matched,
                    "missing_categories": missing,
                    "bonus_categories": bonus,
                }
            except Exception:
                parsed = {}

        if not _validate_categories(parsed):
            meta['status'] = 'empty'
            meta['error'] = 'No JSON parsed from Gemini response'
            return {'_meta': meta}

        meta['status'] = 'ok'
        parsed['_meta'] = meta
        return parsed
    except Exception as exc:
        logger.warning('Gemini categories failed: %s', exc)
        meta['status'] = 'error'
        meta['error'] = str(exc)[:200]
        return {'_meta': meta}

def generate_llm_skill_groups(cv_text: str, jd_text: str, key_categories: list[str]) -> dict:
    if not LLM_ENABLED:
        logger.info('Gemini disabled (no GEMINI_API_KEY)')
        return {}

    if not key_categories:
        return {}

    meta = {'enabled': True, 'model': GEMINI_MODEL, 'status': 'pending'}
    cv_truncated = cv_text[:1800]
    jd_truncated = jd_text[:1600]
    categories_csv = ", ".join(key_categories[:6])

    prompt = f"""Return ONLY JSON. Use ALL keys exactly as shown.
JSON:
{SKILL_GROUPS_MIN_SCHEMA}

Rules:
- Use ONLY these categories: {categories_csv}
- Return exactly 6 groups (one per category)
- For each category, list 2-3 concrete skills from the JD
- Set found=true only if the CV explicitly mentions the skill
- Keep skill names 1–3 words
- importance: Must-have if the JD implies required, else Nice-to-have

JOB DESCRIPTION:
\"\"\"
{jd_truncated}
\"\"\"

RESUME:
\"\"\"
{cv_truncated}
\"\"\"
"""

    try:
        raw = _call_gemini(
            SYSTEM_PROMPT,
            prompt,
            temperature=0.2,
            max_output_tokens=700,
            response_mime_type="application/json",
            min_output_chars=0,
        )
        parsed = _safe_json_parse(raw) or {}
        if not _validate_skill_groups(parsed, key_categories):
            parsed = _repair_json(raw, SKILL_GROUPS_MIN_SCHEMA, max_output_tokens=500) or {}

        if not _validate_skill_groups(parsed, key_categories):
            meta['status'] = 'empty'
            meta['error'] = 'No JSON parsed from Gemini response'
            return {'_meta': meta}

        meta['status'] = 'ok'
        parsed['_meta'] = meta
        return parsed
    except Exception as exc:
        logger.warning('Gemini skill groups failed: %s', exc)
        meta['status'] = 'error'
        meta['error'] = str(exc)[:200]
        return {'_meta': meta}

def _build_recruiter_prompt(cv_text: str, jd_text: str, analysis_summary: dict) -> str:
    cv_truncated = cv_text[:2500]
    jd_truncated = jd_text[:1500]

    matched = ', '.join(analysis_summary.get('matched_skills', [])[:15]) or 'None identified'
    missing = ', '.join(analysis_summary.get('missing_skills', [])[:15]) or 'None identified'
    missing_verbs = ', '.join(analysis_summary.get('missing_verbs', [])[:10]) or 'None'

    score = analysis_summary.get('composite_score', 0)
    exp = analysis_summary.get('experience', {})
    edu = analysis_summary.get('education', {})

    if score >= 70:
        verdict = "STRONG CANDIDATE — likely gets past screening"
    elif score >= 50:
        verdict = "BORDERLINE — needs improvements to stand out"
    elif score >= 30:
        verdict = "BELOW THRESHOLD — significant gaps to address"
    else:
        verdict = "POOR FIT — major rework or different role recommended"

    return f"""Evaluate this candidate as a recruiter making a hiring recommendation.

Overall Match: {score:.0f}% — {verdict}
Skill Coverage: {analysis_summary.get('skill_score', 0):.0f}%
Verb Alignment: {analysis_summary.get('verb_alignment', 0):.0f}%
Matched Skills: {matched}
Missing Skills: {missing}
Experience: CV shows "{exp.get('cv_value', 'Not specified')}", role requires "{exp.get('jd_value', 'Not specified')}" — {exp.get('match_quality', 'Unknown')}
Education: CV shows "{edu.get('cv_value', 'Not specified')}", role requires "{edu.get('jd_value', 'Not specified')}" — {edu.get('match_quality', 'Unknown')}
Missing Action Verbs: {missing_verbs}

Job Description:\n{jd_truncated}\n\nCandidate CV:\n{cv_truncated}

Return JSON:
{RECRUITER_SCHEMA}

Rules:
- Provide 3-5 enhanced_suggestions ranked by impact
- working_well and needs_improvement should be 3-5 items each
- ats_score must be 0-100
- Return ONLY valid JSON
"""


def generate_llm_insights(cv_text: str, jd_text: str, results: dict | None) -> dict:
    if not LLM_ENABLED:
        logger.info('Gemini disabled (no GEMINI_API_KEY)')
        return {}

    try:
        results = results or {}
        analysis_summary = {
            'composite_score': results.get('composite_score', 0),
            'matched_skills': results.get('skill_match', {}).get('matched', []),
            'missing_skills': results.get('skill_match', {}).get('missing', []),
            'skill_score': results.get('skill_match', {}).get('skill_score', 0),
            'experience': results.get('quick_match', {}).get('experience', {}),
            'education': results.get('quick_match', {}).get('education', {}),
            'verb_alignment': results.get('experience_analysis', {}).get('verb_alignment', 0),
            'missing_verbs': results.get('experience_analysis', {}).get('missing_action_verbs', []),
        }

        # Shorter, JSON-only prompt for reliability
        cv_truncated = cv_text[:1600]
        jd_truncated = jd_text[:1200]
        prompt = f"""Return ONLY JSON. Use ALL keys exactly as shown.
JSON:
{INSIGHTS_SCHEMA}

Rules:
- profile_summary: 2-3 short sentences
- working_well: 2-3 items
- needs_improvement: 2-3 items
- enhanced_suggestions: 2-3 items; title <= 6 words; body <= 20 words; examples 1-2 items
- skill_gap_tips: 2-3 items
- Keep all text concise

JOB DESCRIPTION:
\"\"\"
{jd_truncated}
\"\"\"

RESUME:
\"\"\"
{cv_truncated}
\"\"\"
"""
        logger.info('Calling Gemini insights (prompt: %d chars, model: %s)', len(prompt), GEMINI_MODEL)
        raw = _call_gemini(
            SYSTEM_PROMPT,
            prompt,
            temperature=0.2,
            max_output_tokens=700,
            response_mime_type="application/json",
            min_output_chars=0,
        )
        llm_data = _safe_json_parse(raw) or {}
        if not _validate_insights(llm_data):
            llm_data = _repair_json(raw, INSIGHTS_SCHEMA, max_output_tokens=500) or {}

        if not _validate_insights(llm_data):
            return {}

        validated: dict = {}
        if isinstance(llm_data.get('profile_summary'), str):
            validated['profile_summary'] = llm_data['profile_summary']
        if isinstance(llm_data.get('quick_match_insights'), dict):
            validated['quick_match_insights'] = llm_data['quick_match_insights']
        if isinstance(llm_data.get('enhanced_suggestions'), list):
            validated['enhanced_suggestions'] = llm_data['enhanced_suggestions']
        if isinstance(llm_data.get('working_well'), list):
            validated['working_well'] = llm_data['working_well']
        if isinstance(llm_data.get('needs_improvement'), list):
            validated['needs_improvement'] = llm_data['needs_improvement']
        if isinstance(llm_data.get('ats_score'), (int, float)):
            validated['ats_score'] = min(100, max(0, int(llm_data['ats_score'])))
        if isinstance(llm_data.get('skill_gap_tips'), dict):
            validated['skill_gap_tips'] = llm_data['skill_gap_tips']

        logger.info('Gemini insights ready: %s', list(validated.keys()))
        return validated

    except Exception as exc:
        logger.warning('Gemini insights generation failed: %s', exc)
        return {}


def merge_suggestions(base_suggestions: list, llm_suggestions: list):
    if not llm_suggestions:
        return

    llm_titles = {s.get('title', '').lower().strip() for s in llm_suggestions if isinstance(s, dict)}

    retained_nlp = []
    for base in base_suggestions:
        base_title = base.get('title', '').lower().strip()
        covered = any(base_title in lt or lt in base_title for lt in llm_titles)
        if not covered and base.get('type') in ('missing_skills', 'missing_verbs'):
            base['priority'] = 'low'
            retained_nlp.append(base)

    base_suggestions.clear()
    for s in llm_suggestions:
        if isinstance(s, dict) and s.get('title'):
            base_suggestions.append({
                'type': 'recruiter_insight',
                'title': s.get('title', ''),
                'body': s.get('body', ''),
                'examples': s.get('examples', []),
                'priority': 'high' if len(base_suggestions) < 2 else 'medium',
            })
    base_suggestions.extend(retained_nlp)
