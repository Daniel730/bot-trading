"""Sentry fail-closed / scrub contracts (#119)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.services import sentry_service


@pytest.fixture(autouse=True)
def _reset_sentry():
    sentry_service.reset_for_tests()
    yield
    sentry_service.reset_for_tests()


def test_setup_sentry_noop_when_dsn_empty():
    with patch("src.config.settings") as settings:
        settings.SENTRY_DSN = ""
        settings.SENTRY_ENABLED = True
        settings.SENTRY_TRACES_SAMPLE_RATE = 0.0
        settings.SENTRY_SAMPLE_RATE = 1.0
        settings.SENTRY_ENVIRONMENT = ""
        settings.PAPER_TRADING = True
        assert sentry_service.setup_sentry(force=True) is False
        assert sentry_service.is_enabled() is False


def test_setup_sentry_noop_when_disabled_flag():
    with patch("src.config.settings") as settings:
        settings.SENTRY_DSN = "https://key@example.ingest.sentry.io/1"
        settings.SENTRY_ENABLED = False
        settings.SENTRY_TRACES_SAMPLE_RATE = 0.0
        settings.SENTRY_SAMPLE_RATE = 1.0
        settings.SENTRY_ENVIRONMENT = "test"
        settings.PAPER_TRADING = True
        assert sentry_service.setup_sentry(force=True) is False
        assert sentry_service.is_enabled() is False


def test_before_send_scrubs_dashboard_token_header():
    event = {
        "request": {
            "headers": {
                "Authorization": "Bearer secret-token",
                "X-Dashboard-Session": "sess",
                "Content-Type": "application/json",
            }
        },
        "extra": {"dashboard_token": "should-hide", "pair": "A_B"},
    }
    scrubbed = sentry_service._before_send(event, {})
    assert scrubbed is not None
    assert scrubbed["request"]["headers"]["Authorization"] == "[Filtered]"
    assert scrubbed["extra"]["dashboard_token"] == "[Filtered]"
    assert scrubbed["extra"]["pair"] == "A_B"


def test_setup_sentry_inits_when_enabled_and_dsn_set():
    mock_sdk = MagicMock()
    with patch.dict("sys.modules", {"sentry_sdk": mock_sdk}):
        # Integrations imported inside setup — stub packages.
        mock_fastapi = MagicMock()
        mock_logging = MagicMock()
        mock_asyncio = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "sentry_sdk.integrations.fastapi": mock_fastapi,
                "sentry_sdk.integrations.logging": mock_logging,
                "sentry_sdk.integrations.asyncio": mock_asyncio,
            },
        ):
            mock_fastapi.FastApiIntegration = MagicMock(return_value="fastapi")
            mock_logging.LoggingIntegration = MagicMock(return_value="logging")
            mock_asyncio.AsyncioIntegration = MagicMock(return_value="asyncio")
            with patch("src.config.settings") as settings:
                settings.SENTRY_DSN = "https://key@example.ingest.sentry.io/1"
                settings.SENTRY_ENABLED = True
                settings.SENTRY_TRACES_SAMPLE_RATE = 0.0
                settings.SENTRY_SAMPLE_RATE = 1.0
                settings.SENTRY_ENVIRONMENT = "ci"
                settings.PAPER_TRADING = True
                assert sentry_service.setup_sentry(force=True) is True
                assert sentry_service.is_enabled() is True
                mock_sdk.init.assert_called_once()
                kwargs = mock_sdk.init.call_args.kwargs
                assert kwargs["dsn"].startswith("https://")
                assert kwargs["send_default_pii"] is False
                assert kwargs["traces_sample_rate"] == 0.0
