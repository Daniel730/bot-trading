import os
import json
from typing import Dict, List, Optional
from src.config import settings
import google.generativeai as genai

from src.models.persistence import PersistenceManager

class FundamentalAnalyst:
    """
    Agent specialized in analyzing SEC filings to detect structural financial risks.
    Evolved from the NewsAnalyst to provide high-fidelity fundamental context.
    """
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel('gemini-1.5-pro')
        self.persistence = PersistenceManager(settings.DB_PATH)

    async def analyze_structural_integrity(self, ticker: str, sec_sections: Dict[str, str], metadata: Optional[Dict] = None) -> Dict:
        """
        Uses Gemini to analyze SEC sections and produce a risk score, with caching.
        """
        # Feature 009: Caching
        if metadata:
            cached = self.persistence.get_sec_filing(ticker, metadata['type'])
            # If the cached filing is the same one we are looking at (same date/accession)
            if cached and cached['accession_number'] == metadata['accession_number']:
                return {
                    "integrity_score": cached['integrity_score'],
                    "recommendation": "GO" if cached['integrity_score'] > 60 else "NO-GO",
                    "risk_factors": ["Cached Analysis"],
                    "rationale": cached['risk_summary']
                }

        prompt = f"""
        You are a Senior Credit Analyst validating a statistical arbitrage trade for {ticker}.
        Your goal is to determine if a recent price divergence is a "Technical Noise" (safe to trade) 
        or a "Structural Change" (dangerous value trap).

        Below are the key sections extracted from {ticker}'s latest SEC filing:

        ### Item 1A: Risk Factors
        {sec_sections.get('Item 1A', 'Not found')}

        ### Item 7: Management's Discussion & Analysis
        {sec_sections.get('Item 7', 'Not found')}

        ### Item 3: Legal Proceedings
        {sec_sections.get('Item 3', 'Not found')}

        ### Instructions:
        1. Identify any "Structural Breaks": impending bankruptcy, major fraud allegations, loss of primary customers, or $1B+ lawsuits.
        2. Evaluate "Liquidity Risk": mention of debt default, inability to meet interest payments, or "going concern" warnings.
        3. Provide a 'Structural Integrity Score' (0-100), where 100 is perfectly healthy and 0 is imminent collapse.
        4. Recommend "GO" or "NO-GO" for a mean-reversion trade.

        Return your analysis ONLY as a JSON object with these keys:
        - "integrity_score": int
        - "recommendation": "GO" | "NO-GO"
        - "risk_factors": list[str]
        - "rationale": str (max 2 sentences)
        """

        try:
            response = self.model.generate_content(prompt)
            # Simple cleanup to handle potential markdown in response
            json_text = response.text.replace('```json', '').replace('```', '').strip()
            result = json.loads(json_text)
            
            # Save to cache if we have metadata
            if metadata:
                self.persistence.save_sec_filing(
                    accession_number=metadata['accession_number'],
                    ticker=ticker,
                    filing_type=metadata['type'],
                    filing_date=metadata['date'],
                    risk_summary=result['rationale'],
                    score=result['integrity_score']
                )
            
            return result
        except Exception as e:
            print(f"FUNDAMENTAL ANALYST ERROR: {e}")
            return {
                "integrity_score": 50,
                "recommendation": "NO-GO",
                "risk_factors": ["Analysis failed"],
                "rationale": f"Internal agent error: {str(e)}"
            }

fundamental_analyst = FundamentalAnalyst()
