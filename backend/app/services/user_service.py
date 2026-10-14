from fastapi import HTTPException
from app.repositories.user_repo import UserRepository
from app.repositories.log_repo import LogRepository
from app.schemas.user_schema import UserCreate, UserUpdate

class UserService:
    def __init__(self):
        self.repo = UserRepository()
        self.log_repo = LogRepository()

    def get_all_users(self, hub_id: str):
        return self.repo.get_all_by_hub(hub_id)

    def get_user(self, doc_id: str):
        user = self.repo.get_by_id(doc_id)
        if not user:
            raise HTTPException(status_code=404, detail="Utilizatorul nu a fost găsit în Whitelist.")
        
        # Populăm relația One-to-Many cu istoricul acelui utilizator
        user["logs"] = self.log_repo.get_by_user_id(doc_id)
        return user

    def create_user(self, user: UserCreate):
        user_data = user.model_dump()
        # Sincronizare automată între rol și accesul la aplicație
        if user_data["role"] in ["ADMIN", "APP_USER"]:
            user_data["has_app_access"] = True
        else:
            user_data["has_app_access"] = False
            
        return self.repo.create(user_data)

    def update_user(self, doc_id: str, user_update: UserUpdate):
        update_data = {k: v for k, v in user_update.model_dump().items() if v is not None}
        if not update_data:
            raise HTTPException(status_code=400, detail="Nu au fost furnizate date pentru actualizare.")
        
        if "role" in update_data:
            update_data["has_app_access"] = update_data["role"] in ["ADMIN", "APP_USER"]

        updated = self.repo.update(doc_id, update_data)
        if not updated:
            raise HTTPException(status_code=404, detail="Utilizatorul nu a fost găsit.")
        return updated

    def delete_user(self, doc_id: str):
        deleted = self.repo.delete(doc_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Utilizatorul nu a fost găsit.")
        return {"message": "Utilizatorul a fost șters cu succes."}