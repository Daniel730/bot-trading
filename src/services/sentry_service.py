"""Sentry error reporting — fail-closed when DSN is empty.

Single error product (#119). Tracing stays on OpenTelemetry (#118); Sentry
defaults to errors-only (``SENTRY_TRACES_SAMPLE_RATE=0``).
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

_SETUP_DONE = False
_ENABLED = False

_TOKENISH = re.compile(
    r"(?i)(authorization|dashboard[_-]?token|api[_-]?key|api[_-]?secret|password|totp|backup[_-]?code)"
)


def is_enabled() -> bool:
    return _ENABLED


def _scrub_value(key: str, value: Any) -> Any:
    if _TOKENISH.search(str(key or "")):
        return "[Filtered]"
    if isinstance(value, str) and len(value) > 8 and _TOKENISH.search(value):
        return "[Filtered]"
    return value


def _before_send(event: dict, hint: dict) -> Optional[dict]:
    """Drop obvious secrets from request headers / extra context."""
    del hint  # unused; keep signature for sentry-sdk
    request = event.get("request") or {}
    headers = request.get("headers")
    if isinstance(headers, dict):
        request["headers"] = {
            k: _scrub_value(k, v) for k, v in headers.items()
        }
        event["request"] = request
    extra = event.get("extra")
    if isinstance(extra, dict):
        event["extra"] = {k: _scrub_value(k, v) for k, v in extra.items()}
    return event


def _release_tag() -> str:
    for key in ("SENTRY_RELEASE", "IMAGE_TAG", "GIT_COMMIT", "SOURCE_COMMIT"):
        value = (os.getenv(key) or "").strip()
        if value:
            return value
    return "dev"


def setup_sentry(*, force: bool = False) -> bool:
    """Init sentry-sdk when DSN is non-empty. Empty DSN => no-op (fail-closed)."""
    global _SETUP_DONE, _ENABLED

    if _SETUP_DONE and not force:
        return _ENABLED

    from src.config import settings

    dsn = (getattr(settings, "SENTRY_DSN", "") or "").strip()
    enabled_flag = bool(getattr(settings, "SENTRY_ENABLED", False))
    _SETUP_DONE = True

    # Fail-closed: no DSN means never init, even if SENTRY_ENABLED=true.
    if not dsn:
        _ENABLED = False
        logger.info("Sentry disabled (SENTRY_DSN empty).")
        return False

    if not enabled_flag:
        _ENABLED = False
        logger.info("Sentry DSN set but SENTRY_ENABLED=false; skipping init.")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.asyncio import AsyncioIntegration

        traces = float(getattr(settings, "SENTRY_TRACES_SAMPLE_RATE", 0.0) or 0.0)
        traces = max(0.0, min(1.0, traces))
        sample_rate = float(getattr(settings, "SENTRY_SAMPLE_RATE", 1.0) or 1.0)
        sample_rate = max(0.0, min(1.0, sample_rate))
        environment = (getattr(settings, "SENTRY_ENVIRONMENT", "") or "").strip()
        if not environment:
            environment = "paper" if settings.PAPER_TRADING else "live"

        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            release=_release_tag(),
            send_default_pii=False,
            sample_rate=sample_rate,
            traces_sample_rate=traces,
            before_send=_before_send,
            integrations=[
                FastApiIntegration(),
                AsyncioIntegration(),
                LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
            ],
        )
        _ENABLED = True
        logger.info(
            "Sentry enabled (environment=%s, release=%s, traces_sample_rate=%.3f).",
            environment,
            _release_tag(),
            traces,
        )
        return True
    except Exception as exc:  # noqa: BLE001 — never block trading on error product
        _ENABLED = False
        logger.warning("Sentry setup failed; continuing without error reporting: %s", exc)
        return False


def reset_for_tests() -> None:
    global _SETUP_DONE, _ENABLED
    _SETUP_DONE = False
    _ENABLED = False
