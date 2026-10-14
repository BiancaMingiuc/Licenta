from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from app.schemas.log_schema import LogEntity

UserRole = Literal["ADMIN", "APP_USER", "PHYSICAL_ONLY"]

class UserCreate(BaseModel):
    hub_id: str = "HUB_001"
    name: str
    role: UserRole = "PHYSICAL_ONLY"
    has_app_access: bool = False
    email: Optional[str] = None
    allowed_cameras: List[str] = Field(default_factory=lambda: ["cam_intrare"])
    embedding: Optional[List[float]] = None

class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[UserRole] = None
    has_app_access: Optional[bool] = None
    email: Optional[str] = None
    allowed_cameras: Optional[List[str]] = None
    embedding: Optional[List[float]] = None

class UserEntity(BaseModel):
    id: str
    hub_id: str
    name: str
    role: UserRole
    has_app_access: bool
    email: Optional[str] = None
    allowed_cameras: List[str] = Field(default_factory=list)
    embedding: Optional[List[float]] = None
    logs: Optional[List[LogEntity]] = Field(default_factory=list)