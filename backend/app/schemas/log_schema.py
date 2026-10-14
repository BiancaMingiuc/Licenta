from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime

class LogCreate(BaseModel):
    hub_id: str = "HUB_001"
    camera_id: str = "cam_intrare"
    user_id: Optional[str] = None
    user_name: Optional[str] = "Persoană Necunoscută"
    status: Literal["GRANTED", "DENIED"] = "DENIED"

class LogEntity(BaseModel):
    """Definiția completă a unui document din colecția Logs"""
    id: str
    hub_id: str
    camera_id: str
    user_id: Optional[str] = "UNKNOWN"
    user_name: Optional[str] = "Persoană Necunoscută"
    status: str
    timestamp: Optional[datetime] = None


class SimulatedDetection(BaseModel):
    hub_id: str = "HUB_001"
    camera_id: str = "cam_intrare"
    authorized: bool = False
    user_id: Optional[str] = None