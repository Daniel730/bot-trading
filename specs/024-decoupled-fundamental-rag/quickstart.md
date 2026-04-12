# Quickstart: Decoupled Fundamental RAG

## Testing the Materialized View

### 1. Pre-load Cache (Manual Test)

Use `redis-cli` to set a mock score for a ticker:

```bash
redis-cli SETEX "sec:integrity:AAPL" 3600 '{"score": 85, "prosecutor_argument": "...", "defender_argument": "...", "final_reasoning": "...", "last_updated": "2026-04-05T12:00:00Z"}'
```

### 2. Verify Orchestrator Performance

Invoke the orchestrator for `AAPL` and verify the latency:

```python
import asyncio
from src.agents.orchestrator import orchestrator

async def test():
    input_data = {
        "signal_context": {
            "ticker_a": "AAPL",
            "ticker_b": "MSFT",
            "signal_id": "test-123"
        }
    }
    start = time.time()
    result = await orchestrator.ainvoke(input_data)
    end = time.time()
    print(f"Latency: {end - start:.4f}s")
    print(f"Confidence: {result['final_confidence']}")

asyncio.run(test())
```

### 3. Verify Background Worker

Run the background worker script (to be implemented) and check Redis for updates:

```bash
python scripts/update_fundamental_cache.py --ticker MSFT
redis-cli GET "sec:integrity:MSFT"
```

### 4. Verify Telemetry on Cache Miss

Remove the cache entry and invoke the orchestrator again:

```bash
redis-cli DEL "sec:integrity:TSLA"
```

Check the logs or telemetry metrics for `orchestrator.fundamental_cache_miss`.
