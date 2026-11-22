"""Unit coverage for goal-focused dashboard recommendations."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.services.onboarding_service import OnboardingService


@pytest.mark.parametrize(
    "primary_goal",
    ["more_clients", "organization", "reduce_cancellations", "save_time", "better_service", "productivity"],
)
def test_dashboard_layout_only_describes_existing_recommendations(primary_goal):
    db = Mock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        primary_goal=primary_goal,
    )

    result = OnboardingService.get_dashboard_layout(db, barbershop_id=1)

    assert set(result.model_dump()) == {"layout_type", "greeting_message", "insights"}
    assert result.insights


def test_dashboard_layout_without_goal_returns_setup_advice_only():
    db = Mock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        primary_goal=None,
    )

    result = OnboardingService.get_dashboard_layout(db, barbershop_id=1)

    assert set(result.model_dump()) == {"layout_type", "greeting_message", "insights"}
    assert result.layout_type == "default"
    assert result.insights
