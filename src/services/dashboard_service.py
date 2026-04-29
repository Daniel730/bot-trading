import asyncio
import base64
import hashlib
import hmac
import json
import logging
import math
import os
import secrets
import socket
import time
from collections import deque
from datetime import datetime, timedelta, timezone
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
from src.services.brokerage_service import brokerage_service

logger = logging.getLogger(__name__)


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


class ConnectionManager:
    def __init__(self, max_connections: int = 50):
        self.active_connections: List[WebSocket] = []
        self.max_connections = max_connections

    async def connect(self, websocket: WebSocket):
        if len(self.active_connections) >= self.max_connections:
            logger.warning("WebSocket: Max connections reached. Rejecting client without accept.")
            await websocket.close(code=1008)
            return
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("New WebSocket client connected. Total: %s", len(self.active_connections))

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

    def create(self, actor: str = "dashboard") -> dict:
        raw = secrets.token_urlsafe(32)
        digest = self._hash(raw)
        expires_at = _utcnow() + timedelta(seconds=self.ttl_seconds)
        self._sessions[digest] = {"actor": actor, "expires_at": expires_at}
        return {"session_token": raw, "expires_at": expires_at.isoformat(), "actor": actor}

    def verify(self, session_token: Optional[str]) -> dict:
        if not session_token:
            raise HTTPException(status_code=401, detail="Dashboard login is required.")
        digest = self._hash(session_token)
        session = self._sessions.get(digest)
        if not session:
            raise HTTPException(status_code=401, detail="Invalid or expired dashboard session.")
        if session["expires_at"] <= _utcnow():
            self._sessions.pop(digest, None)
            raise HTTPException(status_code=401, detail="Dashboard session expired.")
        return session

    def revoke(self, session_token: Optional[str]) -> None:
        if session_token:
            self._sessions.pop(self._hash(session_token), None)

    def _hash(self, value: str) -> str:
        return hmac.new(_dashboard_secret().encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


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


def verify_security_token(token: str = Query(None)):
    secret = settings.DASHBOARD_TOKEN.strip().strip('"').strip("'")
    if token != secret:
        logger.warning(
            "DASHBOARD: Auth failed. Expected Len: %s, Received Len: %s",
            len(secret),
            len(token) if token else 0,
        )
        raise HTTPException(status_code=403, detail="Invalid Dashboard Token")
    return token


def verify_token(token: str = Query(None), session: str = Query(None)):
    verified_token = verify_security_token(token)
    session_manager.verify(session)
    return verified_token


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


class T212WalletSyncRequest(BaseModel):
    budget: float = Field(..., gt=0)
    skip_owned: bool = True
    skip_pending: bool = True
    delay_seconds: float = Field(default=0.5, ge=0, le=10)


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


app = FastAPI(title="Arbitrage Dashboard")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class DashboardService:
    def __init__(self):
        self.server = None
        self.persistence = PersistenceManager(settings.DB_PATH)
        self.dashboard_state = dashboard_state
        self.health_history: Deque[dict] = deque(maxlen=120)
        self.totp = TOTPManager(self.persistence)
        self.editable_config: Dict[str, dict] = {
            "APPROVAL_THRESHOLD": {"type": "float", "sensitive": False},
            "SCAN_INTERVAL_SECONDS": {"type": "int", "sensitive": False},
            "MONITOR_ENTRY_ZSCORE": {"type": "float", "sensitive": False},
            "MAX_RISK_PER_TRADE": {"type": "float", "sensitive": True},
            "MAX_DRAWDOWN": {"type": "float", "sensitive": True},
            "T212_BUDGET_USD": {"type": "float", "sensitive": False},
            "WEB3_BUDGET_USD": {"type": "float", "sensitive": False},
            "LIVE_CAPITAL_DANGER": {"type": "bool", "sensitive": True},
            "PAPER_TRADING": {"type": "bool", "sensitive": True},
            "DEV_MODE": {"type": "bool", "sensitive": True},
            "OPENAI_API_KEY": {"type": "str", "sensitive": True},
            "GEMINI_API_KEY": {"type": "str", "sensitive": True},
            "POLYGON_API_KEY": {"type": "str", "sensitive": True},
            "T212_API_KEY": {"type": "str", "sensitive": True},
            "T212_API_SECRET": {"type": "str", "sensitive": True},
            "TRADING_212_API_KEY": {"type": "str", "sensitive": True},
            "TELEGRAM_BOT_TOKEN": {"type": "str", "sensitive": True},
            "WEB3_PRIVATE_KEY": {"type": "str", "sensitive": True},
            "WEB3_RPC_URL": {"type": "str", "sensitive": True},
        }

    def attach_monitor(self, monitor):
        dashboard_state.monitor = monitor

    def _coint_t212_tickers(self) -> tuple[int, list[str]]:
        monitor = dashboard_state.monitor
        if monitor is None:
            raise HTTPException(status_code=409, detail="The bot monitor is not attached yet. Start the bot before syncing T212.")

        tickers: list[str] = []
        coint_pairs = 0
        for pair in monitor.active_pairs:
            if pair.get("is_cointegrated") is not True:
                continue
            ticker_a = str(pair.get("ticker_a") or "").strip().upper()
            ticker_b = str(pair.get("ticker_b") or "").strip().upper()
            if not ticker_a or not ticker_b:
                continue
            if "-USD" in ticker_a or "-USD" in ticker_b:
                continue
            coint_pairs += 1
            for ticker in (ticker_a, ticker_b):
                if brokerage_service.get_venue(ticker) == "T212" and ticker not in tickers:
                    tickers.append(ticker)

        return coint_pairs, tickers

    async def sync_t212_wallet_for_coint(self, request: T212WalletSyncRequest) -> dict:
        if not settings.has_t212_key:
            raise HTTPException(status_code=400, detail="Trading 212 API key is not configured.")

        coint_pair_count, candidate_tickers = self._coint_t212_tickers()
        if not candidate_tickers:
            raise HTTPException(status_code=400, detail="No COINT equity tickers are active for T212.")

        try:
            positions = await asyncio.to_thread(brokerage_service.get_positions)
            pending_orders = await brokerage_service.get_pending_orders()
            account_cash = await asyncio.to_thread(brokerage_service.get_account_cash)
            pending_value = float(await brokerage_service.get_pending_orders_value())
        except Exception as exc:
            logger.error("DASHBOARD: T212 wallet sync preflight failed: %s", exc)
            raise HTTPException(status_code=502, detail=f"Could not read Trading 212 wallet state: {exc}") from exc

        owned_tickers: list[str] = []
        for position in positions:
            ticker = str(position.get("ticker") or "").upper()
            quantity = _safe_float(position.get("quantity"))
            if ticker and quantity is not None and quantity > 0:
                owned_tickers.append(ticker)

        pending_buy_tickers: list[str] = []
        for order in pending_orders:
            ticker = str(order.get("ticker") or "").upper()
            quantity = _safe_float(order.get("quantity"))
            if ticker and quantity is not None and quantity > 0:
                pending_buy_tickers.append(ticker)

        target_tickers: list[str] = []
        skipped: list[dict] = []
        for ticker in candidate_tickers:
            t212_ticker = brokerage_service._format_ticker(ticker)
            if request.skip_owned and t212_ticker in owned_tickers:
                skipped.append({"ticker": ticker, "reason": "owned"})
                continue
            if request.skip_pending and t212_ticker in pending_buy_tickers:
                skipped.append({"ticker": ticker, "reason": "pending_buy"})
                continue
            target_tickers.append(ticker)

        if not target_tickers:
            result = {
                "status": "ok",
                "mode": "demo" if settings.is_t212_demo else "live",
                "message": "All COINT T212 tickers are already owned or pending.",
                "coint_pairs": coint_pair_count,
                "candidate_tickers": candidate_tickers,
                "target_tickers": [],
                "skipped": skipped,
                "budget": float(request.budget),
                "spendable_cash": _safe_float((account_cash or 0.0) - pending_value),
                "orders": [],
                "failures": 0,
            }
            await dashboard_state.add_message("SYSTEM", "T212 wallet sync skipped: every COINT ticker is already owned or pending.")
            return result

        from src.services.budget_service import budget_service

        raw_cash = float(account_cash or 0.0)
        spendable_cash = max(0.0, raw_cash - max(0.0, pending_value))
        effective_cash = budget_service.get_effective_cash("T212", spendable_cash)
        budget = float(request.budget)
        if budget > effective_cash + 1e-9:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Requested wallet sync budget {budget:.2f} exceeds spendable T212 cash/budget "
                    f"{effective_cash:.2f}."
                ),
            )

        cents = int(round(budget * 100))
        min_order_cents = max(1, int(round(settings.MIN_TRADE_VALUE * 100)))
        if cents < len(target_tickers) * min_order_cents:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Budget {budget:.2f} is too small for {len(target_tickers)} tickers; "
                    f"each needs at least {settings.MIN_TRADE_VALUE:.2f}."
                ),
            )

        base_cents = cents // len(target_tickers)
        extra_cents = cents % len(target_tickers)
        plan = [
            {
                "ticker": ticker,
                "amount": (base_cents + (1 if idx < extra_cents else 0)) / 100,
            }
            for idx, ticker in enumerate(target_tickers)
        ]

        orders: list[dict] = []
        failures = 0
        for idx, item in enumerate(plan):
            ticker = item["ticker"]
            amount = item["amount"]
            try:
                response = await brokerage_service.place_value_order(
                    ticker,
                    amount,
                    "BUY",
                    client_order_id=f"dashboard-wallet-sync-{int(time.time())}-{idx}",
                )
            except Exception as exc:
                failures += 1
                orders.append({"ticker": ticker, "amount": amount, "status": "error", "message": str(exc)})
            else:
                status = "error" if response.get("status") == "error" else "ok"
                if status == "error":
                    failures += 1
                orders.append(
                    {
                        "ticker": ticker,
                        "amount": amount,
                        "status": status,
                        "order_id": response.get("order_id") or response.get("orderId") or response.get("id"),
                        "message": response.get("message"),
                    }
                )

            if idx < len(plan) - 1 and request.delay_seconds > 0:
                await asyncio.sleep(request.delay_seconds)

        await dashboard_state.add_message(
            "SYSTEM",
            f"T212 wallet sync submitted {len(plan) - failures}/{len(plan)} BUY orders for COINT tickers.",
            metadata={"type": "t212_wallet_sync", "failures": failures, "tickers": target_tickers},
        )

        return {
            "status": "ok" if failures == 0 else "partial",
            "mode": "demo" if settings.is_t212_demo else "live",
            "message": f"Submitted {len(plan) - failures}/{len(plan)} BUY orders.",
            "coint_pairs": coint_pair_count,
            "candidate_tickers": candidate_tickers,
            "target_tickers": target_tickers,
            "skipped": skipped,
            "budget": budget,
            "spendable_cash": _safe_float(spendable_cash),
            "effective_cash": _safe_float(effective_cash),
            "per_ticker_min": min(item["amount"] for item in plan),
            "per_ticker_max": max(item["amount"] for item in plan),
            "orders": orders,
            "failures": failures,
        }

    def _coerce_config_value(self, key: str, value: Any) -> Any:
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
                return str(value)
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
        if self.editable_config.get(key, {}).get("sensitive"):
            return self._mask_sensitive_value(value)
        return value

    def get_dashboard_config(self) -> dict:
        items = []
        for key, spec in self.editable_config.items():
            raw_value = getattr(settings, key)
            items.append(
                {
                    "key": key,
                    "value": self._mask_sensitive_value(raw_value) if spec["sensitive"] else raw_value,
                    "type": spec["type"],
                    "sensitive": spec["sensitive"],
                }
            )
        audit_log = []
        for entry in self.persistence.get_recent_config_changes(limit=25):
            key = entry.get("key")
            if self.editable_config.get(key, {}).get("sensitive"):
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
        }

    async def update_dashboard_config(self, actor: str, updates: Dict[str, Any], otp_token: Optional[str]) -> dict:
        if not updates:
            raise HTTPException(status_code=400, detail="No configuration updates provided.")

        normalized_updates: Dict[str, Any] = {}
        requires_2fa = False
        for key, value in updates.items():
            normalized_key = str(key).strip().upper()
            if self.editable_config.get(normalized_key, {}).get("sensitive") and self._is_masked_placeholder(value):
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

    async def start(self):
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
        while True:
            try:
                from src.services.budget_service import budget_service
                from src.services.persistence_service import persistence_service

                today = datetime.now().date().isoformat()

                t212_cash: Optional[float] = None
                t212_pending: float = 0.0
                if not settings.PAPER_TRADING or settings.is_t212_demo:
                    try:
                        t212_cash = await asyncio.to_thread(brokerage_service.get_account_cash)
                        t212_pending = await brokerage_service.get_pending_orders_value()
                    except Exception as exc:
                        logger.warning("DASHBOARD: Could not fetch T212 cash: %s", exc)

                t212_budget_info = budget_service.get_venue_budget_info("T212")
                t212_daily_budget = t212_budget_info["total"] if t212_budget_info["total"] > 0 else ((t212_cash * 0.25) if t212_cash is not None else None)
                t212_daily_used = t212_budget_info["used"]
                t212_daily_pnl = await persistence_service.get_daily_pnl_for_date(today, venue="T212")
                t212_total_pnl = await persistence_service.get_total_pnl(venue="T212")
                t212_invested = await persistence_service.get_current_investment(venue="T212")

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

                global_cash = sum(c for c in [t212_cash, web3_cash] if c is not None) or None
                global_pending = t212_pending
                global_spendable = (global_cash - global_pending) if global_cash is not None else None
                global_daily_budget = sum(b for b in [t212_daily_budget, web3_daily_budget] if b is not None) or None
                global_daily_used = t212_daily_used + web3_daily_used
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
                    "t212": {
                        "available_cash": t212_cash,
                        "pending_orders_value": t212_pending,
                        "spendable_cash": (t212_cash - t212_pending) if t212_cash is not None else None,
                        "daily_budget": t212_daily_budget,
                        "daily_used": t212_daily_used,
                        "daily_usage_pct": ((t212_daily_used / t212_daily_budget * 100) if t212_daily_budget and t212_daily_budget > 0 else None),
                        "daily_profit": t212_daily_pnl,
                        "total_revenue": t212_total_pnl,
                        "total_invested": t212_invested,
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
    session_manager.revoke(session)
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
    try:
        verify_token(token, session)
    except HTTPException:
        await websocket.close(code=4003)
        return

    await connection_manager.connect(websocket)
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
    verify_token(token, session)
    if dashboard_service.totp.verify_setup(request.token):
        await dashboard_state.add_message("SYSTEM", "Two-factor authentication enabled for dashboard config changes.")
        return {"status": "ok", "two_factor": dashboard_service.totp.public_status()}
    if dashboard_service.totp.verify_token_or_backup(request.token):
        return {"status": "ok", "verified": True, "two_factor": dashboard_service.totp.public_status()}
    raise HTTPException(status_code=403, detail="Invalid 2FA token.")


@app.get("/api/pairs")
async def list_pairs(token: str = Query(None), session: str = Query(None)):
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


@app.post("/api/t212/wallet/sync")
async def sync_t212_wallet(request: T212WalletSyncRequest, token: str = Query(None), session: str = Query(None)):
    verify_token(token, session)
    return await dashboard_service.sync_t212_wallet_for_coint(request)


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
            latest_prices = await data_service.get_latest_price(list(set(all_tickers)))
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
