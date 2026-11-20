"""Default browser protections and cache rules for API responses."""

from fastapi import Request, Response

from app.core.config.settings import get_settings


async def add_security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), geolocation=(), microphone=()")
    is_debug_api_docs = getattr(get_settings(), "DEBUG", False) and request.url.path in {
        "/docs", "/docs/oauth2-redirect", "/redoc",
    }
    if not is_debug_api_docs:
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; connect-src 'self' https: http://localhost:* http://127.0.0.1:*; "
            "base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'",
        )

    if get_settings().ENVIRONMENT.lower() == "production":
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )

    if request.url.path == "/api" or request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"

    return response
