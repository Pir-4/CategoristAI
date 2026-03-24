from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.routing import APIRouter

from app.api.dependencies import check_admin_permission, get_current_user
from app.core import AsyncSession, get_session
from app.models import User
from app.schemas import UserCreate, UserRead, UserUpdate
from app.services.user_service import (
    create_user as svc_create_user,
)
from app.services.user_service import (
    get_user as svc_get_user,
)
from app.services.user_service import (
    get_users as svc_get_users,
)
from app.services.user_service import (
    update_user as svc_update_user,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
async def get_users(
    session: AsyncSession = Depends(get_session),
    _: User = Depends(check_admin_permission),
) -> list[UserRead]:
    users = await svc_get_users(session)
    return [UserRead.model_validate(user) for user in users]


@router.get("/me")
async def get_me(
    user: User = Depends(get_current_user),
) -> UserRead:
    return UserRead.model_validate(user)


@router.get("/{user_id}")
async def get_user(
    user_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(check_admin_permission),
) -> UserRead:
    user = await svc_get_user(session=session, user_id=user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return UserRead.model_validate(user)


@router.post("")
async def create_user(
    user: UserCreate,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(check_admin_permission),
) -> UserRead:
    new_user = await svc_create_user(session=session, data=user)
    return UserRead.model_validate(new_user)


@router.patch("/{user_id}")
async def update_user(
    user_id: UUID,
    user: UserUpdate,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(check_admin_permission),
) -> UserRead:
    new_user = await svc_update_user(
        session=session, user_id=user_id, data=user
    )
    return UserRead.model_validate(new_user)
