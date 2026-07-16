"""Unit tests for Decision Flight Recorder ring buffer + export."""

import json
from pathlib import Path

from src.services.decision_trace_service import reset_decision_recorder_for_tests


def test_ring_overflow_drops_oldest(monkeypatch):
    monkeypatch.setattr("src.config.settings.DECISION_TRACE_LEVEL", "compact")
    recorder = reset_decision_recorder_for_tests(maxsize=3)
    recorder.begin_scan("scan-overflow")
    for i in range(5):
        recorder.record(
            stage="test",
            outcome="skip",
            reason="missing_price",
            inputs={"i": i},
        )
    events = recorder.events()
    assert len(events) == 3
    assert events[0].inputs["i"] == 2
    assert events[-1].inputs["i"] == 4


def test_compact_omits_routine_skips(monkeypatch):
    monkeypatch.setattr("src.config.settings.DECISION_TRACE_LEVEL", "compact")
    recorder = reset_decision_recorder_for_tests(maxsize=50)
    recorder.begin_scan("scan-compact")
    recorder.record(stage="zscore_gate", outcome="skip", reason="below_entry_threshold")
    recorder.record(stage="pre_signal", outcome="skip", reason="missing_price")
    reasons = [e.reason for e in recorder.events()]
    assert "below_entry_threshold" not in reasons
    assert "missing_price" in reasons


def test_verbose_keeps_routine_skips(monkeypatch):
    monkeypatch.setattr("src.config.settings.DECISION_TRACE_LEVEL", "verbose")
    recorder = reset_decision_recorder_for_tests(maxsize=50)
    recorder.begin_scan("scan-verbose")
    recorder.record(stage="zscore_gate", outcome="skip", reason="below_entry_threshold")
    assert any(e.reason == "below_entry_threshold" for e in recorder.events())


def test_off_records_nothing(monkeypatch):
    monkeypatch.setattr("src.config.settings.DECISION_TRACE_LEVEL", "off")
    recorder = reset_decision_recorder_for_tests(maxsize=50)
    recorder.begin_scan("scan-off")
    assert recorder.record(stage="test", outcome="skip", reason="missing_price") is None
    assert recorder.events() == []


def test_anomaly_promotes_neighbors(monkeypatch):
    monkeypatch.setattr("src.config.settings.DECISION_TRACE_LEVEL", "compact")
    recorder = reset_decision_recorder_for_tests(maxsize=100)
    recorder.begin_scan("scan-promote")
    for i in range(5):
        recorder.record(stage="test", outcome="skip", reason="missing_price", inputs={"i": i})
    recorder.record(stage="process_pair", outcome="anomaly", reason="exception")
    promoted = [e for e in recorder.events() if e.promoted]
    assert len(promoted) >= 2
    assert any(e.reason == "exception" for e in promoted)


def test_record_and_export_pack(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("src.config.settings.DECISION_TRACE_LEVEL", "compact")
    recorder = reset_decision_recorder_for_tests(maxsize=100)
    scan_id = recorder.begin_scan("scan-export")
    recorder.set_pair_id("AAA_BBB")
    signal_id = "11111111-1111-4111-8111-111111111111"
    recorder.set_signal_id(signal_id)
    recorder.record(
        stage="signal",
        outcome="continue",
        reason="entry_band",
        inputs={"z_score": 2.5},
        signal_id=signal_id,
    )
    recorder.record(
        stage="orchestrator",
        outcome="veto",
        reason="orchestrator_veto",
        inputs={"confidence": 0.2, "api_key": "nope"},
        signal_id=signal_id,
    )
    recorder.record(
        stage="process_pair",
        outcome="anomaly",
        reason="exception",
        inputs={"error_type": "ValueError"},
        signal_id=signal_id,
    )

    pack = recorder.export_pack(
        out_dir=tmp_path,
        signal_id=signal_id,
        journal_refs={"agent_reasoning_trace_id": signal_id},
    )
    assert (pack / "manifest.json").exists()
    assert (pack / "trail.jsonl").exists()
    assert (pack / "summary.md").exists()
    assert (pack / "AGENT_HINT.md").exists()

    manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["event_count"] >= 2
    assert manifest["filter"]["signal_id"] == signal_id
    assert scan_id

    lines = (pack / "trail.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert lines
    first = json.loads(lines[0])
    assert "api_key" not in json.dumps(first) or "[REDACTED]" in json.dumps(
        [json.loads(line) for line in lines]
    )
    hint = (pack / "AGENT_HINT.md").read_text(encoding="utf-8")
    assert "AgentReasoning" in hint
    assert "TradeJournal" in hint


def test_export_last_anomaly(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("src.config.settings.DECISION_TRACE_LEVEL", "compact")
    recorder = reset_decision_recorder_for_tests(maxsize=100)
    recorder.begin_scan("scan-last")
    recorder.record(stage="a", outcome="skip", reason="missing_price")
    recorder.record(stage="b", outcome="anomaly", reason="orchestrator_timeout")
    pack = recorder.export_pack(out_dir=tmp_path, last_anomaly=True)
    manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["event_count"] >= 1
    assert manifest["filter"]["last_anomaly"] is True
