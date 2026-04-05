from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Numeric, DateTime, JSON, Enum, Index, func, Boolean, Integer, Text, ForeignKey
import enum
from datetime import datetime
from typing import Optional, List
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

class DecisionType(enum.Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    VETO = "VETO"

class FrequencyType(enum.Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"

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
    execution_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, name="metadata")

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
                expire_on_commit=False,
                pool_pre_ping=True
            )
            cls._instance.AsyncSessionLocal = async_sessionmaker(
                cls._instance.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
        return cls._instance

    async def init_db(self):
        """Initializes the database schema."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def log_trade(self, trade_data: dict):
        """Logs a trade execution to the ledger."""
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

    async def close_trade(self, signal_id: uuid.UUID, exit_prices: dict, pnl: float):
        """Marks trades with a specific signal_id as CLOSED and records PnL."""
        from sqlalchemy import update
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                stmt = update(TradeLedger).where(TradeLedger.signal_id == signal_id).values(
                    status=OrderStatus.CLOSED,
                    metadata_json={"exit_prices": exit_prices, "pnl": pnl}
                )
                await session.execute(stmt)

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

persistence_service = PersistenceService()
