import asyncio
import base64
import hashlib
import hmac
import inspect
import json
import logging
import math
import os
import secrets
import socket
import time
from collections import deque
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from typing import Any, Deque, Dict, List, Literal, Optional
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse
import uvicorn

from src.config import save_pairs_override, save_settings_override, settings
from src.models.persistence import PersistenceManager
from src.services.brokerage_service import BrokerageService, brokerage_service

try:
    from scripts import seed_equal_wallet as wallet_seed
except Exception:  # pragma: no cover - surfaced as an endpoint error if unavailable.
    wallet_seed = None

logger = logging.getLogger(__name__)
_dashboard_auth_token: ContextVar[Optional[str]] = ContextVar("dashboard_auth_token", default=None)
_dashboard_auth_session: ContextVar[Optional[str]] = ContextVar("dashboard_auth_session", default=None)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _safe_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _scrub_non_finite(obj):
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: _scrub_non_finite(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_scrub_non_finite(v) for v in obj]
    return obj


def _bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    scheme, _, credentials = authorization.partition(" ")
    if scheme.lower() == "bearer" and credentials.strip():
        return credentials.strip()
    return authorization.strip() or None


async def _call_brokerage(func, *args, **kwargs):
    """
    Execute a possibly-blocking brokerage call and return its result, awaiting it if it returns an awaitable.
    
    Returns:
        The value returned by the brokerage call; if the call returns an awaitable, the awaited result.
    """
    result = await asyncio.to_thread(func, *args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


def _format_brokerage_ticker(ticker: str) -> str:
    """
    Normalize a ticker string for the active brokerage provider.
    
    Parameters:
        ticker (str): Ticker symbol (may include surrounding whitespace or mixed case).
    
    Returns:
        str: A normalized ticker suitable for the active brokerage. Leading/trailing whitespace is removed and letters are uppercased; when the active provider is T212 and a provider-specific formatter is available, the provider formatter is used instead.
    """
    ticker = (ticker or "").strip().upper()
    if brokerage_service.provider_name == "T212":
        if wallet_seed is not None and hasattr(wallet_seed, "format_t212_ticker"):
            return wallet_seed.format_t212_ticker(ticker)
    return ticker


def _position_ticker(position: dict) -> str:
    """
    Derive an uppercase instrument ticker from a position mapping.
    
    Checks the following keys (in order) and returns the first present value converted to uppercase:
    `ticker`, `instrumentCode`, and `instrument["ticker"]`. If none are present, returns an empty string.
    
    Parameters:
    	position (dict): Position mapping that may contain `ticker`, `instrumentCode`, or an `instrument` dict.
    
    Returns:
    	ticker (str): Uppercase ticker string, or an empty string if no ticker is found.
    """
    instrument = position.get("instrument") or {}
    return str(
        position.get("ticker")
        or position.get("instrumentCode")
        or instrument.get("ticker")
        or ""
    ).upper()


class ConnectionManager:
    def __init__(self, max_connections: int = 50):
        self.active_connections: List[WebSocket] = []
        self.max_connections = max_connections

    async def connect(self, websocket: WebSocket, accept: bool = True) -> bool:
        if len(self.active_connections) >= self.max_connections:
            logger.warning("WebSocket: Max connections reached. Rejecting client without accept.")
            await websocket.close(code=1008)
            return False
        if accept:
            await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("New WebSocket client connected. Total: %s", len(self.active_connections))
        return True

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("WebSocket client disconnected. Total: %s", len(self.active_connections))

    async def broadcast(self, message: str):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as exc:
                logger.error("Error sending to WebSocket client: %s", exc)
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)


connection_manager = ConnectionManager()


class DashboardState:
    def __init__(self):
        self.stage = "Booting up..."
        self.details = "Initializing core components and services."
        self.bot_start_time = _utcnow().isoformat()
        self.portfolio_metrics = {
            "total_revenue": None,
            "total_invested": None,
            "daily_profit": None,
            "available_cash": None,
            "daily_allocation": None,
            "daily_usage_pct": None,
        }
        self.market_regime = {"regime": "STABLE", "confidence": 1.0}
        self.global_accuracy = settings.GLOBAL_STRATEGY_ACCURACY_DEFAULT
        self.active_signals = []
        self.terminal_messages = []
        self.listeners: List[asyncio.Queue] = []
        self._lock = asyncio.Lock()
        self.monitor = None
        self.desired_bot_state = "RUNNING"
        self.last_control_action: Optional[dict] = None

    def runtime_info(self) -> dict:
        if settings.DEV_MODE:
            mode = "DEV"
        elif settings.PAPER_TRADING:
            mode = "PAPER"
        else:
            mode = "LIVE"
        return {
            "mode": mode,
            "paper_trading": settings.PAPER_TRADING,
            "dev_mode": settings.DEV_MODE,
            "live_capital_danger": settings.LIVE_CAPITAL_DANGER,
            "region": settings.REGION,
            "bot_start_time": self.bot_start_time,
            "approval_threshold": settings.APPROVAL_THRESHOLD,
            "desired_bot_state": self.desired_bot_state,
            "last_control_action": self.last_control_action,
        }

    async def add_message(self, msg_type: str, text: str, metadata: dict = None):
        async with self._lock:
            msg = {
                "id": str(os.urandom(4).hex()),
                "type": msg_type,
                "text": text,
                "timestamp": _utcnow().isoformat(),
                "metadata": metadata or {},
            }
            self.terminal_messages.append(msg)
            if len(self.terminal_messages) > 100:
                self.terminal_messages.pop(0)
            await self._broadcast()

    async def _broadcast(self):
        message = json.dumps(
            {
                "stage": self.stage,
                "details": self.details,
                "bot_start_time": self.bot_start_time,
                "runtime": self.runtime_info(),
                "metrics": self.portfolio_metrics,
                "market_regime": self.market_regime,
                "global_accuracy": self.global_accuracy,
                "active_signals": self.active_signals,
                "terminal_messages": self.terminal_messages,
                "timestamp": _utcnow().isoformat(),
            }
        )
        for q in self.listeners:
            await q.put(message)

    async def update(
        self,
        stage: str,
        details: str,
        pnl: float = None,
        signals: int = None,
        active_signals: list = None,
    ):
        async with self._lock:
            self.stage = stage
            self.details = details
            if active_signals is not None:
                self.active_signals = active_signals
            if pnl is not None:
                self.portfolio_metrics["daily_profit"] = pnl
            await self._broadcast()

    async def update_metrics(self, metrics: dict):
        async with self._lock:
            self.portfolio_metrics.update(metrics)
            await self._broadcast()


dashboard_state = DashboardState()


def _dashboard_secret() -> str:
    return settings.DASHBOARD_TOKEN.strip().strip('"').strip("'")


class DashboardSessionManager:
    def __init__(self, ttl_seconds: int = 12 * 60 * 60):
        self.ttl_seconds = ttl_seconds
        self._sessions: Dict[str, dict] = {}
        self._revoked: Dict[str, datetime] = {}

    def create(self, actor: str = "dashboard") -> dict:
        expires_at = _utcnow() + timedelta(seconds=self.ttl_seconds)
        payload = {
            "actor": actor,
            "exp": int(expires_at.timestamp()),
            "iat": int(_utcnow().timestamp()),
            "nonce": secrets.token_urlsafe(16),
        }
        session_token = self._encode_signed(payload)
        return {"session_token": session_token, "expires_at": expires_at.isoformat(), "actor": actor}

    def verify(self, session_token: Optional[str]) -> dict:
        if not session_token:
            raise HTTPException(status_code=401, detail="Dashboard login is required.")
        if session_token.startswith("v1."):
            return self._verify_signed(session_token)
        digest = self._hash(session_token)
        session = self._sessions.get(digest)
        if not session:
            raise HTTPException(status_code=401, detail="Invalid or expired dashboard session.")
        if session["expires_at"] <= _utcnow():
            self._sessions.pop(digest, None)
            raise HTTPException(status_code=401, detail="Dashboard session expired.")
        return session

    def revoke(self, session_token: Optional[str]) -> None:
        if not session_token:
            return
        digest = self._hash(session_token)
        self._sessions.pop(digest, None)
        if session_token.startswith("v1."):
            try:
                session = self._verify_signed(session_token, check_revoked=False)
                self._revoked[digest] = session["expires_at"]
                self._prune_revoked()
            except HTTPException:
                pass

    def _hash(self, value: str) -> str:
        return hmac.new(_dashboard_secret().encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()

    def _encode_signed(self, payload: dict) -> str:
        payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        payload_b64 = self._b64encode(payload_json)
        signature = hmac.new(
            _dashboard_secret().encode("utf-8"),
            payload_b64.encode("ascii"),
            hashlib.sha256,
        ).digest()
        return f"v1.{payload_b64}.{self._b64encode(signature)}"

    def _verify_signed(self, session_token: str, check_revoked: bool = True) -> dict:
        try:
            version, payload_b64, signature_b64 = session_token.split(".", 2)
        except ValueError:
            raise HTTPException(status_code=401, detail="Invalid or expired dashboard session.")
        if version != "v1":
            raise HTTPException(status_code=401, detail="Invalid or expired dashboard session.")

        expected_signature = hmac.new(
            _dashboard_secret().encode("utf-8"),
            payload_b64.encode("ascii"),
            hashlib.sha256,
        ).digest()
        try:
            received_signature = self._b64decode(signature_b64)
        except ValueError:
            raise HTTPException(status_code=401, detail="Invalid or expired dashboard session.")
        if not hmac.compare_digest(received_signature, expected_signature):
            raise HTTPException(status_code=401, detail="Invalid or expired dashboard session.")
        if check_revoked and self._hash(session_token) in self._revoked:
            self._prune_revoked()
            if self._hash(session_token) in self._revoked:
                raise HTTPException(status_code=401, detail="Invalid or expired dashboard session.")

        try:
            payload = json.loads(self._b64decode(payload_b64).decode("utf-8"))
            expires_at = datetime.fromtimestamp(int(payload["exp"]), tz=timezone.utc)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            raise HTTPException(status_code=401, detail="Invalid or expired dashboard session.")
        if expires_at <= _utcnow():
            raise HTTPException(status_code=401, detail="Dashboard session expired.")
        return {"actor": str(payload.get("actor") or "dashboard"), "expires_at": expires_at}

    def _prune_revoked(self) -> None:
        now = _utcnow()
        expired = [digest for digest, expires_at in self._revoked.items() if expires_at <= now]
        for digest in expired:
            self._revoked.pop(digest, None)

    @staticmethod
    def _b64encode(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    @staticmethod
    def _b64decode(value: str) -> bytes:
        try:
            padding = "=" * (-len(value) % 4)
            return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))
        except Exception as exc:
            raise ValueError("Invalid base64 value") from exc


session_manager = DashboardSessionManager()


class DashboardLoginChallengeManager:
    def __init__(self, ttl_seconds: int = 5 * 60):
        self.ttl_seconds = ttl_seconds
        self._challenges: Dict[str, dict] = {}

    async def create(self, actor: str, request: Request) -> dict:
        from src.services.notification_service import notification_service

        challenge_id = secrets.token_urlsafe(9)
        expires_at = _utcnow() + timedelta(seconds=self.ttl_seconds)
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._challenges[challenge_id] = {
            "actor": actor,
            "expires_at": expires_at,
            "future": future,
        }
        notification_service.pending_approvals[challenge_id] = future
        summary = self._summary(actor, request, expires_at)
        sent = await notification_service.send_dashboard_login_approval(challenge_id, summary)
        if not sent:
            self.discard(challenge_id)
            raise HTTPException(
                status_code=503,
                detail="Login approval notifications are not configured. Use an authenticator or backup code.",
            )
        return {
            "status": "pending",
            "challenge_id": challenge_id,
            "expires_at": expires_at.isoformat(),
            "message": "Approval notification sent.",
        }

    def complete(self, challenge_id: str) -> dict:
        challenge = self._challenges.get(challenge_id)
        if not challenge:
            raise HTTPException(status_code=404, detail="Invalid or expired login challenge.")
        if challenge["expires_at"] <= _utcnow():
            self.discard(challenge_id)
            raise HTTPException(status_code=410, detail="Login challenge expired.")
        future = challenge["future"]
        if not future.done():
            return {
                "status": "pending",
                "challenge_id": challenge_id,
                "expires_at": challenge["expires_at"].isoformat(),
            }
        approved = bool(future.result())
        actor = challenge["actor"]
        self.discard(challenge_id)
        if not approved:
            raise HTTPException(status_code=403, detail="Login approval was rejected.")
        return {"status": "approved", **session_manager.create(actor=actor)}

    def discard(self, challenge_id: str) -> None:
        self._challenges.pop(challenge_id, None)
        try:
            from src.services.notification_service import notification_service
            notification_service.pending_approvals.pop(challenge_id, None)
        except Exception:
            pass

    def _summary(self, actor: str, request: Request, expires_at: datetime) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        client = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
        user_agent = request.headers.get("user-agent", "unknown")
        return (
            f"*Actor*: `{actor}`\n"
            f"*IP*: `{client}`\n"
            f"*User-Agent*: `{user_agent[:120]}`\n"
            f"*Expires*: `{expires_at.isoformat()}`"
        )


login_challenge_manager = DashboardLoginChallengeManager()


def verify_security_token(token: Optional[str] = None):
    token = token or _dashboard_auth_token.get()
    secret = settings.DASHBOARD_TOKEN.strip().strip('"').strip("'")
    if token != secret:
        logger.warning(
            "DASHBOARD: Auth failed. Expected Len: %s, Received Len: %s",
            len(secret),
            len(token) if token else 0,
        )
        raise HTTPException(status_code=403, detail="Invalid Dashboard Token")
    return token


def verify_token(token: Optional[str] = None, session: Optional[str] = None):
    session = session or _dashboard_auth_session.get()
    token = token or _dashboard_auth_token.get()
    session_manager.verify(session)
    if token:
        return verify_security_token(token)
    return session


def _serialize_pair(active_pair: dict) -> dict:
    ticker_a = active_pair.get("ticker_a", "")
    ticker_b = active_pair.get("ticker_b", "")
    is_crypto = "-USD" in ticker_a or "-USD" in ticker_b
    pair_id = active_pair.get("id", "")
    sector = settings.PAIR_SECTORS.get(
        pair_id,
        settings.PAIR_SECTORS.get(f"{ticker_b}_{ticker_a}", "Crypto" if is_crypto else "Unassigned"),
    )
    return {
        "id": pair_id,
        "ticker_a": ticker_a,
        "ticker_b": ticker_b,
        "hedge_ratio": _safe_float(active_pair.get("hedge_ratio")),
        "mean": _safe_float(active_pair.get("mean")),
        "std": _safe_float(active_pair.get("std")),
        "is_cointegrated": active_pair.get("is_cointegrated"),
        "is_crypto": is_crypto,
        "sector": sector,
    }


class TOTPManager:
    def __init__(self, persistence: PersistenceManager):
        self.persistence = persistence

    def _key_bytes(self) -> bytes:
        return hashlib.sha256(settings.DASHBOARD_TOKEN.encode("utf-8")).digest()

    def _protect_secret(self, secret: str) -> str:
        secret_bytes = secret.encode("utf-8")
        key = self._key_bytes()
        masked = bytes(b ^ key[i % len(key)] for i, b in enumerate(secret_bytes))
        return base64.urlsafe_b64encode(masked).decode("ascii")

    def _unprotect_secret(self, payload: str) -> str:
        masked = base64.urlsafe_b64decode(payload.encode("ascii"))
        key = self._key_bytes()
        raw = bytes(b ^ key[i % len(key)] for i, b in enumerate(masked))
        return raw.decode("utf-8")

    def _normalize_token(self, token: str) -> str:
        return "".join(ch for ch in str(token or "") if ch.isdigit())

    def generate_secret(self) -> str:
        return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")

    def _counter(self, for_time: Optional[int] = None, interval: int = 30) -> int:
        ts = for_time if for_time is not None else int(time.time())
        return int(ts // interval)

    def totp_token(self, secret: str, counter: Optional[int] = None, digits: int = 6) -> str:
        normalized = secret.upper()
        padding = "=" * ((8 - len(normalized) % 8) % 8)
        key = base64.b32decode(normalized + padding, casefold=True)
        ctr = self._counter() if counter is None else counter
        msg = ctr.to_bytes(8, "big")
        digest = hmac.new(key, msg, hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        code = int.from_bytes(digest[offset : offset + 4], "big") & 0x7FFFFFFF
        return str(code % (10**digits)).zfill(digits)

    def verify_totp(self, secret: str, token: str, window: int = 1) -> bool:
        normalized = self._normalize_token(token)
        if len(normalized) != 6:
            return False
        current = self._counter()
        for offset in range(-window, window + 1):
            if hmac.compare_digest(self.totp_token(secret, current + offset), normalized):
                return True
        return False

    def hash_backup_code(self, code: str) -> str:
        return hashlib.sha256(code.encode("utf-8")).hexdigest()

    def generate_backup_codes(self, count: int = 8) -> List[str]:
        return [secrets.token_hex(4).upper() for _ in range(count)]

    def get_state(self) -> dict:
        return self.persistence.get_dashboard_auth_state(
            "totp_state",
            default={"enabled": False, "pending": None, "secret_encrypted": None, "backup_code_hashes": []},
        )

    def save_state(self, state: dict) -> None:
        self.persistence.set_dashboard_auth_state("totp_state", state)

    def initiate_setup(self) -> dict:
        secret = self.generate_secret()
        backup_codes = self.generate_backup_codes()
        state = self.get_state()
        state["pending"] = {
            "secret_encrypted": self._protect_secret(secret),
            "backup_code_hashes": [self.hash_backup_code(code) for code in backup_codes],
            "created_at": _utcnow().isoformat(),
        }
        self.save_state(state)
        label = quote("Arbitrage Bot Dashboard")
        issuer = quote("Alpha Arbitrage Elite")
        otpauth = f"otpauth://totp/{issuer}:{label}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30"
        return {
            "enabled": bool(state.get("enabled")),
            "secret": secret,
            "otpauth_url": otpauth,
            "backup_codes": backup_codes,
        }

    def verify_setup(self, token: str) -> bool:
        state = self.get_state()
        pending = state.get("pending")
        if not pending:
            return False
        secret = self._unprotect_secret(pending["secret_encrypted"])
        if not self.verify_totp(secret, token):
            return False
        state["enabled"] = True
        state["secret_encrypted"] = pending["secret_encrypted"]
        state["backup_code_hashes"] = pending["backup_code_hashes"]
        state["pending"] = None
        self.save_state(state)
        return True

    def verify_token_or_backup(self, token: str) -> bool:
        state = self.get_state()
        if not state.get("enabled") or not state.get("secret_encrypted"):
            return False
        secret = self._unprotect_secret(state["secret_encrypted"])
        if self.verify_totp(secret, token):
            return True
        hashed = self.hash_backup_code(str(token or "").strip().upper())
        backups = list(state.get("backup_code_hashes", []))
        if hashed in backups:
            backups.remove(hashed)
            state["backup_code_hashes"] = backups
            self.save_state(state)
            return True
        return False

    def public_status(self) -> dict:
        state = self.get_state()
        pending = state.get("pending")
        return {
            "enabled": bool(state.get("enabled")),
            "pending_setup": bool(pending),
            "backup_codes_remaining": len(state.get("backup_code_hashes", [])),
        }


class CommandRequest(BaseModel):
    command: str
    metadata: Optional[dict] = None


class SettingsUpdateRequest(BaseModel):
    approval_threshold: float


class PairConfig(BaseModel):
    ticker_a: str
    ticker_b: str


class PairsUpdateRequest(BaseModel):
    pairs: List[PairConfig]
    crypto_pairs: Optional[List[PairConfig]] = None
    apply_now: bool = True


class WalletSyncRequest(BaseModel):
    budget: float = Field(..., gt=0)
    skip_owned: bool = True
    skip_pending: bool = True
    delay_seconds: float = Field(default=0.5, ge=0, le=10)


class WalletRecommendationRequest(BaseModel):
    budget: float = Field(..., gt=0)
    include_broken: bool = False
    skip_owned: bool = True
    skip_pending: bool = True


class WalletRecommendationBuyRequest(WalletRecommendationRequest):
    tickers: Optional[List[str]] = None
    delay_seconds: float = Field(default=0.5, ge=0, le=10)


T212WalletSyncRequest = WalletSyncRequest
T212WalletRecommendationRequest = WalletRecommendationRequest
T212WalletRecommendationBuyRequest = WalletRecommendationBuyRequest


class DashboardConfigUpdateRequest(BaseModel):
    actor: str = "dashboard"
    updates: Dict[str, Any]
    otp_token: Optional[str] = None


class DashboardLoginRequest(BaseModel):
    security_token: str
    otp_token: Optional[str] = None
    actor: str = "dashboard"


class DashboardLoginCompleteRequest(BaseModel):
    challenge_id: str


class TOTPVerifyRequest(BaseModel):
    token: str


class BotControlRequest(BaseModel):
    action: Literal["start", "stop", "restart"]
    actor: str = "dashboard"


app = FastAPI(title="Arbitrage Dashboard", redirect_slashes=True)


@app.middleware("http")
async def dashboard_auth_context(request: Request, call_next):
    token_marker = _dashboard_auth_token.set(_bearer_token(request.headers.get("authorization")))
    session_marker = _dashboard_auth_session.set(request.headers.get("x-dashboard-session"))
    try:
        return await call_next(request)
    finally:
        _dashboard_auth_token.reset(token_marker)
        _dashboard_auth_session.reset(session_marker)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.dashboard_allowed_origins,
    allow_origin_regex=settings.dashboard_allowed_origin_regex,
    allow_methods=["*"],
    allow_headers=["Accept", "Authorization", "Content-Type", "X-Dashboard-Session"],
)


class DashboardService:
    def __init__(self):
        self.server = None
        self.persistence = PersistenceManager(settings.DB_PATH)
        self.dashboard_state = dashboard_state
        self.health_history: Deque[dict] = deque(maxlen=120)
        self.totp = TOTPManager(self.persistence)
        self.editable_config: Dict[str, dict] = {
            "REGION": {"type": "str", "sensitive": False, "options": ["US", "EU"]},
            "APPROVAL_THRESHOLD": {"type": "float", "sensitive": False},
            "SCAN_INTERVAL_SECONDS": {"type": "int", "sensitive": False},
            "MARKET_DATA_TIMEOUT_SECONDS": {"type": "float", "sensitive": False},
            "MONITOR_ENTRY_ZSCORE": {"type": "float", "sensitive": False},
            "TAKE_PROFIT_ZSCORE": {"type": "float", "sensitive": False},
            "STOP_LOSS_ZSCORE": {"type": "float", "sensitive": False},
            "MAX_ALLOCATION_PERCENTAGE": {"type": "float", "sensitive": True},
            "MAX_RISK_PER_TRADE": {"type": "float", "sensitive": True},
            "MAX_DRAWDOWN": {"type": "float", "sensitive": True},
            "FINANCIAL_KILL_SWITCH_PCT": {"type": "float", "sensitive": True},
            "COINTEGRATION_PVALUE_THRESHOLD": {"type": "float", "sensitive": False},
            "KALMAN_DELTA": {"type": "float", "sensitive": False},
            "KALMAN_R": {"type": "float", "sensitive": False},
            "BROKERAGE_PROVIDER": {
                "type": "str",
                "sensitive": True,
                "masked": False,
                "options": ["T212", "ALPACA"],
            },
            "T212_BUDGET_USD": {"type": "float", "sensitive": False},
            "WEB3_BUDGET_USD": {"type": "float", "sensitive": False},
            "TRADING_212_MODE": {
                "type": "str",
                "sensitive": True,
                "masked": False,
                "options": ["demo", "live"],
            },
            "LIVE_CAPITAL_DANGER": {"type": "bool", "sensitive": True},
            "PAPER_TRADING": {"type": "bool", "sensitive": True},
            "DEV_MODE": {"type": "bool", "sensitive": True},
            "OPENAI_API_KEY": {"type": "str", "sensitive": True},
            "GEMINI_API_KEY": {"type": "str", "sensitive": True},
            "POLYGON_API_KEY": {"type": "str", "sensitive": True},
            "T212_API_KEY": {"type": "str", "sensitive": True},
            "T212_API_SECRET": {"type": "str", "sensitive": True},
            "TRADING_212_API_KEY": {"type": "str", "sensitive": True},
            "ALPACA_API_KEY": {"type": "str", "sensitive": True},
            "ALPACA_API_SECRET": {"type": "str", "sensitive": True},
            "ALPACA_BASE_URL": {"type": "str", "sensitive": True, "masked": False},
            "ALLOW_LIVE_APPROVAL_WITHOUT_TELEGRAM": {"type": "bool", "sensitive": True},
            "SEC_USER_AGENT": {"type": "str", "sensitive": False},
            "TELEGRAM_BOT_TOKEN": {"type": "str", "sensitive": True},
            "TELEGRAM_CHAT_ID": {"type": "str", "sensitive": False},
            "WEB3_PRIVATE_KEY": {"type": "str", "sensitive": True},
            "WEB3_RPC_URL": {"type": "str", "sensitive": True},
        }

    def attach_monitor(self, monitor):
        dashboard_state.monitor = monitor

    async def _wallet_pair_z_scores(self, pair_ids: list[str]) -> dict[str, float]:
        """
        Fetch Kalman z-scores for the given pair IDs from the Redis-backed Kalman state store.
        
        Parameters:
            pair_ids (list[str]): Iterable of pair identifier strings to query.
        
        Returns:
            dict[str, float]: Mapping of pair_id to its parsed z-score. Pair IDs with missing, non-finite, or unparsable z-scores are omitted.
        
        Notes:
            - Individual fetch errors for a pair_id are suppressed and that pair will be skipped.
            - If the Redis backend cannot be contacted, a warning is logged and an empty mapping (or any successfully collected scores) is returned.
        """
        scores: dict[str, float] = {}
        try:
            from src.services.redis_service import redis_service

            for pair_id in pair_ids:
                try:
                    state = await redis_service.get_kalman_state(pair_id)
                    if state and "z_score" in state:
                        z_score = _safe_float(state["z_score"])
                        if z_score is not None:
                            scores[pair_id] = z_score
                except Exception:
                    continue
        except Exception as exc:
            logger.warning("DASHBOARD: Could not fetch wallet recommendation z-scores: %s", exc)
        return scores

    async def _collect_wallet_candidates(self, include_broken: bool) -> tuple[dict[str, int], dict[str, dict]]:
        """
        Collects candidate tickers for wallet recommendations from the monitor's active pairs.
        
        Raises:
        	HTTPException: 409 if the bot monitor is not attached.
        
        Parameters:
        	include_broken (bool): If True, include tickers from pairs not marked as cointegrated ("broken_eligible") as candidates; if False, still considers them but logs a warning the first time each non-cointegrated ticker is encountered.
        
        Returns:
        	counts (dict[str, int]): Counters with keys `"coint"` and `"broken_eligible"` representing number of pairs in each category.
        	candidates (dict[str, dict]): Mapping from ticker symbol to candidate metadata with the following keys:
        		- ticker (str): Uppercased ticker symbol.
        		- categories (set[str]): Set containing one or more of `"coint"` / `"broken_eligible"`.
        		- pairs (list[dict]): List of pair info dicts, each containing `id`, `ticker_a`, `ticker_b`, `category`, `z_score` (float or None), `estimated_cost_pct` (float), and `sector`.
        		- sectors (set[str]): Set of sector names for that ticker.
        		- max_abs_z_score (float): Maximum absolute z-score observed across pairs for this ticker (0.0 if none).
        		- estimated_cost_pct (float): Maximum estimated cost percentage observed across pairs for this ticker (0.0 if none).
        """
        monitor = dashboard_state.monitor
        if monitor is None:
            raise HTTPException(status_code=409, detail="The bot monitor is not attached yet. Start the bot before reading wallet recommendations.")

        pair_ids = [
            str(pair.get("id") or f"{pair.get('ticker_a')}_{pair.get('ticker_b')}")
            for pair in monitor.active_pairs
        ]
        z_scores = await self._wallet_pair_z_scores(pair_ids)
        counts = {"coint": 0, "broken_eligible": 0}
        candidates: dict[str, dict] = {}
        active_provider = brokerage_service.provider_name
        for pair in monitor.active_pairs:
            ticker_a = str(pair.get("ticker_a") or "").strip().upper()
            ticker_b = str(pair.get("ticker_b") or "").strip().upper()
            if not ticker_a or not ticker_b:
                continue
            if "-USD" in ticker_a or "-USD" in ticker_b:
                continue

            is_coint = pair.get("is_cointegrated") is True
            category = "coint" if is_coint else "broken_eligible"
            counts[category] += 1
            if category == "broken_eligible" and not include_broken:
                continue

            pair_id = str(pair.get("id") or f"{ticker_a}_{ticker_b}")
            sector = settings.PAIR_SECTORS.get(
                pair_id,
                settings.PAIR_SECTORS.get(f"{ticker_b}_{ticker_a}", "Unassigned"),
            )
            z_score = _safe_float(z_scores.get(pair_id))
            estimated_cost = _safe_float(pair.get("estimated_cost_pct")) or 0.0
            pair_info = {
                "id": pair_id,
                "ticker_a": ticker_a,
                "ticker_b": ticker_b,
                "category": category,
                "z_score": z_score,
                "estimated_cost_pct": estimated_cost,
                "sector": sector,
            }

            for ticker in (ticker_a, ticker_b):
                if brokerage_service.get_venue(ticker) != active_provider:
                    continue
                provider = brokerage_service.provider
                if hasattr(provider, "is_supported_symbol") and not provider.is_supported_symbol(ticker):
                    continue
                entry = candidates.setdefault(
                    ticker,
                    {
                        "ticker": ticker,
                        "categories": set(),
                        "pairs": [],
                        "sectors": set(),
                        "max_abs_z_score": 0.0,
                        "estimated_cost_pct": 0.0,
                    },
                )
                entry["categories"].add(category)
                entry["pairs"].append(pair_info)
                entry["sectors"].add(sector)
                entry["estimated_cost_pct"] = max(float(entry["estimated_cost_pct"]), estimated_cost)
                if z_score is not None:
                    entry["max_abs_z_score"] = max(float(entry["max_abs_z_score"]), abs(z_score))

        return counts, candidates

    @staticmethod
    def _wallet_recommendation_score(candidate: dict) -> float:
        categories = candidate.get("categories") or set()
        base = 100.0 if "coint" in categories else 55.0
        z_bonus = min(float(candidate.get("max_abs_z_score") or 0.0), 4.0) * 8.0
        pair_bonus = min(len(candidate.get("pairs") or []), 4) * 3.0
        cost_penalty = min(float(candidate.get("estimated_cost_pct") or 0.0) * 1000.0, 25.0)
        return round(max(1.0, base + z_bonus + pair_bonus - cost_penalty), 4)

    @staticmethod
    def _build_weighted_wallet_plan(total_budget: float, recommendations: list[dict]) -> list[tuple[str, Decimal]]:
        """
        Builds a weighted allocation plan that distributes a total budget across recommended tickers proportional to their scores.
        
        Parameters:
            total_budget (float): Total budget in decimal currency units to allocate.
            recommendations (list[dict]): List of recommendation objects. Each item must include "ticker" (str) and may include "score" (numeric). This function will add/overwrite "rank" (int, 1-based) and "suggested_amount" (float) on each recommendation dict.
        
        Returns:
            list[tuple[str, Decimal]]: Ordered list of (ticker, amount) pairs where amount is a Decimal currency value representing the suggested allocation for that ticker.
        
        Raises:
            ValueError: If the provided budget is too small to allocate at least $0.01 to each recommendation.
        """
        if not recommendations:
            return []
        budget_dec = Decimal(str(total_budget))
        cents = int((budget_dec * Decimal("100")).to_integral_value(rounding=ROUND_DOWN))
        if cents < len(recommendations):
            raise ValueError(
                f"Budget {budget_dec} is too small for {len(recommendations)} recommendations; "
                "each ticker needs at least 0.01."
            )

        scores = [max(Decimal("0.01"), Decimal(str(item.get("score") or 0.01))) for item in recommendations]
        total_score = sum(scores)

        allocations = [0] * len(recommendations)
        remaining_cents = cents
        for i, score in enumerate(scores):
            share = (score * Decimal(str(cents)) / total_score).to_integral_value(rounding=ROUND_DOWN)
            allocations[i] = int(share)
            remaining_cents -= int(share)

        while remaining_cents > 0:
            for i in range(len(allocations)):
                allocations[i] += 1
                remaining_cents -= 1
                if remaining_cents == 0:
                    break

        plan: list[tuple[str, Decimal]] = []
        for rank, (item, allocated_cents) in enumerate(zip(recommendations, allocations), start=1):
            amount = Decimal(allocated_cents) / Decimal("100")
            item["rank"] = rank
            item["suggested_amount"] = float(amount)
            plan.append((item["ticker"], amount))
        return plan

    async def _get_brokerage_wallet_state(self) -> dict:
        """
        Fetches the current brokerage wallet state including positions, pending orders, owned and pending tickers, and cash balances.
        
        Returns:
            dict: A mapping with the following keys:
                - positions (list): Raw positions returned by the brokerage.
                - pending_orders (list): Raw pending orders returned by the brokerage.
                - owned_tickers (set[str]): Tickers with a positive owned quantity.
                - pending_buy_tickers (set[str]): Tickers with a positive pending buy quantity.
                - account_cash (float): Reported account cash (0.0 if absent).
                - pending_value (float): Total value reserved by pending orders.
                - spendable_cash (float): Available cash after subtracting pending_value (not negative).
                - effective_cash (float): Budget-service–adjusted available cash for the active provider.
        
        Raises:
            HTTPException: Status 502 if brokerage calls fail or cannot be read.
        """
        try:
            positions = await _call_brokerage(brokerage_service.get_positions)
            pending_orders = await _call_brokerage(brokerage_service.get_pending_orders)
            account_cash = await _call_brokerage(brokerage_service.get_account_cash)
            pending_value = float(await _call_brokerage(brokerage_service.get_pending_orders_value))
        except Exception as exc:
            logger.error("DASHBOARD: Brokerage wallet state preflight failed: %s", exc)
            raise HTTPException(status_code=502, detail=f"Could not read brokerage wallet state: {exc}") from exc

        owned_tickers: set[str] = set()
        for position in positions:
            ticker = _position_ticker(position)
            quantity = _safe_float(position.get("quantity"))
            if ticker and quantity is not None and quantity > 0:
                owned_tickers.add(ticker)

        pending_buy_tickers: set[str] = set()
        for order in pending_orders:
            ticker = _position_ticker(order)
            quantity = _safe_float(order.get("quantity"))
            if ticker and quantity is not None and quantity > 0:
                pending_buy_tickers.add(ticker)

        from src.services.budget_service import budget_service

        raw_cash = float(account_cash or 0.0)
        spendable_cash = max(0.0, raw_cash - max(0.0, pending_value))
        effective_cash = budget_service.get_effective_cash(brokerage_service.provider_name, spendable_cash)
        return {
            "positions": positions,
            "pending_orders": pending_orders,
            "owned_tickers": owned_tickers,
            "pending_buy_tickers": pending_buy_tickers,
            "account_cash": raw_cash,
            "pending_value": pending_value,
            "spendable_cash": spendable_cash,
            "effective_cash": effective_cash,
        }

    async def calculate_wallet_recommendations(self, request: WalletRecommendationRequest) -> dict:
        """
        Calculate wallet buy recommendations based on active pairs, candidate scoring, and available brokerage cash.
        
        Produces ranked recommendations and skipped items after filtering by ownership and pending orders, and evaluates whether the requested budget is feasible given the broker's effective cash.
        
        Parameters:
            request (WalletRecommendationRequest): Request containing `budget`, `include_broken`, `skip_owned`, and `skip_pending` flags that control candidate inclusion and filtering.
        
        Returns:
            dict: A summary object with the following keys:
                - status: Operation status, always `"ok"` on success.
                - mode: The active brokerage provider name used for ticker formatting and cash checks.
                - message: Human-readable summary of the result.
                - generated_at: ISO8601 timestamp when recommendations were generated.
                - include_broken: Echoes the `include_broken` request flag.
                - coint_pairs: Count of cointegrated pairs considered.
                - broken_eligible_pairs: Count of broken-eligible pairs considered.
                - candidate_tickers: Sorted list of all candidate tickers considered.
                - recommended_tickers: Ordered list of tickers recommended for purchase.
                - budget: Requested budget (numeric).
                - usable_budget: Budget used for planning (may equal `budget`).
                - cash_limited: `true` if requested budget exceeds broker effective cash, `false` otherwise.
                - spendable_cash: Broker spendable cash (may be `null` if unavailable).
                - effective_cash: Broker effective cash after budget rules (may be `null` if unavailable).
                - can_buy: `true` if there are recommendations that can be converted into orders.
                - warning: Warning message string when planning issues occur, otherwise `null`.
                - recommendations: List of recommendation objects with fields:
                    - ticker, broker_ticker, category (`"coint"` or `"broken_eligible"`), categories (list),
                    - pairs (list), sectors (list), score (numeric), max_abs_z_score (numeric),
                    - estimated_cost_pct (numeric), rank (assigned by planner or `null`), suggested_amount (numeric), status.
                - skipped: List of skipped candidate objects (same fields as recommendations plus `reason` string).
        
        The returned structure has non-finite float values replaced with `null` for safe JSON serialization.
        """
        if not brokerage_service.test_connection():
            raise HTTPException(status_code=400, detail=f"Brokerage provider {brokerage_service.provider_name} is not configured or reachable.")

        counts, candidates = await self._collect_wallet_candidates(request.include_broken)
        wallet_state = await self._get_brokerage_wallet_state()

        recommendations: list[dict] = []
        skipped: list[dict] = []
        for ticker, candidate in candidates.items():
            broker_ticker = _format_brokerage_ticker(ticker)
            categories = sorted(candidate["categories"])
            category = "coint" if "coint" in candidate["categories"] else "broken_eligible"
            common = {
                "ticker": ticker,
                "broker_ticker": broker_ticker,
                "category": category,
                "categories": categories,
                "pairs": candidate["pairs"],
                "sectors": sorted(candidate["sectors"]),
                "score": self._wallet_recommendation_score(candidate),
                "max_abs_z_score": _safe_float(candidate.get("max_abs_z_score")) or 0.0,
                "estimated_cost_pct": _safe_float(candidate.get("estimated_cost_pct")) or 0.0,
            }
            if request.skip_owned and broker_ticker in wallet_state["owned_tickers"]:
                skipped.append({**common, "reason": "owned"})
                continue
            if request.skip_pending and broker_ticker in wallet_state["pending_buy_tickers"]:
                skipped.append({**common, "reason": "pending_buy"})
                continue
            recommendations.append({**common, "rank": None, "suggested_amount": 0.0, "status": "ready"})

        recommendations.sort(
            key=lambda item: (
                0 if item["category"] == "coint" else 1,
                -float(item["score"]),
                item["ticker"],
            )
        )

        budget = float(request.budget)
        effective_cash = float(wallet_state["effective_cash"])
        usable_budget = budget
        cash_limited = budget > effective_cash + 1e-9
        warning = None
        if cash_limited:
            logger.warning(
                "DASHBOARD: Wallet recommendation budget %.2f exceeds effective %s cash %.2f; deferring to broker.",
                budget,
                brokerage_service.provider_name,
                effective_cash,
            )
            warning = (
                f"Budget {budget:.2f} exceeds spendable {brokerage_service.provider_name} cash/budget {effective_cash:.2f}; "
                "the broker will be the final gate."
            )
        can_buy = bool(recommendations)

        if recommendations and can_buy:
            try:
                self._build_weighted_wallet_plan(usable_budget, recommendations)
            except ValueError as exc:
                warning = str(exc)
                can_buy = False
        elif recommendations:
            warning = f"No spendable {brokerage_service.provider_name} cash is available for this plan."

        if not recommendations and skipped:
            message = "Every eligible recommendation is already owned or pending."
        elif not recommendations:
            message = f"No {brokerage_service.provider_name} stock recommendations are available for the current filters."
        else:
            message = f"Calculated {len(recommendations)} recommended {brokerage_service.provider_name} stock buys."

        return _scrub_non_finite(
            {
                "status": "ok",
                "mode": brokerage_service.provider_name,
                "message": message,
                "generated_at": _utcnow().isoformat(),
                "include_broken": request.include_broken,
                "coint_pairs": counts["coint"],
                "broken_eligible_pairs": counts["broken_eligible"],
                "candidate_tickers": sorted(candidates),
                "recommended_tickers": [item["ticker"] for item in recommendations],
                "budget": budget,
                "usable_budget": usable_budget,
                "cash_limited": cash_limited,
                "spendable_cash": _safe_float(wallet_state["spendable_cash"]),
                "effective_cash": _safe_float(effective_cash),
                "can_buy": can_buy,
                "warning": warning,
                "recommendations": recommendations,
                "skipped": skipped,
            }
        )

    async def buy_wallet_recommendations(self, request: WalletRecommendationBuyRequest) -> dict:
        """
        Place BUY orders for wallet recommendations computed from the current market state, optionally restricted to a user-selected set of tickers.
        
        Accepts a WalletRecommendationBuyRequest containing the desired budget, optional explicit ticker list, include_broken flag, and inter-order delay. Validates brokerage connectivity, obtains a recommendation snapshot, applies any ticker overrides (allowing manual overrides for active but non-recommended tickers), builds a weighted allocation plan, places value-based BUY orders, and records a system message.
        
        Parameters:
            request (WalletRecommendationBuyRequest): Request payload with fields:
                - budget: total amount to spend.
                - tickers (optional): list of tickers to restrict purchases to (case-insensitive).
                - include_broken (optional): whether to include candidates from broken/eligible pairs.
                - delay_seconds (optional): delay between sequential orders.
        
        Returns:
            dict: Summary of the buy operation with keys:
                - status: "ok" if all orders succeeded, otherwise "partial".
                - mode: brokerage provider name used.
                - message: human-readable summary.
                - budget: submitted budget (float).
                - target_tickers: list of tickers that were ordered.
                - recommendations: final recommendation entries used to build the plan.
                - skipped: list of any skipped orders (currently may be empty).
                - orders: list of per-order result objects from the brokerage.
                - failures: integer count of failed orders.
        
        Raises:
            HTTPException: if the brokerage is unreachable/configured, if no recommendations are available, if user-provided tickers are not in the active provider universe, or if the weighted plan cannot be built.
        """
        if not brokerage_service.test_connection():
            raise HTTPException(status_code=400, detail=f"Brokerage provider {brokerage_service.provider_name} is not configured or reachable.")

        plan_snapshot = await self.calculate_wallet_recommendations(request)
        budget = float(request.budget)

        if plan_snapshot.get("cash_limited"):
            logger.warning(
                "DASHBOARD: Proceeding with wallet recommendation BUY despite cash_limited=true (budget=%.2f, effective_cash=%.2f).",
                budget,
                float(plan_snapshot.get("effective_cash") or 0.0),
            )

        recommendations = plan_snapshot.get("recommendations") or []
        if request.tickers:
            selected_tickers = {ticker.strip().upper() for ticker in request.tickers if ticker.strip()}
            known_tickers = {item["ticker"] for item in recommendations}
            unknown = sorted(selected_tickers - known_tickers)
            if unknown:
                _, active_universe = self._get_active_tickers()
                active_universe_set = set(active_universe)
                truly_unknown = [t for t in unknown if t not in active_universe_set]
                if truly_unknown:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Tickers are not in any active {brokerage_service.provider_name} pair: "
                            f"{', '.join(truly_unknown)}"
                        ),
                    )
                manual_overrides = [t for t in unknown if t in active_universe_set]
                logger.warning(
                    "DASHBOARD: Manual override buy for non-recommended ticker %s",
                    ", ".join(manual_overrides),
                )
                for ticker in manual_overrides:
                    recommendations.append({
                        "ticker": ticker,
                        "broker_ticker": _format_brokerage_ticker(ticker),
                        "category": "manual_override",
                        "categories": ["manual_override"],
                        "pairs": [],
                        "sectors": [],
                        "score": 1.0,
                        "max_abs_z_score": 0.0,
                        "estimated_cost_pct": 0.0,
                        "rank": None,
                        "suggested_amount": 0.0,
                        "status": "manual_override",
                    })
            recommendations = [item for item in recommendations if item["ticker"] in selected_tickers]

        if not recommendations:
            raise HTTPException(status_code=400, detail=f"No recommended {brokerage_service.provider_name} tickers are available to buy.")

        try:
            seed_plan = self._build_weighted_wallet_plan(budget, recommendations)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        orders, failures, skipped_orders = await self._place_wallet_orders(
            seed_plan,
            request.delay_seconds
        )

        submitted = sum(1 for order in orders if order.get("status") == "ok")
        planned = len(seed_plan)
        target_tickers = [ticker for ticker, _ in seed_plan]
        await dashboard_state.add_message(
            "SYSTEM",
            f"Wallet recommendations submitted {submitted}/{planned} BUY orders for {brokerage_service.provider_name}.",
            metadata={
                "type": "wallet_recommendation_buy",
                "failures": failures,
                "tickers": target_tickers,
                "include_broken": request.include_broken,
                "broker": brokerage_service.provider_name
            },
        )

        return _scrub_non_finite(
            {
                "status": "ok" if failures == 0 else "partial",
                "mode": brokerage_service.provider_name,
                "message": f"Submitted {submitted}/{planned} recommended BUY orders.",
                "budget": budget,
                "target_tickers": target_tickers,
                "recommendations": recommendations,
                "skipped": skipped_orders,
                "orders": orders,
                "failures": failures,
            }
        )
    def _get_active_tickers(self) -> tuple[int, list[str]]:
        """
        Collect active tickers that belong to the configured brokerage provider and count cointegrated pairs.
        
        Returns:
            tuple: (coint_pairs, tickers) where `coint_pairs` is the number of active pairs marked as cointegrated, and `tickers` is a list of unique, uppercased tickers that match the active brokerage provider (tickers containing "-USD" are excluded).
        
        Raises:
            HTTPException: with status 409 if the bot monitor is not attached.
        """
        monitor = dashboard_state.monitor
        if monitor is None:
            raise HTTPException(status_code=409, detail="The bot monitor is not attached yet. Start the bot before syncing.")

        tickers: list[str] = []
        coint_pairs = 0
        active_provider = brokerage_service.provider_name
        for pair in monitor.active_pairs:
            ticker_a = str(pair.get("ticker_a") or "").strip().upper()
            ticker_b = str(pair.get("ticker_b") or "").strip().upper()
            if not ticker_a or not ticker_b:
                continue
            if "-USD" in ticker_a or "-USD" in ticker_b:
                continue
            is_coint = pair.get("is_cointegrated") is True
            if is_coint:
                coint_pairs += 1
            for ticker in (ticker_a, ticker_b):
                if brokerage_service.get_venue(ticker) == active_provider and ticker not in tickers:
                    tickers.append(ticker)

        return coint_pairs, tickers

    async def _place_wallet_orders(
        self,
        plan: list[tuple[str, Decimal]],
        delay_seconds: float = 0.5,
    ) -> tuple[list[dict], int, list[dict]]:
        """
        Place buy orders for each (ticker, amount) in the provided plan and return per-order results.
        
        Parameters:
            plan (list[tuple[str, Decimal]]): Ordered list of (ticker, amount) pairs specifying the target value to buy for each ticker.
            delay_seconds (float): Seconds to wait between placing consecutive orders; no delay if <= 0.
        
        Returns:
            tuple[list[dict], int, list[dict]]: A tuple containing:
                - orders: list of per-order result dicts with keys including `ticker`, `amount`, `status` and, on success, `order_id` or, on failure, `message`.
                - failures: integer count of orders that failed (exceptions or error responses).
                - skipped: list of skipped order records (currently empty in normal flow).
        """
        orders: list[dict] = []
        failures = 0
        skipped = []

        for idx, (ticker, amount) in enumerate(plan, start=1):
            order = {
                "ticker": ticker,
                "amount": float(amount),
                "status": "pending",
            }
            try:
                result = await brokerage_service.place_value_order(
                    ticker,
                    float(amount),
                    "BUY"
                )
                if result.get("status") == "error":
                    failures += 1
                    order.update({"status": "error", "message": result.get("message")})
                else:
                    order.update({
                        "status": "ok",
                        "order_id": result.get("order_id") or result.get("orderId") or result.get("id"),
                    })
            except Exception as exc:
                failures += 1
                order.update({"status": "error", "message": str(exc)})

            orders.append(order)
            if idx < len(plan) and delay_seconds > 0:
                await asyncio.sleep(delay_seconds)

        return orders, failures, skipped

    async def sync_wallet_for_coint(self, request: WalletSyncRequest) -> dict:
        """
        Syncs the account by placing equal-value BUY orders across active cointegrated tickers.
        
        Parameters:
            request (WalletSyncRequest): Request payload containing:
                - budget: total budget to allocate (decimal-like/number).
                - skip_owned: if true, skip tickers already owned.
                - skip_pending: if true, skip tickers with pending buy orders.
                - delay_seconds: delay between placed orders.
        
        Returns:
            dict: Result summary containing:
                - status: "ok" if all orders succeeded, "partial" if some failed.
                - mode: brokerage provider name used.
                - message: human-readable summary.
                - coint_pairs: number of cointegrated pairs considered.
                - candidate_tickers: all active candidate tickers.
                - target_tickers: tickers selected for ordering after filters.
                - skipped: list of skipped ticker records with reasons.
                - budget: requested budget.
                - spendable_cash: cash available after accounting for pending orders.
                - effective_cash: cash adjusted by budget rules.
                - orders: list of order result objects returned by the brokerage.
                - failures: integer count of failed orders.
        """
        if not brokerage_service.test_connection():
            raise HTTPException(status_code=400, detail=f"Brokerage provider {brokerage_service.provider_name} is not configured or reachable.")

        coint_pair_count, candidate_tickers = self._get_active_tickers()
        if not candidate_tickers:
            raise HTTPException(status_code=400, detail=f"No active equity tickers are configured for {brokerage_service.provider_name}.")

        try:
            positions = await _call_brokerage(brokerage_service.get_positions)
            pending_orders = await _call_brokerage(brokerage_service.get_pending_orders)
            account_cash = await _call_brokerage(brokerage_service.get_account_cash)
            pending_value = float(await _call_brokerage(brokerage_service.get_pending_orders_value))
        except Exception as exc:
            logger.error("DASHBOARD: Wallet sync preflight failed: %s", exc)
            raise HTTPException(status_code=502, detail=f"Could not read wallet state: {exc}") from exc

        owned_tickers: list[str] = []
        for position in positions:
            ticker = _position_ticker(position)
            quantity = _safe_float(position.get("quantity"))
            if ticker and quantity is not None and quantity > 0:
                owned_tickers.append(ticker)

        pending_buy_tickers: list[str] = []
        for order in pending_orders:
            ticker = _position_ticker(order)
            quantity = _safe_float(order.get("quantity"))
            if ticker and quantity is not None and quantity > 0:
                pending_buy_tickers.append(ticker)

        target_tickers: list[str] = []
        skipped: list[dict] = []
        for ticker in candidate_tickers:
            broker_ticker = _format_brokerage_ticker(ticker)
            if request.skip_owned and broker_ticker in owned_tickers:
                skipped.append({"ticker": ticker, "reason": "owned"})
                continue
            if request.skip_pending and broker_ticker in pending_buy_tickers:
                skipped.append({"ticker": ticker, "reason": "pending_buy"})
                continue
            target_tickers.append(ticker)

        if not target_tickers:
            result = {
                "status": "ok",
                "mode": brokerage_service.provider_name,
                "message": f"All active {brokerage_service.provider_name} tickers are already owned or pending.",
                "coint_pairs": coint_pair_count,
                "candidate_tickers": candidate_tickers,
                "target_tickers": [],
                "skipped": skipped,
                "budget": float(request.budget),
                "spendable_cash": _safe_float((account_cash or 0.0) - pending_value),
                "orders": [],
                "failures": 0,
            }
            await dashboard_state.add_message("SYSTEM", f"Wallet sync skipped: every active {brokerage_service.provider_name} ticker is already owned or pending.")
            return result

        from src.services.budget_service import budget_service

        raw_cash = float(account_cash or 0.0)
        spendable_cash = max(0.0, raw_cash - max(0.0, pending_value))
        effective_cash = budget_service.get_effective_cash(brokerage_service.provider_name, spendable_cash)
        budget = float(request.budget)

        if budget > effective_cash + 1e-9:
            logger.warning(
                "DASHBOARD: Wallet sync budget %.2f exceeds spendable %s cash/budget %.2f; deferring to broker.",
                budget,
                brokerage_service.provider_name,
                effective_cash,
            )

        try:
            seed_plan = self._build_weighted_wallet_plan(Decimal(str(budget)), [{"ticker": t, "score": 100.0} for t in target_tickers])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        orders, failures, skipped_orders = await self._place_wallet_orders(
            seed_plan,
            request.delay_seconds,
        )

        skipped.extend(skipped_orders)
        submitted = sum(1 for order in orders if order.get("status") == "ok")
        planned = len(seed_plan)

        await dashboard_state.add_message(
            "SYSTEM",
            f"Wallet sync submitted {submitted}/{planned} BUY orders for {brokerage_service.provider_name}.",
            metadata={"type": "wallet_sync", "failures": failures, "tickers": target_tickers, "broker": brokerage_service.provider_name},
        )

        return {
            "status": "ok" if failures == 0 else "partial",
            "mode": brokerage_service.provider_name,
            "message": f"Submitted {submitted}/{planned} BUY orders.",
            "coint_pairs": coint_pair_count,
            "candidate_tickers": candidate_tickers,
            "target_tickers": target_tickers,
            "skipped": skipped,
            "budget": budget,
            "spendable_cash": _safe_float(spendable_cash),
            "effective_cash": _safe_float(effective_cash),
            "orders": orders,
            "failures": failures,
        }

    async def sync_t212_wallet_for_coint(self, request: WalletSyncRequest) -> dict:
        """
        Sync active cointegrated tickers by placing equal-value BUY orders according to the provided request.
        
        Parameters:
            request (WalletSyncRequest): Sync parameters including budget, skip flags for owned/pending tickers, and optional delay between orders.
        
        Returns:
            dict: Result summary with keys including `status` ("ok" or "partial"), `orders` (list of placed order records), `failures` (number of failed orders), and `skipped` (list of skipped tickers).
        """
        return await self.sync_wallet_for_coint(request)

    async def calculate_t212_wallet_recommendations(self, request: WalletRecommendationRequest) -> dict:
        """
        Compute wallet recommendations for a Trading212-compatible request.
        
        Parameters:
            request (WalletRecommendationRequest): Recommendation parameters (budget, skip_owned, skip_pending, include_broken, etc.).
        
        Returns:
            dict: Recommendation payload containing recommended tickers with scores and suggested allocations, skipped items with reasons, budget and cash fields (including `effective_cash` and `cash_limited`), warnings, and any errors or placement-related metadata.
        """
        return await self.calculate_wallet_recommendations(request)

    async def buy_t212_wallet_recommendations(self, request: WalletRecommendationBuyRequest) -> dict:
        """
        Compatibility wrapper for the legacy Trading212 buy-recommendations endpoint that executes the dashboard's wallet buy flow using the provided request.
        
        Parameters:
            request (WalletRecommendationBuyRequest): Payload describing budget, optional ticker overrides, and order placement options.
        
        Returns:
            dict: Result object containing overall `status` ("ok" or "partial"), `orders` (list of placed order records), `failures` (integer count of failed orders), and `skipped` (list of skipped items).
        """
        return await self.buy_wallet_recommendations(request)

    def _coerce_config_value(self, key: str, value: Any) -> Any:
        """
        Coerces and validates a dashboard-editable configuration value according to the editable_config specification.
        
        Parameters:
            key (str): Editable config key; must exist in self.editable_config or a 400 HTTPException is raised.
            value (Any): Input value to coerce. Accepted coercions:
                - "float": converted with float(value)
                - "int": converted with int(value)
                - "bool": accepts booleans or the strings "1","true","yes","on" => True and "0","false","no","off" => False (case-insensitive)
                - "str": trimmed string; if the spec provides `options`, matching is case-insensitive and the canonical option string is returned
        
        Returns:
            Any: The coerced value suitable for assigning to the corresponding settings key.
        
        Raises:
            HTTPException: status 400 if the key is not editable or the value cannot be coerced to the configured type.
        """
        spec = self.editable_config.get(key)
        if not spec:
            raise HTTPException(status_code=400, detail=f"Config key '{key}' is not editable from the dashboard.")
        kind = spec["type"]
        try:
            if kind == "float":
                return float(value)
            if kind == "int":
                return int(value)
            if kind == "bool":
                if isinstance(value, bool):
                    return value
                lowered = str(value).strip().lower()
                if lowered in {"1", "true", "yes", "on"}:
                    return True
                if lowered in {"0", "false", "no", "off"}:
                    return False
                raise ValueError("invalid boolean")
            if kind == "str":
                text = str(value).strip()
                options = spec.get("options")
                if options:
                    normalized_options = {str(option).upper(): str(option) for option in options}
                    option_key = text.upper()
                    if option_key not in normalized_options:
                        raise ValueError(f"expected one of: {', '.join(options)}")
                    return normalized_options[option_key]
                return text
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid value for {key}: {value}") from exc
        return value

    def _mask_sensitive_value(self, value: Any) -> str:
        text = str(value or "")
        if not text:
            return ""
        if len(text) <= 8:
            return "********"
        return f"{text[:4]}...{text[-4:]}"

    def _is_masked_placeholder(self, value: Any) -> bool:
        text = str(value or "")
        return text == "********" or ("..." in text and len(text) <= 16)

    def _audit_value(self, key: str, value: Any) -> Any:
        spec = self.editable_config.get(key, {})
        if spec.get("masked", spec.get("sensitive", False)):
            return self._mask_sensitive_value(value)
        return value

    def get_dashboard_config(self) -> dict:
        """
        Assembles the dashboard's editable configuration, two-factor public status, recent configuration audit entries, and runtime integration flags.
        
        Returns:
            config (dict): A mapping with the following keys:
                - items (list[dict]): Editable configuration entries. Each entry contains:
                    - key (str): Setting name.
                    - value (Any): Current value or a masked placeholder when the setting is sensitive (booleans and enum options are never masked).
                    - type (str): Declared type for the setting (e.g., "str", "int", "float", "bool").
                    - sensitive (bool): Whether the setting is considered sensitive.
                    - options (list, optional): Enumerated choices when the setting exposes options.
                - two_factor (dict): Public status information returned by the TOTP manager.
                - audit_log (list[dict]): Recent configuration change records; old/new values are masked when the setting is marked sensitive.
                - integrations (dict): Runtime integration flags including:
                    - brokerage_provider (str): Active brokerage provider name.
                    - alpaca_configured (bool): Whether Alpaca API credentials appear configured.
                    - alpaca_base_url (str): Configured Alpaca base URL.
                    - t212_configured (bool): Whether a Trading212 key appears configured.
        """
        items = []
        for key, spec in self.editable_config.items():
            raw_value = getattr(settings, key)
            should_mask = spec.get("masked", spec["sensitive"])
            
            # Smart masking: don't mask booleans or items with enumerated options
            if spec["type"] == "bool" or spec.get("options"):
                should_mask = False
                
            item = {
                "key": key,
                "value": self._mask_sensitive_value(raw_value) if should_mask else raw_value,
                "type": spec["type"],
                "sensitive": spec["sensitive"],
            }
            if spec.get("options"):
                item["options"] = spec["options"]
            items.append(item)
        audit_log = []
        for entry in self.persistence.get_recent_config_changes(limit=25):
            key = entry.get("key")
            spec = self.editable_config.get(key, {})
            if spec.get("masked", spec.get("sensitive", False)):
                entry = {
                    **entry,
                    "old_value": self._mask_sensitive_value(entry.get("old_value")),
                    "new_value": self._mask_sensitive_value(entry.get("new_value")),
                }
            audit_log.append(entry)
        return {
            "items": items,
            "two_factor": self.totp.public_status(),
            "audit_log": audit_log,
            "integrations": {
                "brokerage_provider": settings.BROKERAGE_PROVIDER,
                "alpaca_configured": bool(settings.ALPACA_API_KEY.strip() and settings.ALPACA_API_SECRET.strip()),
                "alpaca_base_url": settings.ALPACA_BASE_URL,
                "t212_configured": bool(settings.effective_t212_key.strip()),
            },
        }

    async def update_dashboard_config(self, actor: str, updates: Dict[str, Any], otp_token: Optional[str]) -> dict:
        """
        Update dashboard configuration keys with provided values, persist overrides, audit changes, and return the current dashboard configuration.
        
        Parameters:
            actor (str): Identifier of the actor performing the change for audit messages.
            updates (Dict[str, Any]): Mapping of configuration keys (case-insensitive) to new values. Keys must be declared in the service's editable_config; masked placeholder values for sensitive keys are ignored.
            otp_token (Optional[str]): One-time password or backup code required when any updated key is marked sensitive.
        
        Returns:
            dict: The updated dashboard configuration as returned by get_dashboard_config().
        
        Raises:
            HTTPException(400): If no updates are provided, if no actual changes remain after filtering masked placeholders, or if an unsupported configuration key is included.
            HTTPException(412): If a sensitive key is being changed but two-factor authentication is not enabled.
            HTTPException(403): If a sensitive change is attempted without a valid 2FA token or backup code.
        
        Side effects:
            - Persists each applied override via save_settings_override.
            - Records an audit entry for each changed key via persistence.log_config_change (sensitive values are masked in the audit).
            - Reconfigures the brokerage provider when brokerage-related keys change and refreshes the dashboard monitor's brokerage client when a monitor exists.
            - Emits a system message describing the applied configuration updates.
        """
        if not updates:
            raise HTTPException(status_code=400, detail="No configuration updates provided.")

        normalized_updates: Dict[str, Any] = {}
        requires_2fa = False
        for key, value in updates.items():
            normalized_key = str(key).strip().upper()
            if normalized_key not in self.editable_config:
                raise HTTPException(status_code=400, detail=f"Unsupported configuration key: {normalized_key}")
            spec = self.editable_config.get(normalized_key, {})
            should_mask = spec.get("masked", spec.get("sensitive", False))
            if should_mask and self._is_masked_placeholder(value):
                continue
            normalized_updates[normalized_key] = self._coerce_config_value(normalized_key, value)
            requires_2fa = requires_2fa or self.editable_config[normalized_key]["sensitive"]

        if not normalized_updates:
            raise HTTPException(status_code=400, detail="No changed configuration values provided.")

        if requires_2fa:
            status = self.totp.public_status()
            if not status["enabled"]:
                raise HTTPException(status_code=412, detail="Two-factor authentication must be configured before sensitive changes.")
            if not otp_token or not self.totp.verify_token_or_backup(otp_token):
                raise HTTPException(status_code=403, detail="A valid 2FA token is required for this change.")

        for key, value in normalized_updates.items():
            old_value = getattr(settings, key)
            setattr(settings, key, value)
            save_settings_override({key: value})
            self.persistence.log_config_change(
                actor=actor,
                key=key,
                old_value=self._audit_value(key, old_value),
                new_value=self._audit_value(key, value),
                requires_2fa=self.editable_config[key]["sensitive"],
            )

        brokerage_config_keys = {
            "BROKERAGE_PROVIDER",
            "T212_API_KEY",
            "T212_API_SECRET",
            "TRADING_212_API_KEY",
            "TRADING_212_MODE",
            "ALPACA_API_KEY",
            "ALPACA_API_SECRET",
            "ALPACA_BASE_URL",
        }
        if brokerage_config_keys.intersection(normalized_updates):
            brokerage_service.configure_provider()
            if dashboard_state.monitor is not None:
                dashboard_state.monitor.brokerage = BrokerageService()

        await dashboard_state.add_message(
            "SYSTEM",
            f"Configuration updated by {actor}: {', '.join(sorted(normalized_updates.keys()))}",
            metadata={"type": "config_update", "requires_2fa": requires_2fa},
        )
        return self.get_dashboard_config()

    def _get_process_metrics(self) -> dict:
        timestamp = _utcnow().isoformat()
        cpu_pct = None
        rss_mb = None
        vms_mb = None
        threads = None
        net_sent_mb = None
        net_recv_mb = None
        system_memory_pct = None
        try:
            import psutil  # type: ignore

            proc = psutil.Process(os.getpid())
            mem = proc.memory_info()
            cpu_pct = psutil.cpu_percent(interval=None)
            rss_mb = mem.rss / (1024 * 1024)
            vms_mb = mem.vms / (1024 * 1024)
            threads = proc.num_threads()
            net = psutil.net_io_counters()
            if net:
                net_sent_mb = net.bytes_sent / (1024 * 1024)
                net_recv_mb = net.bytes_recv / (1024 * 1024)
            vm = psutil.virtual_memory()
            system_memory_pct = float(vm.percent)
        except Exception:
            try:
                import resource

                usage = resource.getrusage(resource.RUSAGE_SELF)
                rss_mb = float(usage.ru_maxrss) / 1024.0
            except Exception:
                pass
        return _scrub_non_finite(
            {
                "timestamp": timestamp,
                "cpu_pct": cpu_pct,
                "rss_mb": rss_mb,
                "vms_mb": vms_mb,
                "threads": threads,
                "net_sent_mb": net_sent_mb,
                "net_recv_mb": net_recv_mb,
                "system_memory_pct": system_memory_pct,
                "uptime_seconds": max(0, int((_utcnow() - datetime.fromisoformat(dashboard_state.bot_start_time)).total_seconds())),
                "hostname": socket.gethostname(),
            }
        )

    def latest_health(self) -> dict:
        current = self._get_process_metrics()
        if not self.health_history or self.health_history[-1]["timestamp"] != current["timestamp"]:
            self.health_history.append(current)
        return current

    def health_snapshot(self) -> dict:
        current = self.latest_health()
        return {
            "status": "healthy",
            "current": current,
            "history": list(self.health_history),
        }

    def _tail_log_file(self, path: Path, limit: int) -> List[str]:
        max_bytes = 1024 * 1024
        limit = max(1, limit)
        try:
            with path.open("rb") as fh:
                fh.seek(0, os.SEEK_END)
                size = fh.tell()
                fh.seek(max(0, size - max_bytes))
                data = fh.read()
        except Exception as exc:
            logger.warning("DASHBOARD: Could not read logs from %s: %s", path, exc)
            return []

        text = data.decode("utf-8", errors="replace")
        if text and not text.startswith("\n") and size > max_bytes:
            text = text.split("\n", 1)[-1]
        return text.splitlines()[-limit:]

    def read_recent_logs(self, limit: int = 200) -> dict:
        log_dir = Path("logs")
        try:
            files = sorted([path for path in log_dir.glob("*.log") if path.is_file()], key=lambda path: path.stat().st_mtime, reverse=True)
        except Exception as exc:
            logger.warning("DASHBOARD: Could not list log files from %s: %s", log_dir, exc)
            files = []
        selected = files[0] if files else None
        lines: List[str] = []
        if selected:
            lines = self._tail_log_file(selected, limit)
        return {
            "file": str(selected) if selected else None,
            "lines": lines,
            "events": self.persistence.get_recent_events(limit=min(limit, 100)),
        }

    async def bot_control(self, action: str, actor: str) -> dict:
        action = action.lower()
        if action not in {"start", "stop", "restart"}:
            raise HTTPException(status_code=400, detail=f"Unsupported action '{action}'.")
        desired_state = {"start": "RUNNING", "stop": "STOPPED", "restart": "RESTARTING"}[action]
        dashboard_state.desired_bot_state = desired_state
        dashboard_state.last_control_action = {
            "action": action,
            "actor": actor,
            "timestamp": _utcnow().isoformat(),
        }
        detail = {
            "start": "Dashboard requested bot start.",
            "stop": "Dashboard requested bot stop.",
            "restart": "Dashboard requested graceful restart.",
        }[action]
        await dashboard_state.add_message("SYSTEM", detail, metadata={"type": "bot_control", "action": action, "actor": actor})
        return {"status": "accepted", "requested_state": desired_state, "action": action}

    async def build_summary(self) -> dict:
        """
        Builds a snapshot summary of trading and system metrics for the dashboard.
        
        Returns:
            dict: A scrubbed mapping containing:
                - `current_balance` (float|None): Available cash from portfolio metrics.
                - `capital_deployed` (float|None): Total invested capital from portfolio metrics.
                - `profit_today` (float|None): Daily profit from portfolio metrics.
                - `trades_today` (int): Number of trades opened today (derived from recent trade history).
                - `win_rate` (float): Trade win rate (0.0–1.0) from persisted trade summary.
                - `wins` (int): Count of winning trades from persisted trade summary.
                - `losses` (int): Count of losing trades from persisted trade summary.
                - `closed_trades` (int): Count of closed trades from persisted trade summary.
                - `system_uptime_seconds` (int|None): Uptime in seconds from the latest health snapshot.
                - `system_uptime_human` (str): Human-readable uptime derived from `system_uptime_seconds`.
                - `bot_status` (str): Desired bot state from dashboard state.
                - `stage` (str): Current dashboard stage.
                - `cpu_pct` (float|None): CPU usage percentage from the latest health snapshot.
                - `memory_pct` (float|None): System memory usage percentage from the latest health snapshot.
                - `open_signals` (int): Number of active signals tracked by the dashboard.
                - `open_positions` (int): Number of open signals persisted in storage.
                - `mode` (str): Runtime mode returned by `dashboard_state.runtime_info()` (e.g., "DEV", "PAPER", "LIVE").
        """
        from src.services.persistence_service import persistence_service

        trade_summary = await persistence_service.get_trade_summary()
        today = _utcnow().date().isoformat()
        history = await persistence_service.get_trade_history(page=1, page_size=500)
        trades_today = 0
        for item in history["items"]:
            opened_at = item.get("opened_at")
            if opened_at and opened_at[:10] == today:
                trades_today += 1
        latest_health = self.latest_health()
        uptime_seconds = latest_health.get("uptime_seconds")
        return _scrub_non_finite(
            {
                "current_balance": dashboard_state.portfolio_metrics.get("available_cash"),
                "capital_deployed": dashboard_state.portfolio_metrics.get("total_invested"),
                "profit_today": dashboard_state.portfolio_metrics.get("daily_profit"),
                "trades_today": trades_today,
                "win_rate": trade_summary.get("win_rate", 0.0),
                "wins": int(trade_summary.get("wins", 0)),
                "losses": int(trade_summary.get("losses", 0)),
                "closed_trades": int(trade_summary.get("closed_trades", 0)),
                "system_uptime_seconds": uptime_seconds,
                "system_uptime_human": str(timedelta(seconds=uptime_seconds or 0)),
                "bot_status": dashboard_state.desired_bot_state,
                "stage": dashboard_state.stage,
                "cpu_pct": latest_health.get("cpu_pct"),
                "memory_pct": latest_health.get("system_memory_pct"),
                "open_signals": len(dashboard_state.active_signals),
                "open_positions": len(await persistence_service.get_open_signals()),
                "mode": dashboard_state.runtime_info()["mode"],
            }
        )

    async def trigger_pair_discovery(self, actor: str) -> dict:
        """
        Manually triggers a global pair discovery cycle using PortfolioManagerAgent.
        This runs in the background to avoid blocking the dashboard.
        """
        from src.agents.portfolio_manager_agent import portfolio_manager
        
        # We run it as a background task
        asyncio.create_task(portfolio_manager.run_discovery())
        
        await dashboard_state.add_message(
            "SYSTEM",
            f"Global pair discovery triggered by {actor}.",
            metadata={"type": "pair_discovery", "actor": actor}
        )
        return {"status": "accepted", "message": "Discovery cycle started in background."}

    async def start(self):
        """
        Start the dashboard service: begin telemetry broadcasting, launch the ASGI server, and schedule background polling tasks.
        
        Initializes and starts the telemetry broadcast loop, creates and starts the Uvicorn server on 0.0.0.0:8080, and schedules periodic background tasks for metrics and system health polling. Errors during startup are logged.
        """
        try:
            from src.services.telemetry_service import telemetry_service

            telemetry_service.start_broadcast_loop()
            config = uvicorn.Config(app, host="0.0.0.0", port=8080, log_level="info")
            self.server = uvicorn.Server(config)
            asyncio.create_task(self.server.serve())
            asyncio.create_task(self._poll_metrics())
            asyncio.create_task(self._poll_system_health())
            logger.info("!!! DASHBOARD SERVER STARTED ON PORT 8080 !!!")
        except Exception as exc:
            logger.error("DASHBOARD STARTUP ERROR: %s", exc)

    async def _poll_system_health(self):
        while True:
            try:
                self.health_history.append(self._get_process_metrics())
            except Exception as exc:
                logger.warning("DASHBOARD HEALTH POLLING ERROR: %s", exc)
            await asyncio.sleep(10)

    async def _poll_metrics(self):
        """
        Periodically polls brokerage, budget, and persistence services to refresh dashboard metrics, market regime, and global strategy accuracy, then updates and broadcasts the dashboard state.
        
        This background coroutine runs an infinite loop that gathers provider-specific and WEB3 cash, pending orders, budget usage, daily and total PnL, and invested amounts from configured services, composes a consolidated metrics payload (including a backward-compatibility alias for the legacy `t212` key), fetches the latest market regime and global accuracy, and applies these updates to the shared dashboard state for broadcasting to listeners. Errors encountered while fetching data are logged; the loop pauses between iterations.
        """
        while True:
            try:
                from src.services.budget_service import budget_service
                from src.services.persistence_service import persistence_service

                today = datetime.now().date().isoformat()
                active_provider = brokerage_service.provider_name

                equity_cash: Optional[float] = None
                equity_pending: float = 0.0
                try:
                    equity_cash = await brokerage_service.get_account_cash()
                    equity_pending = await brokerage_service.get_pending_orders_value()
                except Exception as exc:
                    logger.warning("DASHBOARD: Could not fetch %s cash: %s", active_provider, exc)

                equity_budget_info = budget_service.get_venue_budget_info(active_provider)
                equity_daily_budget = equity_budget_info["total"] if equity_budget_info["total"] > 0 else ((equity_cash * 0.25) if equity_cash is not None else None)
                equity_daily_used = equity_budget_info["used"]
                equity_daily_pnl = await persistence_service.get_daily_pnl_for_date(today, venue=active_provider)
                equity_total_pnl = await persistence_service.get_total_pnl(venue=active_provider)
                equity_invested = await persistence_service.get_current_investment(venue=active_provider)

                web3_cash: Optional[float] = None
                if settings.web3_enabled:
                    try:
                        web3_cash = await brokerage_service.get_web3_account_cash()
                    except Exception as exc:
                        logger.warning("DASHBOARD: Could not fetch WEB3 cash: %s", exc)

                web3_budget_info = budget_service.get_venue_budget_info("WEB3")
                web3_daily_budget = web3_budget_info["total"] if web3_budget_info["total"] > 0 else ((web3_cash * 0.25) if web3_cash is not None else None)
                web3_daily_used = web3_budget_info["used"]
                web3_daily_pnl = await persistence_service.get_daily_pnl_for_date(today, venue="WEB3")
                web3_total_pnl = await persistence_service.get_total_pnl(venue="WEB3")
                web3_invested = await persistence_service.get_current_investment(venue="WEB3")

                global_cash = sum(c for c in [equity_cash, web3_cash] if c is not None) or None
                global_pending = equity_pending
                global_spendable = (global_cash - global_pending) if global_cash is not None else None
                global_daily_budget = sum(b for b in [equity_daily_budget, web3_daily_budget] if b is not None) or None
                global_daily_used = equity_daily_used + web3_daily_used
                global_daily_pnl = await persistence_service.get_daily_pnl_for_date(today)
                global_total_pnl = await persistence_service.get_total_pnl()
                global_invested = await persistence_service.get_current_investment()

                metrics = {
                    "total_revenue": global_total_pnl,
                    "total_invested": global_invested,
                    "daily_profit": global_daily_pnl,
                    "available_cash": global_cash,
                    "pending_orders_value": global_pending,
                    "spendable_cash": global_spendable,
                    "daily_budget": global_daily_budget,
                    "daily_usage_pct": ((global_daily_used / global_daily_budget * 100) if global_daily_budget and global_daily_budget > 0 else None),
                    "equity_provider": active_provider,
                    "equity": {
                        "available_cash": equity_cash,
                        "pending_orders_value": equity_pending,
                        "spendable_cash": (equity_cash - equity_pending) if equity_cash is not None else None,
                        "daily_budget": equity_daily_budget,
                        "daily_used": equity_daily_used,
                        "daily_usage_pct": ((equity_daily_used / equity_daily_budget * 100) if equity_daily_budget and equity_daily_budget > 0 else None),
                        "daily_profit": equity_daily_pnl,
                        "total_revenue": equity_total_pnl,
                        "total_invested": equity_invested,
                    },
                    "web3": {
                        "available_cash": web3_cash,
                        "pending_orders_value": 0.0,
                        "spendable_cash": web3_cash,
                        "daily_budget": web3_daily_budget,
                        "daily_used": web3_daily_used,
                        "daily_usage_pct": ((web3_daily_used / web3_daily_budget * 100) if web3_daily_budget and web3_daily_budget > 0 else None),
                        "daily_profit": web3_daily_pnl,
                        "total_revenue": web3_total_pnl,
                        "total_invested": web3_invested,
                    },
                }
                # Alias for backward compatibility
                metrics["t212"] = metrics["equity"]

                regime = await persistence_service.get_latest_market_regime()
                accuracy_str = await persistence_service.get_system_state(
                    "global_strategy_accuracy",
                    str(settings.GLOBAL_STRATEGY_ACCURACY_DEFAULT),
                )

                async with dashboard_state._lock:
                    dashboard_state.portfolio_metrics.update(metrics)
                    if regime:
                        dashboard_state.market_regime = regime
                    dashboard_state.global_accuracy = float(accuracy_str)
                    await dashboard_state._broadcast()
            except Exception as exc:
                logger.error("DASHBOARD POLLING ERROR: %s", exc)
            await asyncio.sleep(10)

    async def update_metrics(self, metrics: dict):
        await dashboard_state.update_metrics(metrics)

    async def update(self, stage: str, details: str, pnl: float = None, signals: int = None, active_signals: list = None):
        await dashboard_state.update(stage, details, pnl, signals, active_signals)

    async def update_state(self, stage: str, details: str, pnl: float = None, signals: int = None, active_signals: list = None):
        await dashboard_state.update(stage, details, pnl, signals, active_signals)


dashboard_service = DashboardService()


async def _login(payload: DashboardLoginRequest, request: Request):
    verify_security_token(payload.security_token)
    status = dashboard_service.totp.public_status()
    if payload.otp_token:
        if not status["enabled"] or not dashboard_service.totp.verify_token_or_backup(payload.otp_token):
            raise HTTPException(status_code=403, detail="Invalid authenticator or backup code.")
        session = session_manager.create(actor=payload.actor)
        await dashboard_state.add_message(
            "SYSTEM",
            "Dashboard login succeeded with fallback code.",
            metadata={"type": "dashboard_login", "actor": payload.actor, "method": "otp"},
        )
        return {"status": "ok", **session, "two_factor": dashboard_service.totp.public_status()}

    try:
        challenge = await login_challenge_manager.create(payload.actor, request)
        return {**challenge, "two_factor": dashboard_service.totp.public_status()}
    except HTTPException:
        if status["enabled"]:
            raise
        session = session_manager.create(actor=payload.actor)
        await dashboard_state.add_message(
            "SYSTEM",
            "Dashboard login succeeded without notification approval because notifications are unavailable.",
            metadata={"type": "dashboard_login", "actor": payload.actor, "method": "token_only_fallback"},
        )
        return {"status": "ok", **session, "two_factor": dashboard_service.totp.public_status()}


@app.options("/api/auth/login")
@app.options("/api/auth/login/")
async def login_preflight():
    return {"status": "ok"}


@app.post("/api/auth/login")
@app.post("/api/auth/login/")
async def login(payload: DashboardLoginRequest, request: Request):
    return await _login(payload, request)


@app.options("/api/auth/login/complete")
@app.options("/api/auth/login/complete/")
async def login_complete_preflight():
    return {"status": "ok"}


@app.post("/api/auth/login/complete")
@app.post("/api/auth/login/complete/")
async def login_complete(request: DashboardLoginCompleteRequest):
    result = login_challenge_manager.complete(request.challenge_id)
    if result["status"] == "approved":
        await dashboard_state.add_message(
            "SYSTEM",
            "Dashboard login approved by notification.",
            metadata={"type": "dashboard_login", "actor": result.get("actor"), "method": "notification"},
        )
        result["status"] = "ok"
        return {**result, "two_factor": dashboard_service.totp.public_status()}
    return {**result, "two_factor": dashboard_service.totp.public_status()}


@app.options("/api/auth/logout")
@app.options("/api/auth/logout/")
async def logout_preflight():
    return {"status": "ok"}


@app.post("/api/auth/logout")
@app.post("/api/auth/logout/")
async def logout(token: str = Query(None), session: str = Query(None)):
    verify_token(token, session)
    session_manager.revoke(session or _dashboard_auth_session.get())
    return {"status": "ok"}


@app.get("/stream")
async def message_stream(request: Request, token: str = Query(None), session: str = Query(None)):
    verify_token(token, session)
    q = asyncio.Queue()
    async with dashboard_state._lock:
        dashboard_state.listeners.append(q)
        await q.put(
            json.dumps(
                {
                    "stage": dashboard_state.stage,
                    "details": dashboard_state.details,
                    "bot_start_time": dashboard_state.bot_start_time,
                    "runtime": dashboard_state.runtime_info(),
                    "metrics": dashboard_state.portfolio_metrics,
                    "market_regime": dashboard_state.market_regime,
                    "global_accuracy": dashboard_state.global_accuracy,
                    "active_signals": dashboard_state.active_signals,
                    "terminal_messages": dashboard_state.terminal_messages,
                    "timestamp": _utcnow().isoformat(),
                }
            )
        )

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                data = await q.get()
                yield {"event": "message", "data": data}
        except asyncio.CancelledError:
            pass
        finally:
            async with dashboard_state._lock:
                if q in dashboard_state.listeners:
                    dashboard_state.listeners.remove(q)

    return EventSourceResponse(event_generator())


@app.get("/ping")
async def ping():
    return {"status": "alive", "stage": dashboard_state.stage}


@app.websocket("/ws/telemetry")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(None), session: str = Query(None)):
    if token or session:
        try:
            verify_token(token, session)
        except HTTPException:
            await websocket.close(code=4003)
            return
        if not await connection_manager.connect(websocket):
            return
    else:
        await websocket.accept()
        try:
            raw_auth = await asyncio.wait_for(websocket.receive_text(), timeout=5)
            auth_payload = json.loads(raw_auth)
            if auth_payload.get("type") != "auth":
                raise ValueError("First WebSocket message must authenticate.")
            verify_token(auth_payload.get("token"), auth_payload.get("session"))
        except Exception as exc:
            logger.warning("WebSocket auth failed: %s", exc)
            await websocket.close(code=4003)
            return
        if not await connection_manager.connect(websocket, accept=False):
            return

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        connection_manager.disconnect(websocket)
    except Exception as exc:
        logger.error("WebSocket error: %s", exc)
        connection_manager.disconnect(websocket)


@app.post("/api/terminal/command")
async def terminal_command(request: CommandRequest, token: str = Query(None), session: str = Query(None)):
    verify_token(token, session)
    from src.services.notification_service import notification_service

    result = await notification_service.handle_dashboard_command(request.command, request.metadata)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result


@app.get("/api/settings")
async def get_settings(token: str = Query(None), session: str = Query(None)):
    verify_token(token, session)
    return {"approval_threshold": settings.APPROVAL_THRESHOLD}


@app.post("/api/settings")
async def update_settings(request: SettingsUpdateRequest, token: str = Query(None), session: str = Query(None)):
    verify_token(token, session)
    old_value = settings.APPROVAL_THRESHOLD
    settings.APPROVAL_THRESHOLD = request.approval_threshold
    save_settings_override({"APPROVAL_THRESHOLD": request.approval_threshold})
    dashboard_service.persistence.log_config_change(
        actor="dashboard",
        key="APPROVAL_THRESHOLD",
        old_value=old_value,
        new_value=request.approval_threshold,
        requires_2fa=False,
    )
    await dashboard_state.add_message("SYSTEM", f"Auto-trade threshold updated to {request.approval_threshold} EUR")
    return {"status": "ok", "approval_threshold": settings.APPROVAL_THRESHOLD}


@app.get("/api/stats/summary")
async def get_stats_summary(token: str = Query(None), session: str = Query(None)):
    verify_token(token, session)
    return await dashboard_service.build_summary()


@app.get("/api/stats/trades")
async def get_trade_history(
    token: str = Query(None),
    session: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    venue: Optional[str] = Query(None),
):
    verify_token(token, session)
    from src.services.persistence_service import persistence_service

    return await persistence_service.get_trade_history(
        page=page,
        page_size=page_size,
        search=search,
        status=status,
        venue=venue,
    )


@app.get("/api/stats/charts/{metric}")
async def get_chart_metric(metric: str, token: str = Query(None), session: str = Query(None)):
    verify_token(token, session)
    from src.services.persistence_service import persistence_service

    try:
        return await persistence_service.get_chart_series(metric)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/system/health")
async def get_system_health(token: str = Query(None), session: str = Query(None)):
    verify_token(token, session)
    return dashboard_service.health_snapshot()


@app.get("/api/system/logs")
async def get_system_logs(token: str = Query(None), session: str = Query(None), limit: int = Query(100, ge=10, le=500)):
    verify_token(token, session)
    return dashboard_service.read_recent_logs(limit=limit)


@app.post("/api/bot/restart")
async def restart_bot(token: str = Query(None), session: str = Query(None)):
    verify_token(token, session)
    return await dashboard_service.bot_control("restart", actor="dashboard")


@app.post("/api/bot/control")
async def control_bot(request: BotControlRequest, token: str = Query(None), session: str = Query(None)):
    verify_token(token, session)
    return await dashboard_service.bot_control(request.action, actor=request.actor)


@app.get("/api/config")
async def get_config(token: str = Query(None), session: str = Query(None)):
    verify_token(token, session)
    return dashboard_service.get_dashboard_config()


@app.post("/api/config/update")
async def update_config(request: DashboardConfigUpdateRequest, token: str = Query(None), session: str = Query(None)):
    verify_token(token, session)
    return await dashboard_service.update_dashboard_config(
        actor=request.actor,
        updates=request.updates,
        otp_token=request.otp_token,
    )


@app.post("/api/auth/2fa/initiate")
async def initiate_2fa(token: str = Query(None), session: str = Query(None)):
    verify_token(token, session)
    return dashboard_service.totp.initiate_setup()


@app.post("/api/auth/2fa/verify")
async def verify_2fa(request: TOTPVerifyRequest, token: str = Query(None), session: str = Query(None)):
    """
    Verify a submitted TOTP or backup code and enable or confirm two-factor authentication for the dashboard.
    
    Parameters:
        request (TOTPVerifyRequest): Payload containing the TOTP/backup token to verify.
        token (str, optional): Optional dashboard API security token or bearer value used to authenticate the request prior to 2FA verification.
        session (str, optional): Optional dashboard session identifier used to authenticate the request prior to 2FA verification.
    
    Returns:
        dict: If the request enables 2FA, returns {"status": "ok", "two_factor": <public_status>}.
              If the request only verifies a token, returns {"status": "ok", "verified": True, "two_factor": <public_status>}.
    
    Raises:
        HTTPException: 403 if the provided TOTP or backup code is invalid.
    """
    verify_token(token, session)
    if dashboard_service.totp.verify_setup(request.token):
        await dashboard_state.add_message("SYSTEM", "Two-factor authentication enabled for dashboard config changes.")
        return {"status": "ok", "two_factor": dashboard_service.totp.public_status()}
    if dashboard_service.totp.verify_token_or_backup(request.token):
        return {"status": "ok", "verified": True, "two_factor": dashboard_service.totp.public_status()}
    raise HTTPException(status_code=403, detail="Invalid 2FA token.")

@app.post("/api/pairs/discover")
async def discover_pairs(token: str = Query(None), session: str = Query(None)):
    verify_token(token, session)
    return await dashboard_service.trigger_pair_discovery(actor="dashboard")

@app.get("/api/pairs")
async def list_pairs(token: str = Query(None), session: str = Query(None)):
    """
    Return a snapshot of pair discovery state including active pairs enriched with latest z-scores and last cointegration check timestamps.
    
    The response includes:
    - `active_pairs`: list of active pair objects with added `last_cointegration_check` (ISO 8601 string or `None`) and `last_z_score` (float or `None`).
    - `configured_pairs`: the dashboard's configured pair list from settings.
    - `crypto_test_pairs`: the configured crypto test pairs from settings.
    - `dev_mode`: current development mode flag from settings.
    
    Returns:
        dict: The scrubbed response object described above, with non-finite floats replaced by `None`.
    """
    verify_token(token, session)
    monitor = dashboard_state.monitor

    active_serialized: list = []
    last_check_map: dict = {}
    if monitor is not None:
        for pair in monitor.active_pairs:
            active_serialized.append(_serialize_pair(pair))
            last_check_iso = None
            last_date = monitor.last_cointegration_check.get(pair.get("id"))
            if last_date:
                last_check_iso = last_date.isoformat()
            last_check_map[pair.get("id")] = last_check_iso

    z_score_map: dict = {}
    try:
        from src.services.redis_service import redis_service

        for pair_id in [p["id"] for p in active_serialized]:
            try:
                state = await redis_service.get_kalman_state(pair_id)
                if state and "z_score" in state:
                    z = _safe_float(state["z_score"])
                    if z is not None:
                        z_score_map[pair_id] = z
            except Exception:
                pass
    except Exception as exc:
        logger.warning("DASHBOARD: Could not fetch z-scores from Redis: %s", exc)

    for entry in active_serialized:
        pid = entry["id"]
        entry["last_cointegration_check"] = last_check_map.get(pid)
        entry["last_z_score"] = z_score_map.get(pid)

    return _scrub_non_finite(
        {
            "active_pairs": active_serialized,
            "configured_pairs": settings.ARBITRAGE_PAIRS,
            "crypto_test_pairs": settings.CRYPTO_TEST_PAIRS,
            "dev_mode": settings.DEV_MODE,
        }
    )


@app.post("/api/pairs")
async def update_pairs(request: PairsUpdateRequest, token: str = Query(None), session: str = Query(None)):
    """
    Update the configured arbitrage pairs (and optional crypto pairs), persist the overrides, and optionally hot-reload the monitoring service.
    
    Parameters:
        request (PairsUpdateRequest): Payload containing `pairs`, optional `crypto_pairs`, and `apply_now` flag.
            - `pairs`: list of pair objects; each pair must contain two distinct tickers.
            - `crypto_pairs` (optional): list of crypto pair objects; validated similarly to `pairs`.
            - `apply_now` (bool): if true and a monitor is attached, attempts to hot-reload pairs immediately.
        token (str): Dashboard security token (from query/header; validated via verify_token). Omit documenting if provided by middleware.
        session (str): Dashboard session token (from query/header; validated via verify_token). Omit documenting if provided by middleware.
    
    Raises:
        HTTPException: 400 if no valid pairs are provided or if any pair has identical tickers.
    
    Returns:
        dict: {
            "status": "ok",
            "saved_pairs": int,       # number of saved non-crypto pairs
            "reloaded": bool,         # true if hot-reload succeeded
            "reload_error": str|null  # error message if hot-reload failed
        }
    """
    verify_token(token, session)

    seen = set()
    cleaned: list = []
    for p in request.pairs:
        ticker_a = (p.ticker_a or "").strip().upper()
        ticker_b = (p.ticker_b or "").strip().upper()
        if not ticker_a or not ticker_b:
            continue
        if ticker_a == ticker_b:
            raise HTTPException(status_code=400, detail=f"Pair must have two distinct tickers (got {ticker_a}/{ticker_b}).")
        key = f"{ticker_a}_{ticker_b}"
        if key in seen:
            continue
        seen.add(key)
        cleaned.append({"ticker_a": ticker_a, "ticker_b": ticker_b})

    if not cleaned:
        raise HTTPException(status_code=400, detail="At least one valid pair is required.")

    crypto_cleaned: Optional[list] = None
    if request.crypto_pairs is not None:
        crypto_cleaned = []
        seen_c = set()
        for p in request.crypto_pairs:
            ta = (p.ticker_a or "").strip().upper()
            tb = (p.ticker_b or "").strip().upper()
            if not ta or not tb or ta == tb:
                continue
            k = f"{ta}_{tb}"
            if k in seen_c:
                continue
            seen_c.add(k)
            crypto_cleaned.append({"ticker_a": ta, "ticker_b": tb})

    save_pairs_override(cleaned, crypto_cleaned)
    settings.ARBITRAGE_PAIRS = cleaned
    if crypto_cleaned is not None:
        settings.CRYPTO_TEST_PAIRS = crypto_cleaned

    reloaded = False
    reload_error: Optional[str] = None
    monitor = dashboard_state.monitor
    if request.apply_now and monitor is not None:
        try:
            await monitor.reload_pairs()
            reloaded = True
        except Exception as exc:
            reload_error = str(exc)
            logger.error("DASHBOARD: Hot-reload of pairs failed: %s", exc)

    await dashboard_state.add_message(
        "SYSTEM",
        f"Pair universe updated ({len(cleaned)} pairs)" + (" - hot-reloaded" if reloaded else " - restart required to apply"),
    )

    return {
        "status": "ok",
        "saved_pairs": len(cleaned),
        "reloaded": reloaded,
        "reload_error": reload_error,
    }


@app.post("/api/wallet/sync")
@app.post("/api/t212/wallet/sync")
async def sync_wallet(request: WalletSyncRequest, token: str = Query(None), session: str = Query(None)):
    """
    Synchronize the wallet by placing buy orders to equalize allocation across active cointegrated tickers.
    
    Parameters:
        request (WalletSyncRequest): Desired budget and options for syncing (e.g., budget amount, skip_owned, skip_pending, delay_seconds).
    
    Returns:
        dict: Operation result containing at least `status` (`"ok"` or `"partial"`), `orders` (placed order records), and `failures` (number of failed orders). Additional fields such as `skipped` may be present.
    """
    verify_token(token, session)
    return await dashboard_service.sync_wallet_for_coint(request)



@app.get("/api/wallet/recommendations")
@app.get("/api/wallet/recommendations/") 
@app.get("/api/t212/wallet/recommendations")
@app.get("/api/t212/wallet/recommendations/")
async def get_wallet_recommendations(
    budget: float = Query(..., gt=0),
    include_broken: bool = Query(False),
    skip_owned: bool = Query(True),
    skip_pending: bool = Query(True),
    token: str = Query(None),
    session: str = Query(None),
):
    """
    Return wallet buy recommendations based on the provided budget and filters.
    
    Returns:
        dict: A response containing recommended tickers with suggested allocations, skipped entries and reasons, budget and cash metadata, flags such as `can_buy` and `cash_limited`, and any warnings.
    """
    verify_token(token, session)
    return await dashboard_service.calculate_wallet_recommendations(
        WalletRecommendationRequest(
            budget=budget,
            include_broken=include_broken,
            skip_owned=skip_owned,
            skip_pending=skip_pending,
        )
    )


@app.post("/api/wallet/recommendations/buy")
@app.post("/api/t212/wallet/recommendations/buy")
async def buy_wallet_recommendations(
    request: WalletRecommendationBuyRequest,
    token: str = Query(None),
    session: str = Query(None),
):
    """
    Place buy orders for weighted wallet recommendations based on the provided request.
    
    Validates dashboard authentication using the optional `token` or `session` query parameters and delegates to the dashboard service to compute recommendations and place orders.
    
    Parameters:
        request (WalletRecommendationBuyRequest): Request payload containing `budget` and optional `tickers` to restrict purchases.
        token (str, optional): Optional security token; used for authentication when provided.
        session (str, optional): Optional dashboard session token; used for authentication when provided.
    
    Returns:
        dict: Result object containing `status` (`"ok"` or `"partial"`), `orders` (list of placed order records), `failures` (number of failed orders), and `skipped` (list of skipped tickers).
    """
    verify_token(token, session)
    return await dashboard_service.buy_wallet_recommendations(request)


@app.get("/api/positions")
async def list_open_positions(token: str = Query(None), session: str = Query(None)):
    verify_token(token, session)
    from src.services.data_service import data_service
    from src.services.persistence_service import persistence_service

    try:
        signals = await persistence_service.get_open_signals()
    except Exception as exc:
        logger.error("DASHBOARD: Failed to fetch open signals: %s", exc)
        return {"positions": []}

    if not signals:
        return {"positions": []}

    all_tickers: list = []
    for sig in signals:
        for leg in sig.get("legs", []):
            all_tickers.append(leg["ticker"])
    latest_prices: dict = {}
    try:
        if all_tickers:
            latest_prices = await data_service.get_latest_price_async(list(set(all_tickers)))
    except Exception as exc:
        logger.warning("DASHBOARD: Could not fetch latest prices for positions: %s", exc)

    positions: list = []
    for sig in signals:
        legs = sig.get("legs", [])
        if len(legs) < 2:
            continue
        leg_a, leg_b = legs[0], legs[1]
        pnl = 0.0
        current_value = 0.0
        for leg in legs:
            cur = latest_prices.get(leg["ticker"])
            if cur is None:
                continue
            qty = leg["quantity"]
            entry = leg["price"]
            current_value += cur * qty
            if leg["side"] == "BUY":
                pnl += (cur - entry) * qty
            else:
                pnl += (entry - cur) * qty
        opened_at = leg_a.get("execution_timestamp")
        if isinstance(opened_at, datetime):
            opened_at = opened_at.isoformat()
        positions.append(
            {
                "signal_id": sig.get("signal_id"),
                "ticker_a": leg_a["ticker"],
                "ticker_b": leg_b["ticker"],
                "side_a": leg_a["side"],
                "side_b": leg_b["side"],
                "qty_a": _safe_float(leg_a["quantity"]),
                "qty_b": _safe_float(leg_b["quantity"]),
                "entry_a": _safe_float(leg_a["price"]),
                "entry_b": _safe_float(leg_b["price"]),
                "current_a": _safe_float(latest_prices.get(leg_a["ticker"])),
                "current_b": _safe_float(latest_prices.get(leg_b["ticker"])),
                "cost_basis": _safe_float(sig.get("total_cost_basis", 0.0)),
                "current_value": _safe_float(current_value),
                "pnl": _safe_float(pnl),
                "opened_at": opened_at,
            }
        )

    return _scrub_non_finite({"positions": positions})


frontend_path = "frontend/dist" if os.path.exists("frontend/dist") else "dashboard"


def _frontend_index_response():
    index_file = os.path.join(frontend_path, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return HTMLResponse(content="<h1>Dashboard Error</h1><p>index.html not found.</p>", status_code=404)


@app.get("/")
async def get_dashboard():
    return _frontend_index_response()


@app.get("/{full_path:path}")
async def get_dashboard_asset_or_spa(full_path: str):
    if full_path.startswith(("api/", "stream", "ws/")):
        raise HTTPException(status_code=404, detail="Not found")
    candidate = os.path.join(frontend_path, full_path)
    if os.path.exists(candidate) and os.path.isfile(candidate):
        return FileResponse(candidate)
    return _frontend_index_response()
