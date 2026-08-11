"""OpenTelemetry tracing — opt-in OTLP export; no-op when disabled.

Keeps vendor tracing separate from the dashboard WebSocket bus in
``telemetry_service``. Enable with ``OTEL_ENABLED=true`` and a non-empty
``OTEL_EXPORTER_OTLP_ENDPOINT`` (see ``.env.template`` / OPERATIONS.md).
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterator, Mapping, Optional

from opentelemetry import trace
from opentelemetry.context import attach, detach
from opentelemetry.trace import Span, Status, StatusCode, Tracer
from opentelemetry.util.types import AttributeValue

logger = logging.getLogger(__name__)

_SETUP_DONE = False
_ENABLED = False
_TRACER_NAME = "alpha-arbitrage"


def is_enabled() -> bool:
    return _ENABLED


def setup_otel(*, force: bool = False) -> bool:
    """Configure TracerProvider + OTLP exporter when opt-in settings allow.

    Returns True when the SDK exporter path was activated. Safe to call more
    than once (no-op after first successful/attempted setup unless ``force``).
    """
    global _SETUP_DONE, _ENABLED

    if _SETUP_DONE and not force:
        return _ENABLED

    from src.config import settings

    want = bool(getattr(settings, "OTEL_ENABLED", False))
    endpoint = (getattr(settings, "OTEL_EXPORTER_OTLP_ENDPOINT", "") or "").strip()
    service_name = (getattr(settings, "OTEL_SERVICE_NAME", "") or "alpha-arbitrage").strip()

    _SETUP_DONE = True

    if not want or not endpoint:
        _ENABLED = False
        logger.info(
            "OpenTelemetry disabled (OTEL_ENABLED=%s, endpoint_set=%s).",
            want,
            bool(endpoint),
        )
        return False

    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import ParentBasedTraceIdRatio

        resource = Resource.create(
            {
                "service.name": service_name,
                "deployment.environment": "paper" if settings.PAPER_TRADING else "live",
            }
        )
        sampler_arg = float(getattr(settings, "OTEL_TRACES_SAMPLER_ARG", 1.0) or 1.0)
        sampler_arg = max(0.0, min(1.0, sampler_arg))
        provider = TracerProvider(
            resource=resource,
            sampler=ParentBasedTraceIdRatio(sampler_arg),
        )
        # Constructor endpoint expects the traces path; env base URL is collector root.
        traces_endpoint = endpoint.rstrip("/")
        if not traces_endpoint.endswith("/v1/traces"):
            traces_endpoint = f"{traces_endpoint}/v1/traces"
        exporter = OTLPSpanExporter(endpoint=traces_endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _ENABLED = True
        logger.info(
            "OpenTelemetry enabled (service=%s, endpoint=%s, sample_ratio=%.3f).",
            service_name,
            endpoint,
            sampler_arg,
        )
        return True
    except Exception as exc:  # noqa: BLE001 — never block trading on telemetry
        _ENABLED = False
        logger.warning("OpenTelemetry setup failed; continuing without export: %s", exc)
        return False


def instrument_fastapi_app(app: Any) -> bool:
    """Optionally instrument a FastAPI app when OTel is enabled."""
    if not _ENABLED:
        return False
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app, excluded_urls="health,ready,metrics")
        logger.info("OpenTelemetry FastAPI instrumentation attached.")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("FastAPI OTel instrumentation skipped: %s", exc)
        return False


def get_tracer(name: str | None = None) -> Tracer:
    return trace.get_tracer(name or _TRACER_NAME)


def _normalize_attributes(
    attributes: Optional[Mapping[str, AttributeValue]],
) -> dict[str, AttributeValue]:
    if not attributes:
        return {}
    out: dict[str, AttributeValue] = {}
    for key, value in attributes.items():
        if value is None:
            continue
        out[str(key)] = value
    return out


@contextmanager
def start_span(
    name: str,
    *,
    attributes: Optional[Mapping[str, AttributeValue]] = None,
    kind: trace.SpanKind = trace.SpanKind.INTERNAL,
) -> Iterator[Span]:
    """Context-managed span; no-op tracer when SDK unset/disabled."""
    tracer = get_tracer()
    with tracer.start_as_current_span(name, kind=kind, attributes=_normalize_attributes(attributes)) as span:
        try:
            yield span
        except Exception as exc:  # noqa: BLE001
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise


class _SpanHandle:
    __slots__ = ("span", "token")

    def __init__(self, span: Span, token: Any):
        self.span = span
        self.token = token


def attach_span(
    name: str,
    attributes: Optional[Mapping[str, AttributeValue]] = None,
) -> _SpanHandle:
    """Start a span without requiring a ``with`` block (large functions)."""
    tracer = get_tracer()
    span = tracer.start_span(name, attributes=_normalize_attributes(attributes))
    token = attach(trace.set_span_in_context(span))
    return _SpanHandle(span, token)


def detach_span(
    handle: Optional[_SpanHandle],
    *,
    error: Optional[BaseException] = None,
    attributes: Optional[Mapping[str, AttributeValue]] = None,
) -> None:
    if handle is None:
        return
    span = handle.span
    try:
        if attributes:
            for key, value in _normalize_attributes(attributes).items():
                span.set_attribute(key, value)
        if error is not None:
            span.record_exception(error)
            span.set_status(Status(StatusCode.ERROR, str(error)))
    finally:
        span.end()
        detach(handle.token)


def set_span_attributes(attributes: Mapping[str, AttributeValue]) -> None:
    span = trace.get_current_span()
    if not span or not span.is_recording():
        return
    for key, value in _normalize_attributes(attributes).items():
        span.set_attribute(key, value)


# Test helpers -----------------------------------------------------------------


def reset_for_tests() -> None:
    """Reset module flags and TracerProvider (unit tests only)."""
    global _SETUP_DONE, _ENABLED
    _SETUP_DONE = False
    _ENABLED = False
    # SDK refuses set_tracer_provider() twice; clear private Once for isolated tests.
    trace._TRACER_PROVIDER = None  # type: ignore[attr-defined]
    trace._PROXY_TRACER_PROVIDER = None  # type: ignore[attr-defined]
    trace._TRACER_PROVIDER_SET_ONCE = trace.Once()  # type: ignore[attr-defined]


def setup_inmemory_tracer() -> Any:
    """Install SDK + InMemorySpanExporter for tests. Returns the exporter."""
    global _SETUP_DONE, _ENABLED

    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource.create({"service.name": "alpha-arbitrage-test"}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _SETUP_DONE = True
    _ENABLED = True
    return exporter
