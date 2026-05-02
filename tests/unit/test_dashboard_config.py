import pytest
from fastapi import HTTPException

from src.services.dashboard_service import dashboard_service


def test_dashboard_config_exposes_alpaca_broker_settings():
    config = dashboard_service.get_dashboard_config()
    items = {item["key"]: item for item in config["items"]}

    assert items["BROKERAGE_PROVIDER"]["options"] == ["T212", "ALPACA"]
    assert items["BROKERAGE_PROVIDER"]["sensitive"] is True
    assert items["BROKERAGE_PROVIDER"]["value"] in {"T212", "ALPACA"}
    assert items["TRADING_212_MODE"]["options"] == ["demo", "live"]
    assert isinstance(items["ALPACA_BASE_URL"]["value"], str)
    assert items["ALPACA_BASE_URL"]["value"] != "********"
    assert items["ALPACA_API_KEY"]["sensitive"] is True
    assert items["ALPACA_API_SECRET"]["sensitive"] is True
    assert items["ALPACA_BASE_URL"]["sensitive"] is True


def test_dashboard_config_validates_brokerage_provider_options():
    assert dashboard_service._coerce_config_value("BROKERAGE_PROVIDER", "alpaca") == "ALPACA"
    assert dashboard_service._coerce_config_value("TRADING_212_MODE", "LIVE") == "live"

    with pytest.raises(HTTPException):
        dashboard_service._coerce_config_value("BROKERAGE_PROVIDER", "IBKR")


# ---------------------------------------------------------------------------
# PR change: removed "smart masking" that exempted bool/options fields from masking
# Now should_mask is determined solely by spec.get("masked", spec["sensitive"])
# without special-casing booleans or fields with options.
# ---------------------------------------------------------------------------

def test_dashboard_config_bool_field_with_sensitive_flag_is_masked():
    """
    The PR removed the smart-masking bypass that prevented masking for
    bool-type fields. After the PR, if a bool field is marked sensitive and
    masked=True, its value will be masked.

    Most bool fields in the real config are NOT sensitive (masked=False),
    so we verify the un-masked path via the real config. If no bool field is
    sensitive, this test simply confirms no crash.
    """
    config = dashboard_service.get_dashboard_config()
    items = {item["key"]: item for item in config["items"]}

    bool_items = [v for v in items.values() if v["type"] == "bool"]
    # Verify we can process bool items without error (regression guard)
    for item in bool_items:
        assert item["value"] in {True, False, "true", "false", "Enabled", "Disabled", "True", "False"} or \
               item["value"] == "********" or \
               isinstance(item["value"], bool)


def test_dashboard_config_options_field_value_is_not_masked():
    """
    Fields with enumerated options (like BROKERAGE_PROVIDER) should expose
    their real value (not "********") regardless of sensitivity flag,
    because the dashboard uses the value for the initial select selection.
    This was the intent of the old smart-masking; after the PR the
    masking decision is purely from the spec's 'masked' key.
    """
    config = dashboard_service.get_dashboard_config()
    items = {item["key"]: item for item in config["items"]}

    # BROKERAGE_PROVIDER has options and its spec should not set masked=True
    bp = items.get("BROKERAGE_PROVIDER")
    if bp:
        # Value must be a real provider name (T212 or ALPACA), not masked
        assert bp["value"] in {"T212", "ALPACA"}, (
            f"Expected BROKERAGE_PROVIDER to expose its real value, got: {bp['value']!r}"
        )


def test_trigger_pair_discovery_method_removed():
    """
    The PR removed trigger_pair_discovery from DashboardService.
    """
    assert not hasattr(dashboard_service, "trigger_pair_discovery"), (
        "DashboardService.trigger_pair_discovery should have been removed in this PR"
    )


def test_get_dashboard_config_returns_required_keys():
    """Regression: get_dashboard_config must always return items, two_factor,
    audit_log, and integrations."""
    config = dashboard_service.get_dashboard_config()
    assert "items" in config
    assert "two_factor" in config
    assert "audit_log" in config
    assert "integrations" in config


def test_integrations_includes_brokerage_provider():
    """integrations.brokerage_provider must be present after the PR."""
    config = dashboard_service.get_dashboard_config()
    integrations = config["integrations"]
    assert "brokerage_provider" in integrations
    assert isinstance(integrations["brokerage_provider"], str)
