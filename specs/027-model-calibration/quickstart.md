# Quickstart: Model Calibration

This guide provides instructions for validating the performance and reliability of the arbitrage system using the newly implemented calibration tools.

## High-Precision Latency Monitoring

1. **Start the Execution Engine (Java)**:
   ```bash
   cd execution-engine && ./gradlew run
   ```
2. **Start the Python Orchestrator**:
   ```bash
   python main.py
   ```
3. **Trigger a Signal Burst**:
   ```bash
   python scripts/simulate_burst.py --count 100
   ```
4. **View Real-Time Latency Metrics (Redis)**:
   ```bash
   redis-cli HGETALL latency_metrics:<signal_id>
   ```

## Shadow Mode Fill Accuracy Audit

1. **Ensure Shadow Mode is Active** (`DRY_RUN=true`).
2. **Perform Calibration Analysis**:
   ```bash
   python scripts/calibration_analysis.py --days 1
   ```
3. **Check results in PostgreSQL**:
   ```sql
   SELECT * FROM fill_analysis ORDER BY audit_timestamp DESC;
   ```

## Redis Idempotency Stress Test

1. **Run the Stress Test Suite**:
   ```bash
   cd execution-engine && ./gradlew test --tests IdempotencyStressTest
   ```
2. **Verify zero double-fire events**:
   ```bash
   grep "Duplicate Request" execution-engine.log | wc -l
   ```
