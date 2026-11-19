"""Owner-facing subscription status and usage contracts."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class SubscriptionUsage(BaseModel):
    used: int
    limit: Optional[int]


class OwnerSubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plan: str
    status: str
    currency: str
    current_period_start: datetime
    current_period_end: datetime
    days_remaining: int
    auto_renew: bool
    usage: dict[str, SubscriptionUsage]
