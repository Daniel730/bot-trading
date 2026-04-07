class BearAgent:
    async def evaluate(self, signal_context: dict) -> dict:
        """
        Evaluates the signal from a bearish perspective (resistance, overbought).
        """
        # Placeholder for LLM logic
        result = {
            "confidence": 0.4,
            "argument": "Approaching major resistance levels; convergence may be delayed."
        }
        
        from src.services.telemetry_service import telemetry_service
        telemetry_service.broadcast("thought", {
            "agent_name": "BEAR_AGENT",
            "signal_id": signal_context.get('signal_id', 'N/A'),
            "ticker_pair": f"{signal_context['ticker_a']}_{signal_context['ticker_b']}",
            "thought": result["argument"],
            "verdict": "BEARISH"
        })
        
        return result

bear_agent = BearAgent()
