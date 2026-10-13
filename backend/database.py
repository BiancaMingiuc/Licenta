# database.py
import firebase_admin  # type: ignore[import-not-found]
from firebase_admin import credentials, firestore  # type: ignore[import-not-found]

# Inițializare conexiune securizată către Firebase folosind fișierul JSON
cred = credentials.Certificate("firebase_credentials.json")
firebase_admin.initialize_app(cred)

db = firestore.client()

def get_whitelist():
    """Extrage toți utilizatorii autorizați din colecția Whitelist."""
    users_ref = db.collection("Whitelist")
    docs = users_ref.stream()
    return [{"id": doc.id, **doc.to_dict()} for doc in docs]

def add_log(user_id: str, status: str):
    """Adaugă un eveniment de acces în istoric cu timestamp-ul serverului."""
    logs_ref = db.collection("Logs")
    logs_ref.add({
        "user_id": user_id,
        "status": status,
        "timestamp": firestore.SERVER_TIMESTAMP
    })
    return {"success": True}