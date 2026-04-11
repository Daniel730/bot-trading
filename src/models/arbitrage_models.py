from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
import uuid

class PairStatus(str, Enum):
    MONITORING = "MONITORING"
    ACTIVE_TRADE = "ACTIVE_TRADE"
    PAUSED = "PAUSED"

class TriggerType(str, Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"

class AIValidationStatus(str, Enum):
    PENDING = "PENDING"
    GO = "GO"
    NO_GO = "NO_GO"
    VETOED = "VETOED"

class FundamentalSignal(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    signal_id: str
    ticker: str
    cik: Optional[str] = None
    structural_integrity_score: int = Field(ge=0, le=100)
    prosecutor_argument: str
    defender_argument: str
    final_reasoning: str
    analyzed_at: datetime = Field(default_factory=datetime.now)

class UserApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class OrderType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class TradeStatus(str, Enum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class ArbitragePair(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ticker_a: str
    ticker_b: str
    beta: Optional[float] = None
    status: PairStatus = PairStatus.MONITORING
    last_z_score: Optional[float] = None
    is_cointegrated: bool = False

class SignalRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    pair_id: str
    timestamp: datetime = Field(default_factory=datetime.now)
    z_score: float
    price_a: float
    price_b: float
    trigger_type: TriggerType
    ai_validation_status: AIValidationStatus = AIValidationStatus.PENDING
    ai_rationale: Optional[str] = None
    user_approval_status: UserApprovalStatus = UserApprovalStatus.PENDING

class VirtualPieAsset(BaseModel):
    ticker: str
    target_weight: float
    current_quantity: float
    currency: str = "USD"

class TradeLedger(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.now)
    ticker: str
    quantity: float
    price: float
    order_type: OrderType
    is_paper: bool = True
    status: TradeStatus = TradeStatus.COMPLETED

class ArbitrageError(Exception):
    """Custom exception hierarchy for arbitrage-related errors."""

class BrokerageError(ArbitrageError):
    """Errors related to brokerage API interactions."""

class DataServiceError(ArbitrageError):
    """Errors related to market data polling."""

class OperatingHoursError(ArbitrageError):
    """Raised when an operation is attempted outside of market hours."""

class SlippageError(ArbitrageError):
    """Raised when current prices exceed slippage tolerance."""
