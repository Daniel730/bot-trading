"""Dashboard self-esteem must not present the orchestrator prior as measured accuracy."""

from src.config import settings
from src.services.dashboard_service import resolve_dashboard_accuracy_display


def test_unset_prior_is_hidden_from_dashboard():
    payload = resolve_dashboard_accuracy_display(
        accuracy_str=str(settings.GLOBAL_STRATEGY_ACCURACY_DEFAULT),
        samples_str="0",
        default_accuracy=settings.GLOBAL_STRATEGY_ACCURACY_DEFAULT,
    )
    assert payload["global_accuracy"] is None
    assert payload["global_accuracy_source"] == "unset"
    assert payload["global_accuracy_samples"] == 0


def test_missing_accuracy_key_is_unset():
    payload = resolve_dashboard_accuracy_display(
        accuracy_str=None,
        samples_str="0",
        default_accuracy=0.5,
    )
    assert payload["global_accuracy"] is None
    assert payload["global_accuracy_source"] == "unset"


def test_measured_accuracy_with_samples():
    payload = resolve_dashboard_accuracy_display(
        accuracy_str="0.6100",
        samples_str="3",
        default_accuracy=0.5,
    )
    assert payload["global_accuracy"] == 0.61
    assert payload["global_accuracy_source"] == "measured"
    assert payload["global_accuracy_samples"] == 3


def test_legacy_accuracy_off_prior_without_samples():
    payload = resolve_dashboard_accuracy_display(
        accuracy_str="0.72",
        samples_str="0",
        default_accuracy=0.5,
    )
    assert payload["global_accuracy"] == 0.72
    assert payload["global_accuracy_source"] == "legacy"
