"""API v1 router."""

from fastapi import APIRouter

from app.api.v1.endpoints import onboarding
from app.api.v1.endpoints import platform
from app.api.v1.endpoints import admin
from app.api.v1 import services
from app.api.v1 import achievements, admin_settings, analytics, billing, performance, password_reset

router = APIRouter()

router.include_router(onboarding.router)
router.include_router(platform.router)
router.include_router(admin.router)
router.include_router(services.router)
router.include_router(achievements.router)
router.include_router(performance.router)
router.include_router(analytics.router)
router.include_router(admin_settings.router)
router.include_router(billing.router)
router.include_router(password_reset.router)
