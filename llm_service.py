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

import requests

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-1.5-pro')
GEMINI_TIMEOUT = int(os.environ.get('GEMINI_TIMEOUT', '45'))
LLM_ENABLED = bool(GEMINI_API_KEY)

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


def _call_gemini(system_prompt: str, user_prompt: str,
                 temperature: float = 0.2, max_output_tokens: int = 1500,
                 response_mime_type: str | None = None) -> str:
    if not LLM_ENABLED:
        return ''

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )
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

    response = requests.post(url, headers=headers, json=payload, timeout=GEMINI_TIMEOUT)
    if not response.ok:
        raise RuntimeError(f"Gemini error: {response.status_code} {response.text}")

    data = response.json()
    cand = data.get('candidates', [{}])[0]
    parts = cand.get('content', {}).get('parts', [])
    finish = cand.get('finishReason')
    if finish:
        logger.info('Gemini finishReason=%s', finish)
    if not parts:
        logger.warning('Gemini returned no parts. Candidate=%s', str(cand)[:200])
    text = ''.join(part.get('text', '') for part in parts)
    logger.info('Gemini response ok (chars=%s)', len(text))
    return text


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
    cv_truncated = cv_text[:1800]
    jd_truncated = jd_text[:1500]

    prompt = f"""Return ONLY JSON with this schema:
{{
  "scores": {{
    "ats": 0,
    "text_similarity": 0,
    "skill_match": 0,
    "verb_alignment": 0
  }},
  "quick_match": {{
    "experience": {{"cv_value": "...", "jd_value": "...", "match_quality": "Strong Match|Good Match|Weak Match|Not a Match"}},
    "education": {{"cv_value": "...", "jd_value": "...", "match_quality": "Strong Match|Good Match|Weak Match|Not a Match"}},
    "skills": {{"cv_value": "...", "jd_value": "...", "match_quality": "Strong Match|Good Match|Weak Match|Not a Match"}},
    "location": {{"cv_value": "...", "jd_value": "...", "match_quality": "Strong Match|Good Match|Weak Match|Not a Match"}}
  }},
  "keywords": {{
    "jd": ["keyword1", "keyword2"],
    "cv": ["keyword1", "keyword2"]
  }}
}}

Rules:
- scores are 0-100 numbers
- If a value is missing in CV or JD, use "Not specified"
- keywords.jd and keywords.cv should each have 8-12 items
- Return ONLY JSON

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
            max_output_tokens=700,
            response_mime_type="application/json",
        )
        parsed = _safe_json_parse(raw) or {}
        if not isinstance(parsed, dict) or not parsed:
            meta['status'] = 'empty'
            meta['error'] = 'No JSON parsed from Gemini response'
            return {'_meta': meta}
        meta['status'] = 'ok'
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

    prompt = f"""Return ONLY JSON with this schema:
{{
  "key_categories": ["Category 1", "Category 2", "Category 3", "Category 4", "Category 5", "Category 6"],
  "matched_categories": ["Category 1"],
  "missing_categories": ["Category 2"],
  "bonus_categories": ["Bonus Category"],
  "skill_groups": [
    {{
      "category": "Category 1",
      "importance": "Must-have|Nice-to-have",
      "skills": [
        {{"name": "Skill A", "found": true}},
        {{"name": "Skill B", "found": false}}
      ]
    }}
  ]
}}

Rules:
- key_categories must be EXACTLY 6 categories from the JD
- matched_categories and missing_categories must be subsets of key_categories
- bonus_categories are relevant to the JD but NOT in key_categories
- Each category should be 1–4 words, title case
- skill_groups must include the same 6 categories with 2–5 skills each
- "found" must reflect whether the CV mentions that skill
- Return ONLY JSON

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
            max_output_tokens=900,
            response_mime_type="application/json",
        )
        parsed = _safe_json_parse(raw) or {}
        if not isinstance(parsed, dict) or not parsed:
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
        cv_truncated = cv_text[:1800]
        jd_truncated = jd_text[:1400]
        prompt = f"""Return ONLY JSON with this schema:
{{
  "profile_summary": "3-5 sentences",
  "working_well": ["..."],
  "needs_improvement": ["..."],
  "skill_gap_tips": {{"Skill": "Tip"}},
  "enhanced_suggestions": [
    {{"title": "...", "body": "...", "examples": ["Example 1", "Example 2"]}}
  ]
}}

Rules:
- working_well and needs_improvement: 3-5 items each
- enhanced_suggestions: 3-5 items
- Return ONLY JSON

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
            max_output_tokens=900,
            response_mime_type="application/json",
        )
        llm_data = _safe_json_parse(raw) or {}

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
