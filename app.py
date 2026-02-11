import json
import logging
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime
import difflib

from dotenv import load_dotenv
load_dotenv()  # Load .env file (Gemini + Firebase keys)

import requests as http_requests
from bs4 import BeautifulSoup
from flask import (Flask, flash, jsonify, redirect, render_template, request,
                   send_file, url_for)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename
from markupsafe import Markup, escape

from analyzer import analyze_cv_against_jd
from firebase_admin import firestore
from firebase_admin_init import get_firebase
from llm_service import rewrite_cv_bullets

import stripe

# Configure logging for debugging on Render
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
# Trust Railway's reverse proxy headers so url_for() generates https:// URLs
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))
app.config['PREFERRED_URL_SCHEME'] = 'https'
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB
app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()

# ---------------------------------------------------------------------------
# Firebase client config (for Google Sign-In on the frontend)
# ---------------------------------------------------------------------------
def _firebase_client_config() -> dict:
    return {
        'apiKey': os.environ.get('NEXT_PUBLIC_FIREBASE_API_KEY', ''),
        'authDomain': os.environ.get('NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN', ''),
        'projectId': os.environ.get('NEXT_PUBLIC_FIREBASE_PROJECT_ID', ''),
        'storageBucket': os.environ.get('NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET', ''),
        'messagingSenderId': os.environ.get('NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID', ''),
        'appId': os.environ.get('NEXT_PUBLIC_FIREBASE_APP_ID', ''),
    }


@app.context_processor
def inject_firebase_config():
    config = _firebase_client_config()
    enabled = all(config.values())
    return {
        'firebase_config': config,
        'firebase_enabled': enabled,
        'stripe_enabled': stripe_enabled,
    }

# Folder to store consented CVs
CV_STORAGE = os.environ.get('CV_STORAGE_PATH',
                            os.path.join(os.path.dirname(os.path.abspath(__file__)), 'collected_cvs'))
os.makedirs(CV_STORAGE, exist_ok=True)

# Admin token for accessing stored CVs (set via env var on Render)
ADMIN_TOKEN = os.environ.get('ADMIN_TOKEN', 'change-me-in-production')
FREE_CREDITS = int(os.environ.get('FREE_CREDITS', '3'))
COST_ANALYZE = int(os.environ.get('COST_ANALYZE', '2'))
COST_REWRITE = int(os.environ.get('COST_REWRITE', '0'))  # rewrite disabled for now

# Default initial credits when user first signs in
INITIAL_CREDITS = int(os.environ.get('INITIAL_CREDITS', '100'))

STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY')
STRIPE_PRICE_ID = os.environ.get('STRIPE_PRICE_ID')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')
PUBLIC_URL = os.environ.get('PUBLIC_URL') or os.environ.get('RENDER_EXTERNAL_URL') or ''

stripe_enabled = bool(STRIPE_SECRET_KEY and STRIPE_PRICE_ID)
if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

MOCK_TOPUP_CREDITS = int(os.environ.get('MOCK_TOPUP_CREDITS', '50'))

ALLOWED_EXTENSIONS = {'pdf', 'docx', 'txt'}

BROWSER_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                   'AppleWebKit/537.36 (KHTML, like Gecko) '
                   'Chrome/120.0.0.0 Safari/537.36'),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}


def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------------------------------------------------------------------------
# Session payload storage for rewrite flow
# ---------------------------------------------------------------------------

SESSION_DIR = os.path.join(tempfile.gettempdir(), 'rewrite_sessions')
os.makedirs(SESSION_DIR, exist_ok=True)


def _save_session_payload(payload: dict) -> str:
    sid = str(uuid.uuid4())
    path = os.path.join(SESSION_DIR, f'{sid}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f)
    return sid


def _load_session_payload(sid: str) -> dict | None:
    path = os.path.join(SESSION_DIR, f'{sid}.json')
    if not os.path.isfile(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def _load_all_sessions(limit: int = 200) -> list[dict]:
    sessions = []
    try:
        files = sorted(os.listdir(SESSION_DIR), reverse=True)
    except FileNotFoundError:
        return sessions
    for fname in files[:limit]:
        if not fname.endswith('.json'):
            continue
        path = os.path.join(SESSION_DIR, fname)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                data['_sid'] = fname[:-5]
                sessions.append(data)
        except Exception:
            continue
    return sessions


# ---------------------------------------------------------------------------
# Credits helpers (Firestore)
# ---------------------------------------------------------------------------

def _firestore_enabled_and_ready(firestore_db) -> bool:
    return firestore_db is not None


def _ensure_user_doc(firestore_db, user_id: str, email: str | None):
    doc_ref = firestore_db.collection('users').document(user_id)
    doc = doc_ref.get()
    credits = INITIAL_CREDITS
    if doc.exists:
        data = doc.to_dict() or {}
        credits = int(data.get('credits', credits))
    else:
        doc_ref.set({
            'email': email,
            'credits': credits,
            'createdAt': firestore.SERVER_TIMESTAMP,
        }, merge=True)
    return doc_ref, credits


def _deduct_credit(firestore_db, user_id: str, email: str | None, amount: int = 1) -> bool:
    doc_ref, credits = _ensure_user_doc(firestore_db, user_id, email)
    if credits < amount:
        return False
    doc_ref.update({
        'credits': firestore.Increment(-amount),
        'lastDebitAt': firestore.SERVER_TIMESTAMP,
    })
    return True


def _add_credit(firestore_db, user_id: str, email: str | None, amount: int = 1):
    doc_ref, _ = _ensure_user_doc(firestore_db, user_id, email)
    doc_ref.update({
        'credits': firestore.Increment(amount),
        'lastCreditAt': firestore.SERVER_TIMESTAMP,
    })


def _bearer_token() -> str:
    auth_header = request.headers.get('Authorization', '')
    if auth_header.lower().startswith('bearer '):
        return auth_header[7:].strip()
    return ''


def _estimate_tokens_from_text(*parts: str) -> int:
    chars = sum(len(p) for p in parts if isinstance(p, str))
    return int(chars / 4)  # rough heuristic


def _diff_words_html(old: str, new: str) -> tuple[Markup, Markup]:
    """Return word-level diff HTML for old and new strings."""
    # Split into tokens preserving whitespace
    def _split(text: str):
        return re.split(r'(\s+)', text or '')

    a = _split(old)
    b = _split(new)
    sm = difflib.SequenceMatcher(a=a, b=b)
    old_parts: list[str] = []
    new_parts: list[str] = []

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            old_parts.extend(escape(tok) for tok in a[i1:i2])
            new_parts.extend(escape(tok) for tok in b[j1:j2])
        elif tag == 'replace':
            old_parts.extend(f'<span class="diff-del">{escape(tok)}</span>' for tok in a[i1:i2])
            new_parts.extend(f'<span class="diff-add">{escape(tok)}</span>' for tok in b[j1:j2])
        elif tag == 'delete':
            old_parts.extend(f'<span class="diff-del">{escape(tok)}</span>' for tok in a[i1:i2])
        elif tag == 'insert':
            new_parts.extend(f'<span class="diff-add">{escape(tok)}</span>' for tok in b[j1:j2])

    return Markup(''.join(old_parts)), Markup(''.join(new_parts))


def _diff_lines_html(old: str, new: str) -> tuple[Markup, Markup]:
    """Return line-level diff HTML for old/new text."""
    a = (old or '').splitlines(keepends=True)
    b = (new or '').splitlines(keepends=True)
    sm = difflib.SequenceMatcher(a=a, b=b)
    old_parts: list[str] = []
    new_parts: list[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            old_parts.extend(escape(line) for line in a[i1:i2])
            new_parts.extend(escape(line) for line in b[j1:j2])
        elif tag == 'replace':
            old_parts.extend(f'<div class="diff-del">{escape(line)}</div>' for line in a[i1:i2])
            new_parts.extend(f'<div class="diff-add">{escape(line)}</div>' for line in b[j1:j2])
        elif tag == 'delete':
            old_parts.extend(f'<div class="diff-del">{escape(line)}</div>' for line in a[i1:i2])
        elif tag == 'insert':
            new_parts.extend(f'<div class="diff-add">{escape(line)}</div>' for line in b[j1:j2])
    return Markup(''.join(old_parts)), Markup(''.join(new_parts))


# ---------------------------------------------------------------------------
# File extraction helpers
# ---------------------------------------------------------------------------

def extract_text_from_file(filepath: str) -> str:
    ext = filepath.rsplit('.', 1)[-1].lower()
    if ext == 'pdf':
        return _extract_pdf(filepath)
    elif ext == 'docx':
        return _extract_docx(filepath)
    elif ext == 'txt':
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    raise ValueError(f'Unsupported file type: {ext}')


def _extract_pdf(filepath: str) -> str:
    import pdfplumber
    text_parts = []
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return '\n'.join(text_parts)


def _extract_docx(filepath: str) -> str:
    from docx import Document
    doc = Document(filepath)
    return '\n'.join(para.text for para in doc.paragraphs if para.text.strip())


def _text_to_pdf(text: str, output_path: str):
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font('Helvetica', size=10)
    for line in text.split('\n'):
        pdf.multi_cell(0, 5, line)
    pdf.output(output_path)


# ---------------------------------------------------------------------------
# URL extraction helpers
# ---------------------------------------------------------------------------

def _extract_from_linkedin_url(url: str) -> str:
    """Extract profile text from a public LinkedIn profile URL.

    Returns extracted text, or a string starting with 'ERROR:' if
    extraction failed with a user-friendly reason.
    """
    if 'linkedin.com/in/' not in url:
        return ''

    logger.info('LinkedIn extraction: requesting %s', url)

    try:
        resp = http_requests.get(url, headers=BROWSER_HEADERS, timeout=15,
                                 allow_redirects=True)
        logger.info('LinkedIn response: status=%s, final_url=%s, length=%d',
                     resp.status_code, resp.url, len(resp.text))
        resp.raise_for_status()
    except http_requests.exceptions.Timeout:
        logger.warning('LinkedIn extraction: request timed out')
        return 'ERROR:TIMEOUT'
    except http_requests.exceptions.ConnectionError:
        logger.warning('LinkedIn extraction: connection error')
        return 'ERROR:CONNECTION'
    except Exception as e:
        logger.warning('LinkedIn extraction: request failed: %s', e)
        return 'ERROR:REQUEST'

    # LinkedIn returns 999 to block bots/servers
    if resp.status_code == 999:
        logger.warning('LinkedIn extraction: got status 999 (bot-blocked)')
        return 'ERROR:BLOCKED'

    # If redirected to login/authwall, public profile is not available
    if 'authwall' in resp.url or '/login' in resp.url:
        logger.warning('LinkedIn extraction: redirected to authwall (%s)', resp.url)
        return 'ERROR:AUTHWALL'

    soup = BeautifulSoup(resp.text, 'html.parser')
    parts = []

    # --- Strategy 1: Name and headline from top-card (most reliable) ---
    name_el = soup.find(class_='top-card-layout__title')
    if name_el:
        parts.append(name_el.get_text(strip=True))
    headline_el = soup.find(class_='top-card-layout__headline')
    if headline_el:
        parts.append(headline_el.get_text(strip=True))

    # --- Strategy 2: Description from meta tags ---
    desc_meta = soup.find('meta', attrs={'name': 'description'})
    if desc_meta and desc_meta.get('content'):
        parts.append(desc_meta['content'])
    else:
        og_desc = soup.find('meta', property='og:description')
        if og_desc and og_desc.get('content'):
            parts.append(og_desc['content'])

    # --- Strategy 3: Profile meta: first/last name ---
    first = soup.find('meta', property='profile:first_name')
    last = soup.find('meta', property='profile:last_name')
    if first and last and not name_el:
        parts.append(f"{first.get('content', '')} {last.get('content', '')}")

    # --- Strategy 4: JSON-LD structured data ---
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string or '')
            persons = []
            if isinstance(data, dict):
                if data.get('@type') == 'Person':
                    persons.append(data)
                for item in data.get('@graph', []):
                    if isinstance(item, dict):
                        author = item.get('author', {})
                        if isinstance(author, dict) and author.get('@type') == 'Person':
                            persons.append(author)
            for person in persons:
                if person.get('jobTitle') and person['jobTitle'] not in '\n'.join(parts):
                    parts.append(person['jobTitle'])
                if person.get('description') and person['description'] not in '\n'.join(parts):
                    parts.append(person['description'])
                if person.get('worksFor'):
                    org = person['worksFor']
                    if isinstance(org, dict) and org.get('name'):
                        parts.append(f"Works at {org['name']}")
                if person.get('alumniOf'):
                    alumni = person['alumniOf']
                    if isinstance(alumni, list):
                        for school in alumni:
                            if isinstance(school, dict) and school.get('name'):
                                parts.append(f"Education: {school['name']}")
        except (json.JSONDecodeError, TypeError):
            continue

    # --- Strategy 5: Profile section cards (experience, education) ---
    for card in soup.find_all(class_='profile-section-card'):
        text = card.get_text(separator=' ', strip=True)
        if text and len(text) > 5:
            parts.append(text)

    # --- Strategy 6: Any section with role-based classes ---
    for cls in ['experience__list', 'education__list',
                'certifications__list', 'skills__list']:
        el = soup.find(class_=cls)
        if el:
            text = el.get_text(separator=' ', strip=True)
            if text and len(text) > 5:
                parts.append(text)

    # --- Strategy 7: Subline items (location, connections) ---
    for el in soup.find_all(class_='top-card__subline-item'):
        text = el.get_text(strip=True)
        if text:
            parts.append(text)

    # --- Strategy 8: Aggressive fallback — try <title> and OG title ---
    if not parts:
        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            title_text = og_title['content']
            # LinkedIn titles often contain "Name - Title - LinkedIn"
            parts.append(title_text)
        title = soup.find('title')
        if title and title.string:
            parts.append(title.string.strip())

    # --- Strategy 9: Last resort — extract all visible text from page ---
    if not parts:
        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'noscript']):
            tag.decompose()
        body_text = soup.get_text(separator='\n', strip=True)
        # Remove very short lines (likely UI elements)
        lines = [l for l in body_text.split('\n') if len(l) > 15]
        if lines:
            parts.append('\n'.join(lines[:50]))  # Cap at 50 useful lines

    extracted = '\n'.join(parts)
    logger.info('LinkedIn extraction: got %d chars from %d strategies',
                len(extracted), len(parts))

    if not extracted or len(extracted) < 30:
        logger.warning('LinkedIn extraction: insufficient content (%d chars)', len(extracted))
        return 'ERROR:BLOCKED'

    return extracted


def _extract_from_jd_url(url: str) -> str:
    """Extract job description text from a URL using trafilatura."""
    try:
        resp = http_requests.get(url, headers=BROWSER_HEADERS, timeout=15,
                                 allow_redirects=True)
        resp.raise_for_status()
    except Exception:
        return ''

    html = resp.text

    # Primary: trafilatura for clean content extraction
    try:
        import trafilatura
        text = trafilatura.extract(html, include_comments=False,
                                   include_tables=True, favor_recall=True)
        if text and len(text) > 50:
            return text
    except Exception:
        pass

    # Fallback: BeautifulSoup text extraction
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
        tag.decompose()
    text = soup.get_text(separator='\n', strip=True)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text[:10000]


# ---------------------------------------------------------------------------
# Unified input processing
# ---------------------------------------------------------------------------

def _process_input(file_field: str, text_field: str, url_field: str = None,
                   save_cv: bool = False, url_extractor=None) -> str:
    """Handle file upload, URL, or text paste. Priority: file > URL > text."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    file = request.files.get(file_field)

    # --- 1. File upload (highest priority) ---
    if file and file.filename and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        ext = filename.rsplit('.', 1)[1].lower()
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(temp_path)
        try:
            text = extract_text_from_file(temp_path)
            if save_cv:
                save_name = f'cv_{timestamp}.{ext}'
                shutil.copy2(temp_path, os.path.join(CV_STORAGE, save_name))
        finally:
            os.remove(temp_path)
        return text

    # --- 2. URL input ---
    if url_field and url_extractor:
        url = request.form.get(url_field, '').strip()
        if url:
            text = url_extractor(url)

            # Handle specific LinkedIn error codes
            if text.startswith('ERROR:'):
                error_code = text.split(':')[1]
                is_linkedin = 'linkedin.com' in url
                if error_code == 'AUTHWALL' and is_linkedin:
                    flash('LinkedIn redirected to a login page. This usually means '
                          'the profile is private or LinkedIn is blocking server '
                          'requests. Please paste your CV/profile text instead.',
                          'warning')
                elif error_code == 'BLOCKED' and is_linkedin:
                    flash('LinkedIn returned limited data (likely blocking server '
                          'requests). Please copy-paste your LinkedIn profile text '
                          'or upload your CV as a file instead.', 'warning')
                elif error_code in ('TIMEOUT', 'CONNECTION'):
                    flash('Could not connect to the URL. Please check the link '
                          'and try again, or paste text instead.', 'warning')
                else:
                    flash('Could not extract content from the URL. '
                          'Please paste text instead.', 'warning')
                return ''

            if text:
                if save_cv:
                    save_name = f'cv_{timestamp}.pdf'
                    _text_to_pdf(text, os.path.join(CV_STORAGE, save_name))
                return text
            else:
                flash('Could not extract content from the URL. Please paste text instead.', 'warning')
                return ''

    # --- 3. Pasted text (lowest priority) ---
    text = request.form.get(text_field, '').strip()
    if text and save_cv:
        save_name = f'cv_{timestamp}.pdf'
        _text_to_pdf(text, os.path.join(CV_STORAGE, save_name))
    return text


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/analyze', methods=['POST'])
def analyze():
    consent_given = request.form.get('cv_consent') == 'yes'

    id_token = request.form.get('id_token', '').strip()
    if not id_token:
        flash('Please sign in with Google to analyze.', 'error')
        return redirect(url_for('index'))

    try:
        auth_client, firestore_db = get_firebase()
        decoded = auth_client.verify_id_token(id_token)
    except Exception as e:
        logger.warning('Firebase auth failed: %s', e)
        flash('Google sign-in failed. Please sign in again.', 'error')
        return redirect(url_for('index'))

    user_id = decoded.get('uid')
    user_email = decoded.get('email')

    try:
        cv_text = _process_input(
            'cv_file', 'cv_text', url_field='cv_url',
            save_cv=consent_given, url_extractor=_extract_from_linkedin_url)
        jd_text = _process_input(
            'jd_file', 'jd_text', url_field='jd_url',
            save_cv=False, url_extractor=_extract_from_jd_url)
    except Exception as e:
        flash(f'Error reading input: {e}', 'error')
        return redirect(url_for('index'))

    if not cv_text or not jd_text:
        if not cv_text and not jd_text:
            flash('Please provide both a CV and a Job Description.', 'error')
        elif not cv_text:
            flash('Could not get CV content. Please try uploading a file or pasting text.', 'error')
        else:
            flash('Could not get JD content. Please try uploading a file or pasting text.', 'error')
        return redirect(url_for('index'))

    if len(jd_text.split()) < 10:
        flash('Job description seems very short. Results may be unreliable.', 'warning')

    charged_credit = False
    if _firestore_enabled_and_ready(firestore_db):
        charged_credit = _deduct_credit(firestore_db, user_id, user_email, amount=COST_ANALYZE)
        if not charged_credit:
            flash('You are out of credits. Buy more to run analysis.', 'error')
            return redirect(url_for('index'))

    try:
        results = analyze_cv_against_jd(cv_text, jd_text)
    except Exception as e:
        if charged_credit and _firestore_enabled_and_ready(firestore_db):
            _add_credit(firestore_db, user_id, user_email, amount=COST_ANALYZE)
        flash(f'Analysis error: {e}', 'error')
        return redirect(url_for('index'))

    # Log usage in Firestore (non-blocking)
    try:
        if user_id and firestore_db is not None:
            firestore_db.collection('analyses').add({
                'userId': user_id,
                'email': user_email,
                'createdAt': firestore.SERVER_TIMESTAMP,
                'matchScore': results.get('skill_match', {}).get('skill_score'),
                'categories': results.get('category_match', {}).get('key_categories', []),
                'matchedCategories': results.get('category_match', {}).get('matched_categories', []),
                'missingCategories': results.get('category_match', {}).get('missing_categories', []),
                'bonusCategories': results.get('category_match', {}).get('bonus_categories', []),
            })

            firestore_db.collection('users').document(user_id).set({
                'email': user_email,
                'lastAnalysisAt': firestore.SERVER_TIMESTAMP,
                'totalAnalyses': firestore.Increment(1),
            }, merge=True)
    except Exception as e:
        logger.warning('Firestore write failed: %s', e)

    session_id = _save_session_payload({
        'cv_text': cv_text,
        'jd_text': jd_text,
        'results': results,
        'user_id': user_id,
        'created_at': datetime.utcnow().isoformat(),
        'token_usage_est': _estimate_tokens_from_text(cv_text, jd_text),
    })

    return render_template('results.html', results=results, session_id=session_id, cost_rewrite=COST_REWRITE)


# ---------------------------------------------------------------------------
@app.route('/api/credits', methods=['GET'])
def api_credits():
    token = _bearer_token()
    if not token:
        return jsonify({'error': 'missing token'}), 401
    try:
        auth_client, firestore_db = get_firebase()
        decoded = auth_client.verify_id_token(token)
    except Exception:
        return jsonify({'error': 'invalid token'}), 401

    if not _firestore_enabled_and_ready(firestore_db):
        return jsonify({'credits': 'unlimited', 'firestore': False})

    _, credits = _ensure_user_doc(firestore_db, decoded.get('uid'), decoded.get('email'))
    return jsonify({'credits': credits})


@app.route('/api/credits/topup', methods=['POST'])
def api_credits_topup():
    token = _bearer_token()
    if not token:
        return jsonify({'error': 'missing token'}), 401
    try:
        auth_client, firestore_db = get_firebase()
        decoded = auth_client.verify_id_token(token)
    except Exception:
        return jsonify({'error': 'invalid token'}), 401

    if not _firestore_enabled_and_ready(firestore_db):
        return jsonify({'error': 'credits disabled'}), 400

    _add_credit(firestore_db, decoded.get('uid'), decoded.get('email'), amount=MOCK_TOPUP_CREDITS)
    _, credits = _ensure_user_doc(firestore_db, decoded.get('uid'), decoded.get('email'))
    return jsonify({'credits': credits, 'added': MOCK_TOPUP_CREDITS, 'status': 'mock_success'})


# ---------------------------------------------------------------------------
# Stripe checkout + webhook
# ---------------------------------------------------------------------------

@app.route('/api/checkout', methods=['POST'])
def api_checkout():
    if not stripe_enabled:
        return jsonify({'error': 'Stripe not configured'}), 400
    token = _bearer_token()
    if not token:
        return jsonify({'error': 'missing token'}), 401
    try:
        auth_client, firestore_db = get_firebase()
        decoded = auth_client.verify_id_token(token)
    except Exception:
        return jsonify({'error': 'invalid token'}), 401

    quantity = 1
    try:
        body = request.get_json(silent=True) or {}
        quantity = int(body.get('quantity', 1))
        if quantity < 1:
            quantity = 1
    except Exception:
        quantity = 1

    success_url = (PUBLIC_URL or 'http://localhost:5050') + '/billing/success?session_id={CHECKOUT_SESSION_ID}'
    cancel_url = (PUBLIC_URL or 'http://localhost:5050') + '/billing/cancel'

    try:
        session = stripe.checkout.Session.create(
            mode='payment',
            line_items=[{
                'price': STRIPE_PRICE_ID,
                'quantity': quantity,
            }],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                'user_id': decoded.get('uid'),
                'email': decoded.get('email', ''),
                'quantity': quantity,
            }
        )
        return jsonify({'url': session.url})
    except Exception as e:
        logger.warning('Stripe checkout failed: %s', e)
        return jsonify({'error': 'stripe_error'}), 500


@app.route('/stripe/webhook', methods=['POST'])
def stripe_webhook():
    if not stripe_enabled or not STRIPE_WEBHOOK_SECRET:
        return 'Webhook not configured', 400
    payload = request.get_data(as_text=True)
    sig = request.headers.get('Stripe-Signature', '')
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        logger.warning('Stripe webhook signature failed: %s', e)
        return 'Bad signature', 400

    if event.get('type') == 'checkout.session.completed':
        session = event['data']['object']
        user_id = session.get('metadata', {}).get('user_id')
        email = session.get('metadata', {}).get('email')
        quantity = int(session.get('metadata', {}).get('quantity', 1))
        if user_id:
            try:
                _, firestore_db = get_firebase()
                if _firestore_enabled_and_ready(firestore_db):
                    _add_credit(firestore_db, user_id, email, amount=quantity)
            except Exception as e:
                logger.warning('Failed to add credits from webhook: %s', e)
    return 'ok', 200


@app.route('/billing/success')
def billing_success():
    flash('Payment successful. Credits added to your account.', 'success')
    return redirect(url_for('index'))


@app.route('/billing/cancel')
def billing_cancel():
    flash('Payment cancelled.', 'warning')
    return redirect(url_for('index'))


# ---------------------------------------------------------------------------
# Account page
# ---------------------------------------------------------------------------

PLANS = [
    {"name": "Starter", "price_inr": 199, "credits": 20, "rewrites": 4, "tag": None},
    {"name": "Popular", "price_inr": 449, "credits": 50, "rewrites": 10, "tag": "Most Popular"},
    {"name": "Pro Pack", "price_inr": 799, "credits": 100, "rewrites": 20, "tag": None},
]


@app.route('/account')
def account():
    return render_template('account.html',
                           plans=PLANS,
                           cost_rewrite=COST_REWRITE,
                           cost_analyze=COST_ANALYZE,
                           stripe_enabled=stripe_enabled)


# ---------------------------------------------------------------------------
# Snippet rewrite API (for selected paragraph)
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Admin dashboard (token/credits overview)
# ---------------------------------------------------------------------------

@app.route('/admin/dashboard')
def admin_dashboard():
    token = request.args.get('token', '')
    if token != ADMIN_TOKEN:
        return 'Unauthorized', 401

    sessions = _load_all_sessions(limit=300)
    analyses = [s for s in sessions if 'results' in s]
    rewrites = [s for s in sessions if 'rewrites' in s]
    total_tokens = sum(int(s.get('token_usage_est', 0) or 0) for s in sessions)
    total_ats = [s.get('results', {}).get('ats_score', 0) for s in analyses if isinstance(s.get('results'), dict)]
    avg_ats = round(sum(total_ats) / len(total_ats), 1) if total_ats else 0

    # Recent entries for table
    recent = []
    for s in sessions[:50]:
        kind = 'rewrite' if 'rewrites' in s else 'analysis'
        ts = s.get('created_at', '')[:19]
        tok = s.get('token_usage_est', 0)
        ats = s.get('results', {}).get('ats_score') if isinstance(s.get('results'), dict) else None
        recent.append({'sid': s.get('_sid'), 'kind': kind, 'created_at': ts, 'tokens': tok, 'ats': ats})

    return render_template('admin_dashboard.html',
                           stats={
                               'sessions': len(sessions),
                               'analyses': len(analyses),
                               'rewrites': len(rewrites),
                               'tokens': total_tokens,
                               'avg_ats': avg_ats,
                           },
                           recent=recent)

# ---------------------------------------------------------------------------
# Admin endpoints — protected by ADMIN_TOKEN
# ---------------------------------------------------------------------------

@app.route('/admin/cvs')
def list_cvs():
    token = request.args.get('token', '')
    if token != ADMIN_TOKEN:
        return 'Unauthorized', 401
    files = sorted(os.listdir(CV_STORAGE), reverse=True)
    files = [f for f in files if not f.startswith('.')]
    file_info = []
    for f in files:
        path = os.path.join(CV_STORAGE, f)
        size_kb = round(os.path.getsize(path) / 1024, 1)
        file_info.append({'name': f, 'size_kb': size_kb})
    return render_template('admin_cvs.html', files=file_info, token=token)


@app.route('/admin/cvs/download/<filename>')
def download_cv(filename):
    token = request.args.get('token', '')
    if token != ADMIN_TOKEN:
        return 'Unauthorized', 401
    filename = secure_filename(filename)
    filepath = os.path.join(CV_STORAGE, filename)
    if not os.path.isfile(filepath):
        return 'File not found', 404
    return send_file(filepath, as_attachment=True)


@app.route('/admin/cvs/download-all')
def download_all_cvs():
    token = request.args.get('token', '')
    if token != ADMIN_TOKEN:
        return 'Unauthorized', 401
    files = [f for f in os.listdir(CV_STORAGE) if not f.startswith('.')]
    if not files:
        return 'No CVs stored yet', 404
    zip_path = os.path.join(tempfile.gettempdir(), 'all_cvs')
    shutil.make_archive(zip_path, 'zip', CV_STORAGE)
    return send_file(zip_path + '.zip', as_attachment=True,
                     download_name='collected_cvs.zip')


@app.route('/api/cvs')
def api_list_cvs():
    token = request.args.get('token', '')
    if token != ADMIN_TOKEN:
        return jsonify({'error': 'Unauthorized'}), 401
    files = sorted(os.listdir(CV_STORAGE), reverse=True)
    files = [f for f in files if not f.startswith('.')]
    return jsonify({'files': files})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    app.run(debug=True, port=port)
