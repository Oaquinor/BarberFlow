"""Shared request policies are configured in the FastAPI app and API routes.

CORS is registered in ``app.main``. Login and support request limits use
MySQL-backed counters; no separate custom middleware stack is configured.
"""
