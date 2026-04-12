# Quickstart: Audit Bug Fixes & System Hardening

This guide explains how to verify the 17 audit bug fixes.

## Prerequisites

- **Environment**: Linux or Docker.
- **Python**: 3.11 or 3.12.
- **Java**: JDK 17+ (for execution-engine).
- **Environment Variables**:
  ```bash
  export POSTGRES_PASSWORD="secure_pass"
  export DASHBOARD_TOKEN="secure_token"
  export REGION="US"
  ```

## Verification Steps

### 1. Python Service Fixes (T-01, A-01, S-01, S-02, S-03, A-03, S-07, S-08)

Run the dedicated audit verification suite:
```bash
pytest tests/unit/test_risk_service.py tests/unit/test_cash_service.py tests/unit/test_monitor_concurrency.py
```
*Note: `test_monitor_concurrency.py` is a new test case for A-03.*

### 2. Java Execution Engine Fixes (J-01, J-02, J-03)

Build and run integration tests for the Java service:
```bash
cd execution-engine
./gradlew clean test
```
*Note: Tests verify gRPC response behavior (onCompleted exactly once) and null handling.*

### 3. Modernization (Python 3.12+)

Verify loop access behavior:
```bash
python3 -m src.monitor --check-loop
```

### 4. Infrastructure (Docker)

Verify Docker healthcheck status:
```bash
docker-compose ps
# Look for 'healthy' status in the 'Status' column
```

## Critical Health Checks

1. **Security**: Confirm the system fails to start if `POSTGRES_PASSWORD` is not set.
2. **Dashboard**: Confirm `DEV_MODE=True` still requires the `DASHBOARD_TOKEN` query parameter.
3. **Execution**: Confirm `getLatestBook()` returning null results in a proper gRPC error response, not a crash.
