# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import get_whitelist, add_log
from pydantic import BaseModel

app = FastAPI(title="Edge AI Access Control API")

# Configurare CORS pentru a permite accesul din frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class LogEntry(BaseModel):
    user_id: str
    status: str

@app.get("/api/whitelist")
def fetch_whitelist():
    """Ruta prin care frontend-ul preia lista de utilizatori din Firebase."""
    return get_whitelist()

@app.post("/api/logs")
def create_log(log: LogEntry):
    """Ruta prin care se salvează o nouă încercare de acces în istoric."""
    return add_log(log.user_id, log.status)