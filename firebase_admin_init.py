import json
import os

import firebase_admin
from firebase_admin import auth, credentials, firestore


def get_firebase():
    """Initialise Firebase Admin and return (auth, firestore_client)."""
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

    return auth, firestore.client()
