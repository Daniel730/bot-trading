import os
import json
from typing import Dict, List
from src.config import settings
import google.generativeai as genai

class FundamentalAnalyst:
    """
    Agent specialized in analyzing SEC filings to detect structural financial risks.
    Evolved from the NewsAnalyst to provide high-fidelity fundamental context.
    """
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel('gemini-1.5-pro')

    async def analyze_structural_integrity(self, ticker: str, sec_sections: Dict[str, str]) -> Dict:
        """
        Uses Gemini to analyze SEC sections and produce a risk score.
        """
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
            return json.loads(json_text)
        except Exception as e:
            print(f"FUNDAMENTAL ANALYST ERROR: {e}")
            return {
                "integrity_score": 50,
                "recommendation": "NO-GO",
                "risk_factors": ["Analysis failed"],
                "rationale": f"Internal agent error: {str(e)}"
            }

fundamental_analyst = FundamentalAnalyst()
