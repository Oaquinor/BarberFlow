"""API v1 router."""

from fastapi import APIRouter

from app.api.v1.endpoints import onboarding
from app.api.v1.endpoints import platform
from app.api.v1.endpoints import booking
from app.api.v1.endpoints import booking_waitlist
from app.api.v1.endpoints import admin
from app.api.v1.endpoints import owner
from app.api.v1.endpoints import notifications
from app.api.v1 import services
from app.api.v1 import achievements, admin_settings, analytics, billing, client_accounts, performance, password_reset
from app.api.v1 import inventory
from app.api.v1 import retail_sales
from app.api.v1 import expenses

router = APIRouter()

router.include_router(onboarding.router)
router.include_router(platform.router)
router.include_router(booking.router)
router.include_router(booking_waitlist.router)
router.include_router(admin.router)
router.include_router(owner.router)
router.include_router(notifications.router)
router.include_router(services.router)
router.include_router(achievements.router)
router.include_router(performance.router)
router.include_router(analytics.router)
router.include_router(admin_settings.router)
router.include_router(billing.router)
router.include_router(password_reset.router)
router.include_router(inventory.router)
router.include_router(retail_sales.router)
router.include_router(expenses.router)
router.include_router(client_accounts.router)
