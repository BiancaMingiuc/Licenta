from typing import Optional
from fastapi import APIRouter, Query
from app.schemas.log_schema import LogCreate
from app.services.log_service import LogService

router = APIRouter(prefix="/api/logs", tags=["Access Logs"])
service = LogService()

@router.get("/")
def get_logs(
    hub_id: str = Query(default="HUB_001", description="ID-ul sistemului Edge AI"),
    camera_id: Optional[str] = Query(default=None, description="Optional: filtreaza după o camera anume")
):
    return service.get_all_logs(hub_id, camera_id)

@router.post("/")
def add_log(log: LogCreate):
    return service.create_log(log)

@router.delete("/{doc_id}")
def delete_log(doc_id: str):
    return service.delete_log(doc_id)