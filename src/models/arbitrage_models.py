from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

class ArbitrageStatus(str, Enum):
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
    id: UUID = Field(default_factory=uuid4)
    ticker_a: str
    ticker_b: str
    beta: float = 0.0
    status: ArbitrageStatus = ArbitrageStatus.MONITORING
    last_z_score: float = 0.0
    is_cointegrated: bool = False

class ZScoreHistory(BaseModel):
    pair_id: UUID
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    window: int  # 30, 60, or 90
    value: float

class SignalRecord(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    pair_id: UUID
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    z_score: float
    trigger_type: TriggerType
    ai_validation_status: AIValidationStatus = AIValidationStatus.PENDING
    ai_rationale: Optional[str] = None
    user_approval_status: UserApprovalStatus = UserApprovalStatus.PENDING

class VirtualPieAsset(BaseModel):
    ticker: str
    target_weight: float
    current_quantity: float = 0.0
    currency: str = "EUR"

class TradeLedger(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    ticker: str
    quantity: float
    price: float
    order_type: OrderType
    is_paper: bool = True
    status: TradeStatus = TradeStatus.COMPLETED
