import json
import logging

from src import monitor


def test_setup_logging_uses_configured_log_level(monkeypatch):
    monkeypatch.setattr(monitor.settings, "LOG_LEVEL", "DEBUG", raising=False)

    logger = monitor.setup_logging()

    assert logging.getLogger().level == logging.DEBUG
    assert logger.getEffectiveLevel() == logging.DEBUG


def test_setup_logging_writes_durable_structured_jsonl(monkeypatch, tmp_path):
    structured_log_path = tmp_path / "structured_logs.jsonl"
    monkeypatch.setattr(monitor, "STRUCTURED_LOG_PATH", structured_log_path, raising=False)
    monkeypatch.setattr(monitor.settings, "LOG_LEVEL", "INFO", raising=False)

    logger = monitor.setup_logging()
    logger.info("structured heartbeat")

    for handler in logging.getLogger().handlers:
        handler.flush()

    payload = json.loads(structured_log_path.read_text(encoding="utf-8"))
    assert payload["level"] == "INFO"
    assert payload["logger"] == "src.monitor"
    assert payload["message"] == "structured heartbeat"
    assert "timestamp" in payload
