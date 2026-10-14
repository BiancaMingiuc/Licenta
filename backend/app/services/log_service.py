from typing import Optional
from fastapi import HTTPException
from app.repositories.log_repo import LogRepository
from app.repositories.user_repo import UserRepository
from app.schemas.log_schema import LogCreate

class LogService:
    def __init__(self):
        self.repo = LogRepository()
        self.user_repo = UserRepository()

    def get_all_logs(self, hub_id: str, camera_id: Optional[str] = None):
        return self.repo.get_all_by_hub(hub_id, camera_id)

    def create_log(self, log: LogCreate):
        log_data = log.model_dump()
        if log_data["user_id"] == "UNKNOWN":
            log_data["user_id"] = None
        if log_data["user_id"] and not self.user_repo.exists(log_data["user_id"]):
            raise HTTPException(status_code=404, detail="Utilizatorul asociat logului nu a fost găsit.")
        return self.repo.create(log_data)

    def delete_log(self, doc_id: str):
        deleted = self.repo.delete(doc_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Înregistrarea din log nu a fost găsită.")
        return {"message": "Log-ul a fost șters cu succes."}