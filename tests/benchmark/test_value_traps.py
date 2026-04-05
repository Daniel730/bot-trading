import asyncio
import os
import sys
import unittest
from typing import Dict

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.agents.fundamental_analyst import fundamental_analyst
from src.services.sec_service import sec_service
from src.config import settings

class ValueTrapBenchmark(unittest.IsolatedAsyncioTestCase):
    """
    Benchmark suite to verify the accuracy of the FundamentalAnalyst
    against historical bankruptcy/distress cases.
    """

    async def asyncSetUp(self):
        # Ensure we have a valid API key for Gemini and the model is initialized
        if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY == "mock" or not fundamental_analyst.model:
            self.skipTest("GEMINI_API_KEY not set, is mock, or model not initialized. Cannot run benchmark.")

    async def benchmark_case(self, ticker: str, name: str):
        print(f"\n[BENCHMARK] Testing {name} ({ticker})...")
        
        # 1. Fetch SEC Sections
        result = await sec_service.get_analyzed_sections(ticker)
        sections = result.get("sections", {})
        metadata = result.get("metadata")
        
        if not sections or not metadata:
            print(f"  [!] Failed to retrieve SEC sections for {ticker}")
            return None

        print(f"  [+] Retrieved {metadata['type']} filed on {metadata['date']}")
        
        # 2. Run Fundamental Analysis
        analysis = await fundamental_analyst.analyze_structural_integrity(ticker, sections, metadata)
        
        print(f"  [Score]: {analysis['integrity_score']}")
        print(f"  [Verdict]: {analysis['recommendation']}")
        print(f"  [Rationale]: {analysis['rationale']}")
        print(f"  [Risks]: {', '.join(analysis['risk_factors'])}")
        
        return analysis

    async def test_historical_value_traps(self):
        # Historical cases of bank failures in early 2023
        # These filings should ideally trigger a NO-GO or low integrity score
        # Note: Some might be delisted now or have their filings archived differently, 
        # but SEC EDGAR metadata should still be reachable if CIK is valid.
        
        cases = [
            {"ticker": "SIVBQ", "name": "Silicon Valley Bank"}, # SIVBQ is the OTC ticker
            {"ticker": "FRCB", "name": "First Republic Bank"},
            {"ticker": "SBNY", "name": "Signature Bank"},
            {"ticker": "SI", "name": "Silvergate Capital"},
            # Added a "Safe" control case
            {"ticker": "JPM", "name": "JPMorgan Chase"}
        ]
        
        results = {}
        for case in cases:
            analysis = await self.benchmark_case(case['ticker'], case['name'])
            if analysis:
                results[case['ticker']] = analysis

        # Validation logic:
        # 1. Failed banks should have lower integrity scores than JPM
        # 2. Failed banks should ideally have recommendation == "NO-GO"
        
        if "JPM" in results:
            jpm_score = results["JPM"]["integrity_score"]
            for ticker, analysis in results.items():
                if ticker == "JPM": continue
                
                # Check if failed bank is identified as risky
                # (Allowing for some variance in LLM response, but expecting < 60)
                self.assertLess(analysis['integrity_score'], jpm_score, 
                                f"{ticker} score should be lower than JPM")
                
        print("\n[BENCHMARK SUMMARY]")
        for ticker, res in results.items():
            print(f"{ticker}: {res['integrity_score']} ({res['recommendation']})")

if __name__ == "__main__":
    unittest.main()
