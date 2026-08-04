import sys
from types import SimpleNamespace

import pytest

# edgartools may be absent in thin local venvs; stub before importing SEC modules.
sys.modules.setdefault("edgar", SimpleNamespace(set_identity=lambda *_a, **_k: None, Company=object))

from src.services.sec_service import (
    SECService,
    SECUnreachableException,
    _is_sec_unreachable_error,
)


def test_is_sec_unreachable_error_markers():
    assert _is_sec_unreachable_error(TimeoutError("timed out")) is True
    assert _is_sec_unreachable_error(ConnectionError("connection reset")) is True
    assert _is_sec_unreachable_error(RuntimeError("unexpected parse failure")) is False


@pytest.mark.asyncio
async def test_fetch_latest_filing_metadata_raises_on_unreachable(monkeypatch):
    service = SECService.__new__(SECService)
    service._initialized = True
    service.persistence = None

    class BoomCompany:
        def __init__(self, _ticker):
            raise ConnectionError("Failed to resolve sec.gov")

    monkeypatch.setattr("src.services.sec_service.Company", BoomCompany)

    with pytest.raises(SECUnreachableException):
        await service.fetch_latest_filing_metadata("AAPL", "10-K")
