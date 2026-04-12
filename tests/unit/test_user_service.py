from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models import User
from app.schemas import UserCreate, UserUpdate
from app.services.user_service import create_user, update_user


@pytest.fixture
def mock_session():
    return AsyncMock()


async def test_create_user_hashes_password(mock_session):
    user = UserCreate(login="test_user", password="test_password")
    db_user = await create_user(mock_session, user)
    assert db_user.hashed_password != user.password


async def test_update_user_hashes_password(mock_session):
    current_user = User(
        id=uuid4(), login="test_user", hashed_password="old_hash"
    )
    old_hash = current_user.hashed_password
    mock_session.get.return_value = current_user
    user = UserUpdate(login="test_user", password="test_password")

    db_user = await update_user(mock_session, current_user.id, user)
    assert db_user.hashed_password != old_hash
    assert db_user.hashed_password != user.password
