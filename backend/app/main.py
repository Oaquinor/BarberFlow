"""
KingFlow Barber - FastAPI Application

Enterprise SaaS Platform for Modern Barbershops
Developed by NOVENTIA GROUP
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.core.config.settings import get_settings
from app.core.logging.logger import get_logger
from app.api.v1 import router as api_v1_router

settings = get_settings()
logger = get_logger(__name__)


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
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API routers
    application.include_router(api_v1_router, prefix="/api/v1")

    # Get the frontend directory path
    frontend_dir = Path(__file__).parent.parent.parent / "frontend"

    # Mount static files if frontend exists
    if frontend_dir.exists():
        application.mount("/css", StaticFiles(directory=str(frontend_dir / "css")), name="css")
        application.mount("/js", StaticFiles(directory=str(frontend_dir / "js")), name="js")

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
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy"}

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
