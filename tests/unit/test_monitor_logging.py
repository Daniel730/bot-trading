import logging

from src import monitor


def test_setup_logging_uses_configured_log_level(monkeypatch):
    monkeypatch.setattr(monitor.settings, "LOG_LEVEL", "DEBUG", raising=False)

    logger = monitor.setup_logging()

    assert logging.getLogger().level == logging.DEBUG
    assert logger.getEffectiveLevel() == logging.DEBUG
