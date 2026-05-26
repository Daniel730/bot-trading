import logging

from src.services.agent_log_service import AgentLogService


class FakePersistence:
    def __init__(self):
        self.events = []
        self.thoughts = []

    def log_event(self, **kwargs):
        self.events.append(kwargs)

    def log_thought(self, **kwargs):
        self.thoughts.append(kwargs)


def test_agent_log_service_diagnostics_use_logger_not_stdout(caplog, capsys):
    service = AgentLogService.__new__(AgentLogService)
    service.persistence = FakePersistence()

    with caplog.at_level(logging.INFO, logger="src.services.agent_log_service"):
        service.log_fractional_trade(
            ticker="AAPL",
            amount=25.0,
            quantity=0.1,
            price=250.0,
            side="BUY",
            friction={"fees": 0.0},
        )

    assert capsys.readouterr().out == ""
    assert "Fractional trade logged for AAPL" in caplog.text
    assert service.persistence.events[0]["source"] == "FRACTIONAL_ENGINE"
