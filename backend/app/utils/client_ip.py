"""Resolve the client address from the transport or a configured trusted proxy."""

from ipaddress import ip_address

from fastapi import HTTPException, Request


def get_client_ip(request: Request, configured_header: str) -> str:
    """Return a normalized client IP without trusting unconfigured headers."""
    header_name = configured_header.strip().lower()
    if header_name == "socket":
        candidate = request.client.host if request.client else None
        if isinstance(candidate, str) and candidate.strip():
            try:
                return ip_address(candidate.strip()).compressed
            except ValueError:
                # ASGI test clients may supply symbolic transport addresses.
                return candidate.strip().lower()
    elif header_name in {"cf-connecting-ip", "x-real-ip"}:
        candidate = request.headers.get(header_name)
    else:
        raise RuntimeError(
            "CLIENT_IP_HEADER must be socket, CF-Connecting-IP, or X-Real-IP"
        )

    try:
        return ip_address(candidate.strip()).compressed
    except (AttributeError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail="No se pudo verificar la dirección de red para procesar la solicitud.",
        ) from exc
