import json
import re
import logging

logger = logging.getLogger(__name__)

import subprocess

def check_clock_sync(max_drift_us: float = 100.0) -> bool:
    """
    Checks if the local clock is synchronized via chrony and within drift tolerance.
    FR-007: Metrics are INVALID if clock drift > 100us.
    """
    try:
        # Run chronyc tracking to get system clock status
        result = subprocess.run(['chronyc', 'tracking'], capture_output=True, text=True, timeout=2)
        if result.returncode != 0:
            logger.warning("chronyc tracking failed: chrony might not be installed or running.")
            return False
        
        # Look for "System time" line, e.g.:
        # System time     : 0.000001000 seconds slow of NTP time
        for line in result.stdout.splitlines():
            if "System time" in line:
                # Extract the numeric value (seconds)
                parts = line.split(':')
                if len(parts) < 2: continue
                
                # Extract first float found in the value part
                match = re.search(r"([-+]?\d*\.\d+|\d+)", parts[1])
                if match:
                    drift_s = abs(float(match.group(1)))
                    drift_us = drift_s * 1_000_000
                    
                    if drift_us > max_drift_us:
                        logger.error(f"Clock drift {drift_us:.2f}us exceeds tolerance {max_drift_us}us")
                        return False
                    return True
                    
        return False
    except Exception as e:
        logger.error(f"Error checking clock sync: {e}")
        return False

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
