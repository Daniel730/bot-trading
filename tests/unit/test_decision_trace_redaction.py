"""Unit tests for Decision Flight Recorder scrubbing / redaction."""

from src.services.decision_trace_service import (
    reset_decision_recorder_for_tests,
    scrub_value,
    truncate_inputs,
)


def test_scrub_value_redacts_sensitive_keys():
    payload = {
        "api_key": "sk-live-secret",
        "password": "hunter2",
        "token": "abc",
        "ALPACA_API_SECRET": "sec",
        "z_score": 2.1,
        "nested": {"dashboard_token": "tok", "reason": "ok"},
    }
    scrubbed = scrub_value(payload)
    assert scrubbed["api_key"] == "[REDACTED]"
    assert scrubbed["password"] == "[REDACTED]"
    assert scrubbed["token"] == "[REDACTED]"
    assert scrubbed["ALPACA_API_SECRET"] == "[REDACTED]"
    assert scrubbed["z_score"] == 2.1
    assert scrubbed["nested"]["dashboard_token"] == "[REDACTED]"
    assert scrubbed["nested"]["reason"] == "ok"


def test_record_scrubs_inputs(monkeypatch):
    monkeypatch.setattr("src.config.settings.DECISION_TRACE_LEVEL", "compact")
    recorder = reset_decision_recorder_for_tests(maxsize=50)
    recorder.begin_scan("scan-scrub")
    event = recorder.record(
        stage="test",
        outcome="continue",
        reason="unit_scrub",
        inputs={"api_key": "leak-me", "pair": "A_B"},
    )
    assert event is not None
    assert event.inputs["api_key"] == "[REDACTED]"
    assert event.inputs["pair"] == "A_B"


def test_truncate_inputs_bounds_payload():
    huge = {"blob": "x" * 5000}
    trimmed = truncate_inputs(huge, max_chars=80)
    encoded = str(trimmed)
    assert len(encoded) < 200
    assert "_truncated" in trimmed or len(trimmed.get("blob", "")) <= 80
