# Research: Atomic Multi-Leg Execution

## Unknowns & Investigations

### 1. Multi-Leg gRPC Processing in Java
**Investigation**: How to handle the `repeated ExecutionLeg legs` field in the Java gRPC implementation of `ExecutionServiceImpl`.
**Findings**: The Protobuf compiler generates `getLegsList()` and `getLegsCount()` methods. We can iterate through the list to process each leg.
**Decision**: Use a standard `for` loop over `request.getLegsList()` to perform pre-execution validation on all legs.

### 2. Atomic Validation Logic (All-or-Nothing)
**Investigation**: How to ensure that no leg is executed if any other leg fails validation.
**Findings**: The existing logic was "calculate then execute" for a single leg. To support atomicity, we must separate the **Validation Phase** from the **Execution Phase**.
**Decision**: 
- **Validation Phase**: Iterate through all legs, calculate VWAP, and check slippage/depth. Store results in a temporary list.
- **Execution Phase**: Only if all legs pass validation, proceed to broker integration and audit persistence.
- **Error Phase**: If any leg fails, catch the exception, log the failure, and persist "REJECTED" audits for ALL legs in the request.

### 3. Efficient Multi-Leg Audit Persistence with R2DBC
**Investigation**: How to save multiple rows to PostgreSQL using R2DBC without opening multiple connections or sending sequential individual inserts.
**Findings**: The `io.r2dbc.spi.Statement` interface supports batching via the `add()` method. This allows binding multiple sets of parameters to a single statement.
**Decision**: Implement `saveAudits(UUID signalId, String pairId, List<TradeAudit> audits, String status, long latencyMs)` in `TradeLedgerRepository`. Use a loop to bind each audit and call `statement.add()` between them.

### 4. Backward Compatibility for Reporting
**Investigation**: The `ExecutionResponse` only has one `actual_vwap` field. Which leg's VWAP should be returned?
**Findings**: Most arbitrage strategies consider the first leg (index 0) as the primary entry or the "lead" leg for spread calculation.
**Decision**: Return the `actual_vwap` of `legs(0)` in the response to avoid breaking existing downstream consumers (e.g., the Python agent's logging).

## Rationale
- **Capital Preservation**: The primary driver is Principle I of the Constitution. Naked directional exposure is a critical risk.
- **Auditability**: Principle III requires "White Box" operation. Logging failed legs is just as important as logging successful ones for strategy tuning.

## Alternatives Considered
- **Sequential Execution**: Execute Leg A, then Leg B. *Rejected* because Leg A could fill while Leg B fails, leaving an unhedged position.
- **Individual `saveAudit` calls**: Use `Flux.fromIterable(audits).flatMap(repo::saveAudit)`. *Rejected* as it is less efficient than R2DBC statement batching.
