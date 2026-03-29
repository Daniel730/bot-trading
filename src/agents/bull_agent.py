class BullAgent:
    async def evaluate(self, signal_context: dict) -> dict:
        """
        Evaluates the signal from a bullish perspective (momentum, support).
        """
        # Placeholder for LLM logic
        return {
            "confidence": 0.7,
            "argument": "Strong upward momentum detected in the technical baseline."
        }

bull_agent = BullAgent()
