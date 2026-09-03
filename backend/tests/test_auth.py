"""
Authentication endpoint tests.

Tests for login, registration, and token management.
"""

import pytest
from httpx import AsyncClient

from app.core.security import hash_password
from app.models import User
from app.core.constants import UserRole


@pytest.mark.asyncio
async def test_register_user(client: AsyncClient):
    """Test user registration."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "newuser@example.com",
            "password": "SecurePass123",
            "first_name": "New",
            "last_name": "User",
            "phone": "+1234567890"
        }
    )

    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["data"]["email"] == "newuser@example.com"


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, test_db):
    """Test successful login."""
    # Create test user
    user = User(
        email="testuser@example.com",
        password_hash=hash_password("TestPass123"),
        first_name="Test",
        last_name="User",
        role=UserRole.CLIENT,
        is_active=True
    )
    test_db.add(user)
    await test_db.commit()

    # Login
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "testuser@example.com",
            "password": "TestPass123"
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient):
    """Test login with invalid credentials."""
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "nonexistent@example.com",
            "password": "wrongpassword"
        }
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user(client: AsyncClient, test_db):
    """Test getting current user info."""
    # Create and login user
    user = User(
        email="testuser@example.com",
        password_hash=hash_password("TestPass123"),
        first_name="Test",
        last_name="User",
        role=UserRole.CLIENT,
        is_active=True
    )
    test_db.add(user)
    await test_db.commit()

    # Login to get token
    login_response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "testuser@example.com",
            "password": "TestPass123"
        }
    )
    token = login_response.json()["access_token"]

    # Get current user
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["email"] == "testuser@example.com"
