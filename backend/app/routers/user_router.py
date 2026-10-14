from fastapi import APIRouter, Query
from app.schemas.user_schema import UserCreate, UserUpdate
from app.services.user_service import UserService

router = APIRouter(prefix="/api/whitelist", tags=["Whitelist (Users)"])
service = UserService()

@router.get("/")
def get_whitelist(hub_id: str = Query(default="HUB_001", description="ID-ul sistemului Edge AI")):
    return service.get_all_users(hub_id)

@router.get("/{doc_id}")
def get_user(doc_id: str):
    return service.get_user(doc_id)

@router.post("/")
def add_user(user: UserCreate):
    return service.create_user(user)

@router.put("/{doc_id}")
def update_user(doc_id: str, user: UserUpdate):
    return service.update_user(doc_id, user)

@router.delete("/{doc_id}")
def delete_user(doc_id: str):
    return service.delete_user(doc_id)