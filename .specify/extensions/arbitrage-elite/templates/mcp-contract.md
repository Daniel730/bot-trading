# MCP Tool Contract: [TOOL_NAME]

**Feature**: [###-feature-name] | **Server**: FastMCP (Arbitrage-Elite-Engine)
**Purpose**: Standardized definition for Gemini CLI / LangGraph consumption.

## 1. Interface Definition
- **Name**: `[tool_name]`
- **Arguments**:
  - `[arg_name]` (`[type]`): [description]
- **Returns**: `[type]`
- **Output Format**: [JSON / Plain Text / SSE]

## 2. Constitutional Compliance
- **Principle II (Mechanical Rationality)**: [Does this tool perform deterministic calculation or data fetch?]
- **Principle III (Auditability)**: [Does this tool log reasoning to the Thought Journal?]
- **Principle IV (Strict Operation)**: [Does this tool enforce NYSE/NASDAQ hours if applicable?]

## 3. Implementation Blueprint
- **Service**: [e.g., src/services/brokerage_service.py]
- **Logic**: [Brief pseudo-code or description of the tool's behavior]

## 4. Error Handling
- **Edge Case 1**: [e.g., API Timeout] -> [Response]
- **Edge Case 2**: [e.g., Invalid Ticker] -> [Response]
