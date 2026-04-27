import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Numeric, DateTime, JSON, Enum, func, Boolean, Integer, Text, ForeignKey
import enum
from datetime import datetime
from typing import Optional, List, Dict
import uuid
from src.config import settings

class Base(DeclarativeBase):
    pass

class OrderSide(enum.Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderStatus(enum.Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    OPEN = "OPEN"
    CLOSED = "CLOSED"

class AchievabilityStatus(enum.Enum):
    PERFECT = "PERFECT"
    ACCEPTABLE = "ACCEPTABLE"
    UNACHIEVABLE = "UNACHIEVABLE"

class DecisionType(enum.Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    VETO = "VETO"

class FrequencyType(enum.Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"

class MarketRegime(enum.Enum):
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    VOLATILE = "VOLATILE"
    SIDEWAYS = "SIDEWAYS"
    STABLE = "STABLE"

class ExitReason(enum.Enum):
    TAKE_PROFIT = "TAKE_PROFIT"
    STOP_LOSS = "STOP_LOSS"
    KILL_SWITCH = "KILL_SWITCH"
    MANUAL = "MANUAL"
    TIMEOUT = "TIMEOUT"

class TradeLedger(Base):
    __tablename__ = "trade_ledger"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    order_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    signal_id: Mapped[Optional[uuid.UUID]] = mapped_column(index=True)
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    side: Mapped[OrderSide] = mapped_column(Enum(OrderSide))
    quantity: Mapped[float] = mapped_column(Numeric(20, 10))
    price: Mapped[float] = mapped_column(Numeric(20, 10))
    fee: Mapped[float] = mapped_column(Numeric(20, 10), default=0.0)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus), default=OrderStatus.COMPLETED)
    venue: Mapped[str] = mapped_column(String(20), server_default="T212", index=True)
    execution_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, name="metadata")
    latency_rtt_ns: Mapped[Optional[int]] = mapped_column(Integer)
    clock_sync_status: Mapped[Optional[bool]] = mapped_column(Boolean)

class FillAnalysis(Base):
    __tablename__ = "fill_analysis"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    trade_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trade_ledger.id"), index=True)
    theoretical_mid_price: Mapped[float] = mapped_column(Numeric(20, 10))
    vwap_fill_price: Mapped[float] = mapped_column(Numeric(20, 10))
    slippage_bps: Mapped[int] = mapped_column(Integer)
    achievability_status: Mapped[AchievabilityStatus] = mapped_column(Enum(AchievabilityStatus))
    audit_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class AgentReasoning(Base):
    __tablename__ = "agent_reasoning"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    trace_id: Mapped[uuid.UUID] = mapped_column(index=True)
    agent_name: Mapped[str] = mapped_column(String(50))
    ticker_pair: Mapped[str] = mapped_column(String(50))
    thought_journal: Mapped[str] = mapped_column(Text, name="thought_journal")
    risk_metrics: Mapped[Optional[dict]] = mapped_column(JSON)
    decision: Mapped[DecisionType] = mapped_column(Enum(DecisionType))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

class AgentPerformance(Base):
    __tablename__ = "agent_performance"
    
    agent_name: Mapped[str] = mapped_column(String(50), primary_key=True)
    successes: Mapped[int] = mapped_column(Integer, default=1)
    failures: Mapped[int] = mapped_column(Integer, default=1)
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class DCASchedules(Base):
    __tablename__ = "dca_schedules"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    target_ticker: Mapped[str] = mapped_column(String(20))
    amount: Mapped[float] = mapped_column(Numeric(20, 10))
    frequency: Mapped[FrequencyType] = mapped_column(Enum(FrequencyType))
    next_run: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    day_of_week: Mapped[Optional[int]] = mapped_column(Integer)
    day_of_month: Mapped[Optional[int]] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(default=True)
    config: Mapped[Optional[dict]] = mapped_column(JSON)

class TradingPair(Base):
    __tablename__ = "trading_pairs"
    
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    ticker_a: Mapped[str] = mapped_column(String(20))
    ticker_b: Mapped[str] = mapped_column(String(20))
    hedge_ratio: Mapped[float] = mapped_column(Numeric(20, 10), default=0.0)
    is_cointegrated: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(20), default="Active")

class SystemState(Base):
    __tablename__ = "system_state"
    
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)

class PortfolioPerformance(Base):
    __tablename__ = "portfolio_performance"
    
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True, server_default=func.now())
    total_equity: Mapped[float] = mapped_column(Numeric(20, 10))
    daily_return: Mapped[float] = mapped_column(Numeric(20, 10))
    cumulative_drawdown: Mapped[float] = mapped_column(Numeric(20, 10))
    sharpe_ratio: Mapped[float] = mapped_column(Numeric(20, 10))

class MarketRegimeHistory(Base):
    __tablename__ = "market_regime_history"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    regime: Mapped[MarketRegime] = mapped_column(Enum(MarketRegime))
    confidence: Mapped[float] = mapped_column(Numeric(5, 4))
    features: Mapped[Optional[dict]] = mapped_column(JSON)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

class TradeJournal(Base):
    __tablename__ = "trade_journal"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    signal_id: Mapped[uuid.UUID] = mapped_column(index=True, unique=True)
    entry_regime: Mapped[MarketRegime] = mapped_column(Enum(MarketRegime))
    exit_reason: Mapped[Optional[ExitReason]] = mapped_column(Enum(ExitReason))
    efficiency_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    reflection_text: Mapped[Optional[str]] = mapped_column(Text)
    metrics_at_entry: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class OptimizedAllocation(Base):
    __tablename__ = "optimized_allocations"
    
    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    target_weight: Mapped[float] = mapped_column(Numeric(10, 6))
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class UniverseCandidate(Base):
    __tablename__ = "universe_candidates"
    
    pair_id: Mapped[str] = mapped_column(String(50), primary_key=True) # ticker_a_ticker_b
    sector: Mapped[str] = mapped_column(String(50))
    p_value: Mapped[float] = mapped_column(Numeric(10, 6))
    correlation: Mapped[float] = mapped_column(Numeric(10, 6))
    expected_return: Mapped[float] = mapped_column(Numeric(10, 6)) # Projected annual return
    volatility: Mapped[float] = mapped_column(Numeric(10, 6))
    sortino: Mapped[float] = mapped_column(Numeric(10, 6))
    found_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class PersistenceService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PersistenceService, cls).__new__(cls)
            db_url = f"postgresql+asyncpg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
            cls._instance.engine = create_async_engine(
                db_url,
                pool_size=20,
                max_overflow=10,
                pool_pre_ping=True
            )
            cls._instance.AsyncSessionLocal = async_sessionmaker(
                cls._instance.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
        return cls._instance

    async def init_db(self):
        """Initializes the database schema and performs necessary migrations."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            
            # Runtime Migration: Add 'venue' column if it doesn't exist
            # We use a raw SQL block for safety against existing data.
            try:
                from sqlalchemy import text
                await conn.execute(text("ALTER TABLE trade_ledger ADD COLUMN IF NOT EXISTS venue VARCHAR(20) DEFAULT 'T212'"))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_trade_ledger_venue ON trade_ledger (venue)"))
            except Exception as e:
                logger.warning(f"PersistenceService: Migration notice (venue column): {e}")

    async def log_trade(self, trade_data: dict):
        """Logs a trade execution to the ledger with automatic venue detection."""
        if 'signal_id' in trade_data and isinstance(trade_data['signal_id'], str):
            trade_data['signal_id'] = uuid.UUID(trade_data['signal_id'])
            
        # Automatic Venue Detection
        if "venue" not in trade_data or not trade_data["venue"]:
            ticker = trade_data.get("ticker", "").upper()
            trade_data["venue"] = "WEB3" if "-USD" in ticker else "T212"

        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                trade = TradeLedger(**trade_data)
                session.add(trade)

    async def log_reasoning(self, reasoning_data: dict):
        """Logs an agent reasoning event."""
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                reasoning = AgentReasoning(**reasoning_data)
                session.add(reasoning)

    async def save_portfolio_performance(self, perf_data: dict):
        """Saves daily portfolio performance metrics (Sharpe, Drawdown)."""
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                perf = PortfolioPerformance(**perf_data)
                session.add(perf)

    async def log_market_regime(self, regime_data: dict):
        """Logs current market regime classification."""
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                entry = MarketRegimeHistory(**regime_data)
                session.add(entry)

    async def get_latest_market_regime(self) -> Optional[dict]:
        """Retrieves the most recent market regime classification."""
        from sqlalchemy import select, desc
        async with self.AsyncSessionLocal() as session:
            stmt = select(MarketRegimeHistory).order_by(desc(MarketRegimeHistory.timestamp)).limit(1)
            result = await session.execute(stmt)
            regime = result.scalar_one_or_none()
            if regime:
                return {
                    "regime": regime.regime.value,
                    "confidence": float(regime.confidence),
                    "features": regime.features
                }
            return None

    async def log_trade_journal(self, journal_data: dict):
        """Logs or updates a trade journal entry."""
        from sqlalchemy.dialects.postgresql import insert
        # Safety net: TradeJournal.entry_regime is NOT NULL.
        # Some callers may submit partial payloads (reflection updates).
        if "entry_regime" not in journal_data or journal_data.get("entry_regime") is None:
            fallback_regime = MarketRegime.STABLE
            try:
                latest = await self.get_latest_market_regime()
                if latest and latest.get("regime"):
                    fallback_regime = MarketRegime(latest["regime"])
            except Exception:
                pass
            journal_data["entry_regime"] = fallback_regime
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                stmt = insert(TradeJournal).values(**journal_data)
                # If signal_id exists, update values
                update_dict = {k: v for k, v in journal_data.items() if k != 'signal_id'}
                stmt = stmt.on_conflict_do_update(
                    index_elements=[TradeJournal.signal_id],
                    set_=update_dict
                )
                await session.execute(stmt)

    async def close_trade(self, signal_id: uuid.UUID, exit_prices: dict, pnl: float, exit_reason: Optional[ExitReason] = None):
        """Marks trades with a specific signal_id as CLOSED and records PnL."""
        from sqlalchemy import update
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                stmt = update(TradeLedger).where(TradeLedger.signal_id == signal_id).values(
                    status=OrderStatus.CLOSED,
                    metadata_json={"exit_prices": exit_prices, "pnl": pnl, "exit_reason": exit_reason.value if exit_reason else None}
                )
                await session.execute(stmt)
                
                # Update TradeJournal if it exists
                if exit_reason:
                    stmt_j = update(TradeJournal).where(TradeJournal.signal_id == signal_id).values(
                        exit_reason=exit_reason
                    )
                    await session.execute(stmt_j)

        # Trigger reflection in the background
        from src.agents.reflection_agent import reflection_agent
        asyncio.create_task(reflection_agent.reflect_on_trade(str(signal_id)))

    async def get_open_signals(self, venue: Optional[str] = None) -> List[dict]:
        """
        Retrieves all currently OPEN positions grouped by signal_id, 
        optionally filtered by venue.
        """
        from sqlalchemy import select
        async with self.AsyncSessionLocal() as session:
            # We fetch all OPEN orders that represent trades
            stmt = select(TradeLedger).where(TradeLedger.status == OrderStatus.OPEN)
            if venue:
                stmt = stmt.where(TradeLedger.venue == venue)
            result = await session.execute(stmt)
            trades = result.scalars().all()
            
            # Map grouped by signal_id
            signals = {}
            for t in trades:
                sig = str(t.signal_id)
                if sig not in signals:
                    signals[sig] = {
                        "signal_id": sig,
                        "legs": [],
                        "total_cost_basis": 0.0,
                        "venue": t.venue
                    }
                signals[sig]["legs"].append({
                    "ticker": t.ticker,
                    "side": t.side.value,
                    "quantity": float(t.quantity),
                    "price": float(t.price),
                    "execution_timestamp": t.execution_timestamp
                })
                signals[sig]["total_cost_basis"] += float(t.quantity * t.price)
                
            return list(signals.values())

    async def get_active_dca_schedules(self) -> List[DCASchedules]:
        """Retrieves active DCA schedules."""
        from sqlalchemy import select
        async with self.AsyncSessionLocal() as session:
            stmt = select(DCASchedules).where(DCASchedules.is_active == True)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def update_dca_next_run(self, schedule_id: uuid.UUID, next_run: datetime):
        """Updates the next execution time for a schedule."""
        from sqlalchemy import update
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                stmt = update(DCASchedules).where(DCASchedules.id == schedule_id).values(next_run=next_run)
                await session.execute(stmt)

    async def set_system_state(self, key: str, value: str):
        """Updates a persistent system state value."""
        from sqlalchemy.dialects.postgresql import insert
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                stmt = insert(SystemState).values(key=key, value=value)
                stmt = stmt.on_conflict_do_update(
                    index_elements=[SystemState.key],
                    set_=dict(value=value)
                )
                await session.execute(stmt)

    async def get_system_state(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Retrieves a persistent system state value."""
        from sqlalchemy import select
        async with self.AsyncSessionLocal() as session:
            stmt = select(SystemState.value).where(SystemState.key == key)
            result = await session.execute(stmt)
            val = result.scalar_one_or_none()
            return val if val is not None else default

    async def get_active_trading_universe(self) -> List[str]:
        """Returns a unique list of all tickers currently in active trading pairs."""
        from sqlalchemy import select
        async with self.AsyncSessionLocal() as session:
            # Query all tickers from both A and B sides of the pairs
            stmt_a = select(TradingPair.ticker_a).where(TradingPair.status == "Active")
            stmt_b = select(TradingPair.ticker_b).where(TradingPair.status == "Active")
            
            result_a = await session.execute(stmt_a)
            result_b = await session.execute(stmt_b)
            
            tickers = set(result_a.scalars().all()) | set(result_b.scalars().all())
            return sorted(list(tickers))

    async def get_daily_returns(self, venue: Optional[str] = None) -> Dict[str, float]:
        """Returns aggregated daily PnL mapping of form {'YYYY-MM-DD': pnl_sum} based on CLOSED trades."""
        from sqlalchemy import select
        async with self.AsyncSessionLocal() as session:
            stmt = select(TradeLedger).where(TradeLedger.status == OrderStatus.CLOSED)
            if venue:
                stmt = stmt.where(TradeLedger.venue == venue)
            result = await session.execute(stmt)
            trades = result.scalars().all()
            
            # Deduplicate by signal_id because close_trade writes the same
            # signal-level pnl into each closed leg metadata row.
            signal_day_pnl: Dict[tuple[str, str], float] = {}
            for t in trades:
                if not t.metadata_json or "pnl" not in t.metadata_json:
                    continue
                day_str = t.execution_timestamp.strftime("%Y-%m-%d")
                sig = str(t.signal_id) if t.signal_id is not None else str(t.id)
                key = (day_str, sig)
                if key not in signal_day_pnl:
                    signal_day_pnl[key] = float(t.metadata_json["pnl"])

            daily_pnl: Dict[str, float] = {}
            for (day_str, _sig), pnl in signal_day_pnl.items():
                daily_pnl[day_str] = daily_pnl.get(day_str, 0.0) + pnl

            return daily_pnl

    async def get_total_pnl(self, venue: Optional[str] = None) -> float:
        """Returns the absolute sum of all closed trade PnL."""
        daily_returns = await self.get_daily_returns(venue=venue)
        return sum(daily_returns.values())

    async def get_daily_pnl_for_date(self, date_str: str, venue: Optional[str] = None) -> float:
        """Returns realized PnL for one UTC date (YYYY-MM-DD)."""
        daily_returns = await self.get_daily_returns(venue=venue)
        return float(daily_returns.get(date_str, 0.0))

    async def get_current_investment(self, venue: Optional[str] = None) -> float:
        """Returns open-position cost basis across all active signals."""
        open_signals = await self.get_open_signals(venue=venue)
        return float(sum(float(sig.get("total_cost_basis", 0.0)) for sig in open_signals))

    async def get_agent_metrics(self, agent_name: str) -> tuple[int, int]:
        """Returns (successes, failures) for Thompson Sampling."""
        from sqlalchemy import select
        async with self.AsyncSessionLocal() as session:
            stmt = select(AgentPerformance).where(AgentPerformance.agent_name == agent_name)
            result = await session.execute(stmt)
            ap = result.scalar_one_or_none()
            if ap:
                return ap.successes, ap.failures
            return 1, 1 # Beta(1,1) uniform prior

    async def update_agent_metrics(self, agent_name: str, is_success: bool):
        """Increments success or failure count for a given agent via an UPSERT."""
        from sqlalchemy.dialects.postgresql import insert
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                stmt = insert(AgentPerformance).values(
                    agent_name=agent_name,
                    successes=2 if is_success else 1,
                    failures=1 if is_success else 2
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=[AgentPerformance.agent_name],
                    set_=dict(
                        successes=AgentPerformance.successes + (1 if is_success else 0),
                        failures=AgentPerformance.failures + (0 if is_success else 1)
                    )
                )
                await session.execute(stmt)

    async def get_active_portfolio_tickers(self) -> List[str]:
        """Returns a list of unique tickers with COMPLETED (open) trades in the ledger."""
        from sqlalchemy import select, distinct
        async with self.AsyncSessionLocal() as session:
            stmt = select(distinct(TradeLedger.ticker)).where(TradeLedger.status == OrderStatus.COMPLETED)
            result = await session.execute(stmt)
            return [row[0] for row in result.all()]

    async def get_optimized_allocations(self) -> Dict[str, float]:
        """Returns target weights for all optimized tickers."""
        from sqlalchemy import select
        async with self.AsyncSessionLocal() as session:
            stmt = select(OptimizedAllocation)
            result = await session.execute(stmt)
            return {row[0].ticker: float(row[0].target_weight) for row in result.all()}

    async def get_existing_candidate_ids(self, sector: str) -> List[str]:
        """Returns list of pair_ids already in UniverseCandidate for a sector."""
        from sqlalchemy import select
        async with self.AsyncSessionLocal() as session:
            stmt = select(UniverseCandidate.pair_id).where(UniverseCandidate.sector == sector)
            result = await session.execute(stmt)
            return [row[0] for row in result.all()]

    async def save_universe_candidates(self, candidates: List[UniverseCandidate]):
        """Bulk saves universe candidates."""
        if not candidates:
            return
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                for c in candidates:
                    session.add(c)
                # Or use bulk_save_objects if needed, but session.add in a loop within a transaction is usually fine for small/medium batches in async

persistence_service = PersistenceService()
