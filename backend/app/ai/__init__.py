"""Explainable predictive services built from tenant-owned operating data.

The first production feature is the seven-day demand forecast. It uses a
weekday/hour historical baseline and known bookings; it does not call an
external model or invent data where a tenant lacks history.
"""

from app.ai.demand_forecast import DemandForecastService

__all__ = ["DemandForecastService"]
