"""OpenTelemetry opt-in / no-op contracts (#118)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.services import otel_service


@pytest.fixture(autouse=True)
def _reset_otel():
    otel_service.reset_for_tests()
    yield
    otel_service.reset_for_tests()


def test_setup_otel_noop_when_disabled():
    with patch("src.config.settings") as settings:
        settings.OTEL_ENABLED = False
        settings.OTEL_EXPORTER_OTLP_ENDPOINT = "http://localhost:4318"
        settings.OTEL_SERVICE_NAME = "alpha-arbitrage"
        settings.OTEL_TRACES_SAMPLER_ARG = 1.0
        settings.PAPER_TRADING = True
        assert otel_service.setup_otel(force=True) is False
        assert otel_service.is_enabled() is False


def test_setup_otel_noop_when_endpoint_empty():
    with patch("src.config.settings") as settings:
        settings.OTEL_ENABLED = True
        settings.OTEL_EXPORTER_OTLP_ENDPOINT = ""
        settings.OTEL_SERVICE_NAME = "alpha-arbitrage"
        settings.OTEL_TRACES_SAMPLER_ARG = 1.0
        settings.PAPER_TRADING = True
        assert otel_service.setup_otel(force=True) is False
        assert otel_service.is_enabled() is False


def test_inmemory_spans_record_process_attributes():
    exporter = otel_service.setup_inmemory_tracer()
    with otel_service.start_span(
        "monitor.process_pair",
        attributes={"pair.id": "BTC-USD_ETH-USD"},
    ) as span:
        span.set_attribute("pair.reason", "below_entry_threshold")
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "monitor.process_pair"
    assert spans[0].attributes["pair.id"] == "BTC-USD_ETH-USD"
    assert spans[0].attributes["pair.reason"] == "below_entry_threshold"


def test_attach_detach_span_records():
    exporter = otel_service.setup_inmemory_tracer()
    handle = otel_service.attach_span("orchestrator.ainvoke", {"pair.id": "A_B"})
    otel_service.detach_span(handle, attributes={"orchestrator.confidence": 0.42})
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "orchestrator.ainvoke"
    assert spans[0].attributes["orchestrator.confidence"] == 0.42


def test_start_span_records_exception_status():
    exporter = otel_service.setup_inmemory_tracer()
    with pytest.raises(RuntimeError):
        with otel_service.start_span("brokerage.place_market_order"):
            raise RuntimeError("boom")
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].status.status_code.name == "ERROR"
