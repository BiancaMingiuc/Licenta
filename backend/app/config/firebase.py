# database.py
import firebase_admin  # type: ignore[import-not-found]
from firebase_admin import credentials, firestore  # type: ignore[import-not-found]

# Inițializare conexiune securizată către Firebase folosind fișierul JSON
if not firebase_admin._apps:
    cred = credentials.Certificate("firebase_credentials.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()