from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class TradingPair:
    id: str
    asset_a: str
    asset_b: str
    hedge_ratio: float = 0.0
    mean_spread: float = 0.0
    std_spread: float = 0.0
    last_z_score: float = 0.0

@dataclass
class VirtualPieAsset:
    ticker: str
    target_weight: float
    current_quantity: float = 0.0
    last_price: float = 0.0

@dataclass
class PortfolioStrategy:
    ticker: str
    strategy_id: str
    target_weight: float
    risk_profile: str

@dataclass
class Signal:
    id: str
    timestamp: datetime
    pair_id: str
    z_score: float
    status: str  # PENDING_AI, PENDING_USER_CONFIRM, APPROVED, REJECTED, EXECUTED, EXPIRED

@dataclass
class TradingOrder:
    id: str
    ticker: str
    order_type: str  # MARKET, LIMIT, STOP
    direction: str  # BUY, SELL
    quantity: Optional[float] = None
    fiat_value: Optional[float] = None
    is_fractional: bool = False
    status: str = "PENDING"
    created_at: datetime = datetime.now()
