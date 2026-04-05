# Contracts: Resolve Production Rigor Gaps

## Internal Schemas

### FrictionResult (RiskService)

```python
class FrictionResult(BaseModel):
    status: Literal["ACCEPTED", "FRICTION_REJECT"]
    amount: float
    friction_pct: float
    rejection_reason: Optional[str] = None
```

### SystemState (Persistence)

```python
class SystemState(BaseModel):
    operational_status: Literal["NORMAL", "DEGRADED_MODE"]
    consecutive_api_timeouts: int
    last_failure_timestamp: Optional[datetime] = None
```

## Service Interfaces

### DataService.get_latest_price

- **Input**: `tickers: List[str]`
- **Retry Logic**: `@retry(wait=wait_exponential(multiplier=1, min=1, max=4), stop=stop_after_attempt(3))`
- **Failure Behavior**: Returns `0.0` or raises error if retry exhausted.
