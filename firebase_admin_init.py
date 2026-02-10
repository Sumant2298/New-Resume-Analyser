import json
import os

import firebase_admin
from firebase_admin import auth, credentials, firestore


def _firestore_enabled() -> bool:
    value = os.environ.get('FIRESTORE_ENABLED', 'false').strip().lower()
    return value in ('1', 'true', 'yes', 'on')


def get_firebase():
    """Initialise Firebase Admin and return (auth, firestore_client or None)."""
    if not firebase_admin._apps:
        raw_key = os.environ.get('FIREBASE_SERVICE_ACCOUNT_KEY', '')
        if not raw_key:
            raise RuntimeError('FIREBASE_SERVICE_ACCOUNT_KEY is not configured.')
        try:
            service_account_info = json.loads(raw_key)
        except json.JSONDecodeError as exc:
            raise RuntimeError('FIREBASE_SERVICE_ACCOUNT_KEY must be valid JSON.') from exc

        credential = credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(credential)

    if _firestore_enabled():
        return auth, firestore.client()
    return auth, None
