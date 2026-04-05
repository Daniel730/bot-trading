# Feature Specification: Low-Budget Investor Suite

**Feature Branch**: `015-low-budget-investor-suite`  
**Created**: 2026-04-05  
**Status**: Draft  
**Input**: User description: "Don't forget to commit every code. Based on the current architecture of your bot—which already includes sophisticated components like Arbitrage, SEC RAG analysis, Kalman filters, and multiple analyst agents (bull_agent, bear_agent, fundamental_analyst)—your system is heavily geared towards algorithmic trading and institutional-style analysis. To make it feel more like a personal investor agent and to specifically support low-budget investing, you should shift some focus from high-frequency/arbitrage trading to wealth building, portfolio management, and capital efficiency. Here are the specific features and agents you can add to achieve this: 1. Features for \"Low-Budget\" Investing When dealing with a low budget (e.g., $10 to $500), traditional trading rules break down because fees eat up profits, and expensive stocks are out of reach. Fractional Share Engine: Since you are already integrating with Trading 212 (based on mcp_t212_contracts.md), you must fully leverage their fractional shares API. Action: Update your trading_models.py and brokerage_service.py to order by Value (e.g., \"Buy $10 of TSLA\") rather than by Quantity (e.g., \"Buy 1 TSLA\"). Strict Fee-Awareness Constraints: A $1 flat fee on a $10 investment is a 10% loss immediately. Action: Add a FeeAnalyzer step in your risk_service.py that calculates the percentage impact of any spread, currency conversion (FX fees), or commission. If the total friction costs exceed 1-2% of the trade value, the bot should auto-reject the trade. Automated Dollar-Cost Averaging (DCA) Service: Low-budget investors build wealth over time, not via lump sums. Action: Create a dca_service.py that allows the user to tell the bot: \"Invest $15 every Friday into my tech portfolio.\" The bot will automatically distribute the micro-budget across the chosen assets without requiring large capital. Micro-Dividend Reinvestment (DRIP): Action: Track incoming dividends. If the bot receives a $0.40 dividend, it shouldn't sit in cash. The agent should be configured to automatically sweep micro-cash back into the fractional positions to ensure continuous compounding. 2. Agents to Make it More \"Investor-Like\" (Robo-Advisor Persona) Right now, your agents are analysts (Bull, Bear, Fundamental, News). You need agents that manage people and portfolios. portfolio_manager_agent.py (The Advisor): This agent acts as the user-facing layer. Instead of just dumping stock metrics, it explains things holistically. Role: It asks the user for their risk tolerance, age, and goals (e.g., \"I have $50 a month and want to save for a car in 3 years\"). It then dictates the strategy to the other agents (e.g., telling the fundamental_analyst to only look for low-volatility dividend ETFs instead of high-risk crypto). macro_economic_agent.py (The Big Picture): An investor doesn't just look at one stock; they look at the economy. This agent monitors interest rates, inflation data, and broader market trends (SPY/QQQ trends). Role: If interest rates are high, this agent advises the portfolio_manager_agent to allocate some of the low budget into high-yield bonds or money market funds rather than risky tech. \"Explainable AI\" Investment Summaries: Real investors want to know why. Add a conversational capability where the user can open the Telegram terminal and ask: \"Why did we buy AAPL today?\" Action: Update agent_log_service.py to not just log data, but to generate a natural language \"Investment Thesis\" for every trade. E.g., \"I invested $5 in AAPL because the Fundamental Agent noted a strong balance sheet from the latest SEC RAG data, and the Bull Agent noticed positive sentiment.\" 3. Adapting Your Existing Specs for Low Budgets Arbitrage on a Budget (arbitrage_service.py): Traditional arbitrage requires huge capital to profit off tiny margins. For a low-budget bot, shift the focus to Crypto/DeFi Staking Yields or High-Volatility Micro-Arbitrage where percentage spreads are larger (even if the absolute dollar amount is small). Telegram Terminal (spec 012): Utilize the embedded Telegram terminal you are building to give the bot a conversational \"financial advisor\" voice. Allow the user to send messages like: \"I just got a $20 tip at work, put it into something safe.\" The bot parses the natural language, identifies the budget ($20), identifies the risk profile (\"safe\"), and executes fractional ETF buys. Recommended Implementation Steps: Modify src/models/trading_models.py to explicitly support order_type=\"fractional\" and amount_type=\"fiat_value\". Create src/agents/portfolio_manager_agent.py to orchestrate the existing Bear/Bull/Fundamental agents based on user budget constraints. Update prompts.py to include persona instructions for the Orchestrator/Manager to always prioritize capital preservation and zero-fee routes for accounts under a specific balance threshold. Adding complex business logic shouldn't just be about writing harder math; it should be about giving the bot contextual awareness, self-correction capabilities, and advanced risk mechanics. To make this bot a truly elite, highly intelligent investor agent (while still respecting low-budget constraints), here are advanced layers of business logic you can integrate into its calculation, execution, and memory engines. 1. Complex Calculations (The \"Brain\") A. Dynamic Value Averaging (Smart DCA) Instead of a \"dumb\" Dollar-Cost Averaging (investing exactly $10 every Friday), implement Value Averaging. The Logic: The bot calculates a target portfolio growth path (e.g., the portfolio must grow by $50/month). If the market drops and the portfolio is behind target, the bot calculates the exact micro-amount needed to buy the dip heavily. If the market surges and the portfolio is ahead of target, the bot scales back the investment or holds cash. Implementation: Create a ValueAveragingEngine that uses your existing KalmanFilter (kalman_service.py) to determine if the asset is currently mean-reverting (cheap) or overextended (expensive) before sizing the weekly micro-deposit. B. The Kelly Criterion for Micro-Position Sizing Your agents currently output \"bullish\" or \"bearish\" signals. You need to translate that into exact monetary allocations using probability. The Logic: Use the Kelly Criterion formula: f* = (p * b - q) / b (where p is probability of win, q is probability of loss, b is the odds). Implementation: The Orchestrator agent takes the confidence scores of the Fundamental, News, and Bull/Bear agents to calculate an aggregated \"Win Probability.\" If the budget is $100, the Kelly formula will mathematically dictate exactly how much of that $100 to risk on a specific fractional trade to maximize long-term compounding without risking total ruin. C. Micro-Portfolio Optimization (Sharpe & Sortino Targeting) Even with a $50 portfolio, correlation matters. The Logic: Implement a covariance matrix calculator. If the bot already bought fractional Apple (AAPL) and Microsoft (MSFT), and the user adds $5, the bot should mathematically reject buying more Tech. It calculates the Sharpe Ratio of the portfolio and buys an uncorrelated asset (like a fractional Gold ETF or Utility stock) to mathematically reduce portfolio variance. 2. Complex Executions (The \"Hands\") A. Synthetic Trailing Stops for Fractional Shares Many brokers (like Trading 212) have limitations on conditional orders for fractional shares. The Logic: The bot simulates advanced order types in its own memory. It tracks the high-water mark of a stock. If a stock drops by a dynamically calculated percentage (e.g., using Average True Range - ATR), the bot triggers a market sell via API. Implementation: In monitor.py, run a loop that constantly checks prices against an in-memory database of SyntheticOrders. B. Automated Micro-Tax-Loss Harvesting (TLH) The Logic: If the user has a fractional position at a loss, and a different position at a gain, the bot automatically sells the losing position to capture the tax deduction, and immediately rotates that capital into a highly correlated (but different) ETF to avoid wash-sale rules while maintaining market exposure. Execution: The portfolio_manager_agent continuously scans for harvestable losses that exceed the transaction friction (using the FeeAnalyzer mentioned previously). 3. Robust Memory & Action-Taking (The \"Hippocampus\") To make an agent truly intelligent, it needs to remember its mistakes, its successes, and the user's life context. A. Vectorized Trade Post-Mortems (Reinforcement Learning Loop) The Logic: Right now, bots buy/sell and forget. Your bot should do self-evaluations. 30 days after taking a trade, a ReflectionAgent evaluates the decision. Implementation: 1. When a trade is made, embed the reasoning (e.g., \"Bought AAPL because SEC RAG showed high cash flow\") into a Vector Database (like ChromaDB or Pinecone). 2. 30 days later, the bot checks the PnL. 3. If the trade lost money, the bot queries the memory: \"What was my thesis?\" It then updates a \"Weights\" file, telling the Orchestrator to trust the SEC RAG agent less in high-interest-rate environments, effectively learning from its mistakes. B. Temporal Goal Tracking & State Machines The Logic: Financial advice is highly dependent on time horizons. Implementation: Use the embedded Telegram terminal to build a stateful memory of the user. User: \"I'm planning to buy a house in 12 months.\" Bot Action: The bot parses this, updates the user's InvestmentHorizon to \"Short-Term\" in the database. Execution: This state change acts as a global override. Even if the BullAgent screams to buy an ultra-volatile crypto asset, the PortfolioManager intervenes, referencing the memory: \"User needs liquid cash in 11 months for a house. Rejecting high-volatility trade. Routing to 5% Yielding Bond ETF.\" How to wire this into your existing codebase: Enhance src/models/persistence.py: Add SQLite/PostgreSQL tables for UserLifeEvents, TradeTheses (storing the exact JSON of agent confidence scores at the time of trade), and TradeReflections. Upgrade src/services/risk_service.py: Add the KellyCriterionCalculator and CovarianceMatrix logic here. Before any trade is routed to brokerage_service.py, it must pass through these mathematical filters. Create src/agents/reflection_agent.py: A cron-job agent that wakes up once a day, looks at trades made 30 days ago, analyzes the result, and writes a performance review into the database to adjust future agent weighting."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Goal-Oriented Low-Budget DCA (Priority: P1)

As a retail investor with a limited monthly budget, I want to set a long-term goal and have the bot automatically invest small amounts into a diversified portfolio so that I can build wealth over time without worrying about high fees or manual execution.

**Why this priority**: Core of the "Low-Budget" persona. Enables capital building for users with small liquidity.

**Independent Test**: Can be tested by setting a weekly $15 investment goal via Telegram. The bot should execute fractional buys of a set of ETFs, reject any trade where fees exceed 2%, and provide a thesis summary.

**Acceptance Scenarios**:

1. **Given** a user has set a $50/month goal for "Retirement", **When** the weekly DCA trigger occurs, **Then** the bot allocates the budget across fractional shares of pre-defined uncorrelated assets.
2. **Given** a trade is proposed where the broker fee is $1 on a $10 order, **When** the FeeAnalyzer evaluates the trade, **Then** the trade is rejected as it exceeds the 2% friction threshold.

---

### User Story 2 - Intelligent Rebalancing & Reflection (Priority: P2)

As an investor, I want the bot to learn from past trades and optimize my micro-portfolio's risk-adjusted returns (Sharpe ratio) so that my small capital is managed with institutional-grade logic.

**Why this priority**: Distinguishes the bot from simple DCA apps. Provides "Smart" management of small positions.

**Independent Test**: Simulate a 30-day period where a trade thesis was stored. The Reflection Agent should evaluate the PnL and update agent weights in the database.

**Acceptance Scenarios**:

1. **Given** a portfolio with heavy tech exposure and a new $5 deposit, **When** the Covariance Matrix is calculated, **Then** the bot routes the funds to an uncorrelated asset (e.g., Gold or Utilities) to optimize variance.
2. **Given** a trade made 30 days ago resulted in a loss, **When** the Reflection Agent runs, **Then** it updates the "Weights" file to decrease the influence of the agent responsible for the failed thesis in similar market conditions.

---

### User Story 3 - Temporal Goal Tracking & Horizon Management (Priority: P3)

As a user with a specific short-term financial need, I want to tell the bot my deadline so that it automatically shifts to a capital preservation strategy as the deadline approaches.

**Why this priority**: Critical for personal finance safety. Prevents high-volatility exposure for short-term needs.

**Independent Test**: Send "I need my money for a car in 6 months" via Telegram. Verify the `InvestmentHorizon` state changes to "Short-Term" and the bot rejects high-volatility signals.

**Acceptance Scenarios**:

1. **Given** an Investment Horizon of "Short-Term", **When** a Bull signal for a volatile crypto asset is received, **Then** the Portfolio Manager rejects the trade and recommends a high-yield bond ETF instead.

---

### Edge Cases

- **What happens when a dividend is too small for any fractional buy?** (e.g., $0.01). The bot should accumulate the micro-cash until it reaches a minimum tradable threshold (e.g., $1.00) before sweeping.
- **How does the system handle a broker API failure during a DCA run?** The bot must use a retry mechanism with exponential backoff and notify the user via Telegram if the deposit remains unexecuted after 24 hours.
- **What if the user's goal is mathematically impossible with the current budget?** The Portfolio Manager should flag this in the weekly summary and suggest a higher contribution or a longer horizon.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST support ordering by fiat value (e.g., $10) via fractional share integration.
- **FR-002**: System MUST implement a `FeeAnalyzer` that rejects any trade where total friction (fees, spread, FX) exceeds 2% of trade value.
- **FR-003**: System MUST provide an automated DCA service capable of executing recurring micro-buys.
- **FR-004**: System MUST automatically reinvest micro-dividends (DRIP) into existing fractional positions.
- **FR-005**: System MUST implement a `PortfolioManagerAgent` that orchestrates other agents based on user risk/goals.
- **FR-006**: System MUST implement a `MacroEconomicAgent` to monitor interest rates and inflation for global allocation guidance.
- **FR-007**: System MUST generate a structured natural language "Investment Thesis" (min 3 sentences) for every executed trade, covering agent signal aggregation, macro state influence, and risk-veto reasoning.
- **FR-008**: System MUST implement a `ReflectionAgent` to perform vectorized trade post-mortems and update agent weights.
- **FR-009**: System MUST support stateful temporal goal tracking (Short-Term vs Long-Term horizons).
- **FR-010**: System MUST calculate position sizes using the Kelly Criterion based on aggregated agent confidence.
- **FR-011**: System MUST optimize micro-portfolios using a Covariance Matrix and Sharpe Ratio targeting.
- **FR-012**: System MUST simulate synthetic trailing stops in-memory for brokers that don't support them for fractionals.

### Key Entities *(include if feature involves data)*

- **InvestmentGoal**: Represents a user's financial target (Target Amount, Target Date, Risk Tolerance).
- **InvestmentHorizon**: Enum representing the current state of the portfolio strategy (Long-Term, Mid-Term, Short-Term, Immediate).
- **TradeThesis**: Vectorized storage of agent confidence scores, macro data, and reasoning at the time of trade.
- **SyntheticOrder**: In-memory representation of trailing stops and conditional orders for fractional shares.
- **AgentWeight**: Persisted weights assigned to each analyst agent based on historical performance (Reflection logic).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can set a financial goal and start a DCA plan in under 3 conversational steps via Telegram.
- **SC-002**: 100% of trades executed for low-budget portfolios ($< $500) must have total friction costs under 2%.
- **SC-003**: The Reflection Agent must update agent weights within 24 hours of the 30-day post-trade window closing.
- **SC-004**: Portfolio variance for "Balanced" risk profiles should be at least 15% lower than a single-asset (SPY) baseline through Covariance optimization.

## Assumptions

- **Assumption about broker support**: Trading 212 API provides sufficient granularity for fractional share execution and dividend reporting.
- **Assumption about user input**: Users will provide realistic goals and horizons via the Telegram interface.
- **Assumption about data persistence**: SQLite/PostgreSQL will be used to store vectorized trade theses for the Reflection loop.
- **Assumption about existing agents**: The Bull, Bear, Fundamental, and News agents are already functional and provide structured confidence scores.
