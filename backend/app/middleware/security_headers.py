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
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
    }
    if not is_debug_api_docs:
        connect_sources = "'self' https:"
        if get_settings().ENVIRONMENT.lower() != "production":
            connect_sources += " http://localhost:* http://127.0.0.1:*"
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            f"img-src 'self' data: blob:; connect-src {connect_sources}; "
            "base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'",
        )

    if get_settings().ENVIRONMENT.lower() == "production":
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )

    if request.url.path == "/api" or request.url.path.startswith("/api/"):
        cache_control = response.headers.get("Cache-Control", "")
        directives = {item.strip().lower() for item in cache_control.split(",")}
        response.headers["Cache-Control"] = (
            "private, no-store, max-age=0" if "private" in directives else "no-store"
        )
        response.headers["Pragma"] = "no-cache"

    return response
