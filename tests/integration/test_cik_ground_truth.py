import pytest
import asyncio
from src.services.sec_service import SECService

# Ground truth mapping for 50 major tickers (as of early 2026)
# Sources: SEC EDGAR official listings
GROUND_TRUTH = {
    "AAPL": "0000320193", "MSFT": "0000789019", "GOOGL": "0001652044", "AMZN": "0001018724", "META": "0001326801",
    "TSLA": "0001318605", "BRK-B": "0001067983", "V": "0001403161", "JPM": "0000019617", "JNJ": "0000200406",
    "WMT": "0000104169", "NVDA": "0001045810", "PG": "0000080424", "XOM": "0000034088", "MA": "0001141391",
    "HD": "0000354950", "CVX": "0000093410", "LLY": "0000059478", "PEP": "0000077476", "KO": "0000021344",
    "ABBV": "0001551152", "BAC": "0000070858", "COST": "0000909832", "AVGO": "0001730168", "TMO": "0000097745",
    "CSCO": "0000858877", "MCD": "0000063908", "ADBE": "0000796343", "DIS": "0001744489", "ACN": "0001467373",
    "LIN": "0001707925", "NFLX": "0001065280", "ABT": "0000001800", "ORCL": "0001341439", "TXN": "0000097476",
    "VZ": "0000732712", "DHR": "0000313616", "INTC": "0000050863", "PM": "0001413329", "NEE": "0000753308",
    "RTX": "0000101829", "HON": "0000773840", "AMAT": "0000006951", "LOW": "0000060667", "BKNG": "0001075531",
    "T": "0000732717", "UPS": "0001090727", "IBM": "0000051143", "CAT": "0000018230", "GE": "0000040545"
}

@pytest.fixture
def sec_svc():
    return SECService()

@pytest.mark.anyio
async def test_cik_mapping_precision(sec_svc):
    """
    Validates CIK mapping against a ground-truth dataset of 50 tickers.
    Requirement: SC-003 (100% precision).
    """
    failures = []
    total = len(GROUND_TRUTH)
    
    # We use a semaphore to limit concurrent SEC requests to respect rate limits
    semaphore = asyncio.Semaphore(5)
    
    async def check_ticker(ticker, expected_cik):
        async with semaphore:
            actual_cik = await sec_svc.get_cik_by_ticker(ticker)
            if actual_cik != expected_cik:
                failures.append(f"{ticker}: Expected {expected_cik}, got {actual_cik}")

    tasks = [check_ticker(ticker, cik) for ticker, cik in GROUND_TRUTH.items()]
    await asyncio.gather(*tasks)
    
    failure_msg = "\n".join(failures)
    assert not failures, f"CIK Mapping Precision Failed ({len(failures)}/{total}):\n{failure_msg}"
    print(f"\nSUCCESS: 100% Precision verified for {total} tickers.")
