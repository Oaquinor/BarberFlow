"""
KingFlow Barber - FastAPI Application

Enterprise SaaS Platform for Modern Barbershops
Developed by NOVENTIA GROUP
"""

from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config.settings import get_settings
from app.core.logging.logger import get_logger
from app.api.v1 import router as api_v1_router
from app.core.database import get_db
from app.middleware.security_headers import add_security_headers

settings = get_settings()
logger = get_logger(__name__)


def _is_unsafe_production_secret(secret: str) -> bool:
    normalized = secret.strip().lower()
    placeholders = (
        "your-secret", "change-this", "replace-with", "random-bytes",
        "placeholder", "changeme", "example-secret",
    )
    if len(secret) < 32 or any(marker in normalized for marker in placeholders):
        return True
    if len(set(secret)) < 12:
        return True
    return max(secret.count(character) for character in set(secret)) > len(secret) // 2


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("🚀 KingFlow Barber starting...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Debug mode: {settings.DEBUG}")

    yield

    logger.info("👋 KingFlow Barber shutting down...")


def create_application() -> FastAPI:
    """Create and configure FastAPI application."""

    cors_origins = settings.CORS_ORIGINS

    if settings.ENVIRONMENT.lower() == "production":
        if settings.DEBUG:
            raise RuntimeError("DEBUG must be disabled in production")
        if _is_unsafe_production_secret(settings.SECRET_KEY):
            raise RuntimeError("Set a strong SECRET_KEY before starting in production")
        if not settings.DATABASE_URL.startswith("mysql+pymysql://"):
            raise RuntimeError("Production DATABASE_URL must use the MySQL PyMySQL driver")
        frontend_url = urlsplit(settings.FRONTEND_BASE_URL.strip())
        if (
            frontend_url.scheme != "https"
            or not frontend_url.hostname
            or frontend_url.username
            or frontend_url.password
            or frontend_url.query
            or frontend_url.fragment
        ):
            raise RuntimeError("Production FRONTEND_BASE_URL must be an explicit HTTPS URL")
        cors_origins = cors_origins or [settings.FRONTEND_BASE_URL.rstrip("/")]
        if any(origin == "*" or not origin.startswith("https://") for origin in cors_origins):
            raise RuntimeError("Production CORS_ORIGINS must contain explicit HTTPS origins")

    application = FastAPI(
        title="KingFlow Barber API",
        description="Enterprise SaaS Platform for Modern Barbershops",
        version="1.0.0",
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        lifespan=lifespan
    )

    # CORS Configuration
    application.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.middleware("http")(add_security_headers)

    # Include API routers
    application.include_router(api_v1_router, prefix="/api/v1")

    # Get the frontend directory path
    frontend_dir = Path(__file__).parent.parent.parent / "frontend"

    @application.get("/")
    async def root():
        """Serve the frontend index.html."""
        index_file = frontend_dir / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {
            "name": "KingFlow Barber API",
            "version": "1.0.0",
            "status": "running",
            "developer": "NOVENTIA GROUP"
        }

    @application.get("/health")
    def health_check(db: Session = Depends(get_db)):
        """Report healthy only when the configured MySQL connection responds."""
        try:
            db.execute(text("SELECT 1"))
        except Exception as exc:
            raise HTTPException(status_code=503, detail="MySQL no disponible") from exc
        return {"status": "healthy", "database": "connected"}

    # Mount the whole frontend directory last so it acts as a catch-all for
    # static assets and PWA pages (client.html, onboarding.html, admin.html,
    # manifest.webmanifest, sw.js, offline.html, css/, js/, icons/) without
    # shadowing the API routes or the explicit routes above.
    if frontend_dir.exists():
        application.mount("/", StaticFiles(directory=str(frontend_dir)), name="frontend")

    return application


app = create_application()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )
