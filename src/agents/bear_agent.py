class BearAgent:
    async def evaluate(self, signal_context: dict) -> dict:
        """
        Evaluates the signal from a bearish perspective (resistance, overbought).
        """
        # Placeholder for LLM logic
        return {
            "confidence": 0.4,
            "argument": "Approaching major resistance levels; convergence may be delayed."
        }

bear_agent = BearAgent()
