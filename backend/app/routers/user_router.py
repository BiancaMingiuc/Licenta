"""Routes for the known-persons list (whitelist).

Every route requires the ADMIN role. An ``APP_USER`` does not administer
people; they read their own profile through ``GET /api/auth/me``.

``hub_id`` is no longer a query parameter. It is taken from the caller's
token, because otherwise multi-tenant isolation would be a convention only:
any client could ask for another hub's data by changing a parameter in the
URL.
"""

from typing import List

from fastapi import APIRouter, Depends, status

from app.dependencies.auth import require_admin
from app.schemas.auth_schema import CurrentUser
from app.schemas.user_schema import UserCreate, UserDetail, UserPublic, UserUpdate
from app.services.user_service import UserService

router = APIRouter(prefix="/api/whitelist", tags=["Whitelist (Known Persons)"])
service = UserService()


@router.get(
    "/",
    response_model=List[UserPublic],
    summary="List the people registered in this hub",
)
def get_whitelist(current_user: CurrentUser = Depends(require_admin)) -> List[UserPublic]:
    users = service.get_all_users(current_user.hub_id)
    return [UserPublic.from_row(user) for user in users]


@router.get(
    "/{doc_id}",
    response_model=UserDetail,
    summary="One person, with their surveillance history",
)
def get_user(doc_id: str, current_user: CurrentUser = Depends(require_admin)) -> UserDetail:
    user = service.get_user(doc_id, hub_id=current_user.hub_id)
    return UserDetail.from_row(user)


@router.post(
    "/",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Enrol a person",
    responses={
        409: {"description": "Email is already in use"},
        422: {"description": "Invalid combination of role, email and password"},
    },
)
def add_user(user: UserCreate, current_user: CurrentUser = Depends(require_admin)) -> UserPublic:
    """201 Created is the correct status for creating a resource, not 200."""
    created = service.create_user(user, hub_id=current_user.hub_id)
    return UserPublic.from_row(created)


@router.put(
    "/{doc_id}",
    response_model=UserPublic,
    summary="Update a person",
)
def update_user(
    doc_id: str,
    user: UserUpdate,
    current_user: CurrentUser = Depends(require_admin),
) -> UserPublic:
    updated = service.update_user(doc_id, user, hub_id=current_user.hub_id)
    return UserPublic.from_row(updated)


@router.delete("/{doc_id}", summary="Delete a person")
def delete_user(doc_id: str, current_user: CurrentUser = Depends(require_admin)) -> dict[str, str]:
    return service.delete_user(doc_id, hub_id=current_user.hub_id)
