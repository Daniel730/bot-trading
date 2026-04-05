import json
import os
import asyncio
from datetime import datetime
from typing import Dict, List, Optional
import google.generativeai as genai
from pydantic import BaseModel, Field

from src.services.sec_service import SECService
from src.services.agent_log_service import AgentLogService
from src.models.arbitrage_models import FundamentalSignal
from src.services.notification_service import NotificationService
from src.utils import extract_json

class StructuralIntegrityResult(BaseModel):
    score: int = Field(ge=0, le=100)
    prosecutor_argument: str
    defender_argument: str
    final_reasoning: str

class FundamentalAnalyst:
    def __init__(self, sec_service: SECService = None, log_service: AgentLogService = None):
        self.sec_service = sec_service or SECService()
        self.log_service = log_service or AgentLogService()
        self.notification = NotificationService()
        
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        # Using flash for faster adversarial debate (P95 Target < 30s)
        self.model = genai.GenerativeModel('gemini-1.5-flash')

    async def analyze_ticker(self, signal_id: str, ticker: str) -> FundamentalSignal:
        """
        Performs an adversarial RAG analysis on a ticker's SEC filings.
        """
        print(f"[FundamentalAnalyst] Starting SEC analysis for ticker {ticker}...")
        
        # 1. Fetch SEC Content
        sec_result = await self.sec_service.get_analyzed_sections(ticker)
        if not sec_result.get("sections"):
            print(f"[FundamentalAnalyst] No filings found for {ticker}, falling back to News Analysis logic (placeholder)...")
            return self._generate_fallback_signal(signal_id, ticker)
            
        sec_sections = sec_result["sections"]
        sec_metadata = sec_result["metadata"]
        
        sections = {
            "content": f"RISK FACTORS:\n{sec_sections.get('Risk Factors') or 'N/A'}\n\nMD&A:\n{sec_sections.get('MD&A') or 'N/A'}",
            "form": sec_metadata["type"]
        }

        # 2. Adversarial Debate
        result = await self._run_adversarial_debate(ticker, sections["content"])
        
        # 3. Create and return Signal
        signal = FundamentalSignal(
            signal_id=signal_id,
            ticker=ticker,
            structural_integrity_score=result.score,
            prosecutor_argument=result.prosecutor_argument,
            defender_argument=result.defender_argument,
            final_reasoning=result.final_reasoning
        )
        
        # 4. Log to Thought Journal
        self.log_service.log_thought(
            signal_id=signal_id,
            bull=result.defender_argument,
            bear=result.prosecutor_argument,
            news=f"SEC {sections['form']} Analysis",
            verdict=f"Structural Integrity: {result.score}/100. {result.final_reasoning}",
            fundamental_impact=result.score / 100.0,
            sec_ref=sections["content"][:500] + "..."
        )
        
        return signal

    async def _run_adversarial_debate(self, ticker: str, context: str) -> StructuralIntegrityResult:
        """
        Executes the Prosecutor vs Defender pattern using Gemini.
        """
        # Truncate context if too large (NFR-002)
        max_chars = 400000 # ~100k tokens
        if len(context) > max_chars:
            context = context[:max_chars]

        prompt = f"""
        Analyze the following SEC filing sections for {ticker} from a structural risk perspective.
        
        CONTEXT:
        <context>
        {context}
        </context>

        TASK: Perform an Adversarial Debate between a 'Prosecutor' and a 'Defender'.
        
        1. PROSECUTOR: Identify specific, material structural risks (litigation, debt, loss of major customers, regulatory changes) that could explain a price divergence and invalidate an arbitrage trade. Be skeptical.
        2. DEFENDER: Identify mitigating factors, management's plans, or positive operational context that suggests the risks are manageable or already priced in.
        3. JUDGE: Evaluate both arguments and assign a 'Structural Integrity Score' (0-100).
           - 0-30: Critical risk (VETO)
           - 31-40: High risk (VETO)
           - 41-70: Moderate/Normal risk
           - 71-100: Low risk/Solid structure

        OUTPUT FORMAT (JSON ONLY):
        {{
            "score": int,
            "prosecutor_argument": "string",
            "defender_argument": "string",
            "final_reasoning": "string"
        }}
        """

        try:
            response = self.model.generate_content(prompt)
            data = extract_json(response.text)
            return StructuralIntegrityResult(**data)
        except Exception as e:
            print(f"[FundamentalAnalyst] LLM Debate failed: {e}")
            return StructuralIntegrityResult(
                score=50,
                prosecutor_argument="Analysis failed due to LLM error.",
                defender_argument="Analysis failed due to LLM error.",
                final_reasoning="Defaulting to 50 due to technical failure."
            )

    def _generate_fallback_signal(self, signal_id: str, ticker: str) -> FundamentalSignal:
        return FundamentalSignal(
            signal_id=signal_id,
            ticker=ticker,
            structural_integrity_score=50,
            prosecutor_argument="N/A - No SEC filings found.",
            defender_argument="N/A - No SEC filings found.",
            final_reasoning="Fallback to default (50) due to missing SEC data."
        )
