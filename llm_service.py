"""Gemini-powered recruiter insights for CV analysis.

This module replaces Groq with Google's Gemini API (free tier).
Graceful degradation:
- If GEMINI_API_KEY is not set, functions return empty/heuristic results.
- If the API call fails, the app continues with NLP-only analysis.
"""

import json
import logging
import os

import requests

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-1.5-flash')
LLM_ENABLED = bool(GEMINI_API_KEY)

SYSTEM_PROMPT = """You are a senior technical recruiter with 15+ years of hiring experience at top-tier companies.
You evaluate candidates the way a real hiring manager would — direct, specific, and focused on what actually moves the needle in a hiring decision.

Your evaluation style:
- Speak like a recruiter in a debrief meeting: confident, specific, no fluff
- Flag real red flags and genuine strengths — not vague platitudes
- Think about ATS compatibility, hiring manager first impressions, and interview readiness
- Give honest advice that can be acted on TODAY
- Reference specific things from their CV, not generic templates
- Address the candidate directly using "you/your"

GUARDRAILS:
1. NEVER fabricate skills or experience
2. NEVER suggest lying
3. Base feedback on actual CV content + JD requirements
4. Focus on presentation improvements
5. If skills are missing, suggest learning paths
6. Return ONLY valid JSON with no markdown
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


def _safe_json_parse(text: str):
    try:
        return json.loads(text)
    except Exception:
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except Exception:
                return None
        return None


def _call_gemini(system_prompt: str, user_prompt: str,
                 temperature: float = 0.2, max_output_tokens: int = 1500) -> str:
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

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": full_prompt}]
            }
        ],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_output_tokens
        }
    }

    response = requests.post(url, headers=headers, json=payload, timeout=20)
    if not response.ok:
        raise RuntimeError(f"Gemini error: {response.status_code} {response.text}")

    data = response.json()
    parts = data.get('candidates', [{}])[0].get('content', {}).get('parts', [])
    return ''.join(part.get('text', '') for part in parts)


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

    user_prompt = f"""JOB DESCRIPTION:
\"\"\"
{jd_text}
\"\"\"

RESUME:
\"\"\"
{cv_text}
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
        raw = _call_gemini(SYSTEM_PROMPT, user_prompt, temperature=0.2, max_output_tokens=1200)
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
        raw = _call_gemini(SYSTEM_PROMPT, prompt, temperature=0.2, max_output_tokens=900)
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
# Recruiter insights (LLM suggestions, ATS score, etc.)
# ---------------------------------------------------------------------------

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


def generate_llm_insights(cv_text: str, jd_text: str, results: dict) -> dict:
    if not LLM_ENABLED:
        logger.info('Gemini disabled (no GEMINI_API_KEY)')
        return {}

    try:
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

        prompt = _build_recruiter_prompt(cv_text, jd_text, analysis_summary)
        logger.info('Calling Gemini (prompt: %d chars, model: %s)', len(prompt), GEMINI_MODEL)
        raw = _call_gemini(SYSTEM_PROMPT, prompt, temperature=0.4, max_output_tokens=2000)
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
