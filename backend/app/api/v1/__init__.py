"""API v1 router."""

from fastapi import APIRouter

from app.api.v1.endpoints import onboarding
from app.api.v1.endpoints import platform

router = APIRouter()

router.include_router(onboarding.router)
router.include_router(platform.router)
