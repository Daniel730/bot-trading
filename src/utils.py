import json
import re
import logging

logger = logging.getLogger(__name__)

def extract_json(text: str) -> dict:
    """
    Robustly extracts JSON from a string that might contain markdown or other text.
    Handles:
    - ```json ... ```
    - ``` ... ```
    - Plain text with surrounding noise
    """
    # 1. Try to find markdown blocks
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 2. Try to find the first '{' and last '}'
    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            # Try to clean up trailing commas which common in LLM output
            cleaned = re.sub(r",\s*([\]\}])", r"\1", match.group(1))
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                pass

    # 3. Last resort: direct parse
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError as e:
        logger.error(f"Failed to extract JSON from text: {e}")
        raise
