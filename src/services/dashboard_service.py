import asyncio
import json
import logging
import os
from typing import List, Optional
from datetime import datetime, timezone
from fastapi import FastAPI, Request, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
import uvicorn
from src.models.persistence import PersistenceManager
from src.config import settings, save_pairs_override
from src.services.brokerage_service import brokerage_service

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self, max_connections: int = 50):
        self.active_connections: List[WebSocket] = []
        self.max_connections = max_connections

    async def connect(self, websocket: WebSocket):
        if len(self.active_connections) >= self.max_connections:
            # L-12: Close without accept() — avoids allocating a full WebSocket session per rejected attacker
            # Starlette will send a TCP RST rather than completing the HTTP upgrade handshake.
            logger.warning("WebSocket: Max connections reached. Rejecting client without accept.")
            await websocket.close(code=1008)  # 1008 Policy Violation
            return

        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"New WebSocket client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: str):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Error sending to WebSocket client: {e}")
                disconnected.append(connection)
        
        for conn in disconnected:
            self.disconnect(conn)

connection_manager = ConnectionManager()

class DashboardState:
    def __init__(self):
        self.stage = "Booting up..."
        self.details = "Initializing core components and services."
        self.bot_start_time = datetime.now(timezone.utc).isoformat()
        self.portfolio_metrics = {
            "total_revenue": None,
            "total_invested": None,
            "daily_profit": None,
            "available_cash": None,
            "daily_allocation": None,
            "daily_usage_pct": None
        }
        self.market_regime = {"regime": "STABLE", "confidence": 1.0}
        self.global_accuracy = settings.GLOBAL_STRATEGY_ACCURACY_DEFAULT
        self.active_signals = []
        self.terminal_messages = []
        self.listeners = []
        self._lock = asyncio.Lock()
        # Reference to ArbitrageMonitor instance, attached on startup so the
        # dashboard endpoints can inspect/modify the live pair universe.
        self.monitor = None

    def runtime_info(self) -> dict:
        """Bot mode + uptime info, broadcast to the UI alongside metrics."""
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
        }

    async def add_message(self, msg_type: str, text: str, metadata: dict = None):
        async with self._lock:
            msg = {
                "id": str(os.urandom(4).hex()),
                "type": msg_type,
                "text": text,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metadata": metadata or {}
            }
            self.terminal_messages.append(msg)
            if len(self.terminal_messages) > 50:
                self.terminal_messages.pop(0)
            await self._broadcast()

    async def _broadcast(self):
        message = json.dumps({
            "stage": self.stage,
            "details": self.details,
            "bot_start_time": self.bot_start_time,
            "runtime": self.runtime_info(),
            "metrics": self.portfolio_metrics,
            "market_regime": self.market_regime,
            "global_accuracy": self.global_accuracy,
            "active_signals": self.active_signals,
            "terminal_messages": self.terminal_messages,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        for q in self.listeners:
            await q.put(message)

    async def update(self, stage: str, details: str, pnl: float = None, signals: int = None, active_signals: list = None):
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

def verify_token(token: str = Query(None)):
    secret = settings.DASHBOARD_TOKEN.strip().strip('"').strip("'")
    
    if token != secret:
        logger.warning(f"DASHBOARD: Auth failed. Expected Len: {len(secret)}, Received Len: {len(token) if token else 0}")
        raise HTTPException(status_code=403, detail="Invalid Dashboard Token")
    return token

from pydantic import BaseModel
from typing import Optional

class CommandRequest(BaseModel):
    command: str
    metadata: Optional[dict] = None

app = FastAPI(title="Arbitrage Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# API ROUTES (Defined first)

@app.get("/stream")
async def message_stream(request: Request, token: str = Query(None)):
    verify_token(token)
    q = asyncio.Queue()
    async with dashboard_state._lock:
        dashboard_state.listeners.append(q)
        initial_data = json.dumps({
            "stage": dashboard_state.stage,
            "details": dashboard_state.details,
            "bot_start_time": dashboard_state.bot_start_time,
            "runtime": dashboard_state.runtime_info(),
            "metrics": dashboard_state.portfolio_metrics,
            "market_regime": dashboard_state.market_regime,
            "global_accuracy": dashboard_state.global_accuracy,
            "active_signals": dashboard_state.active_signals,
            "terminal_messages": dashboard_state.terminal_messages,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        await q.put(initial_data)

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
async def websocket_endpoint(websocket: WebSocket, token: str = Query(None)):
    try:
        verify_token(token)
    except HTTPException:
        await websocket.close(code=4003) # Forbidden
        return

    await connection_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, though we mostly broadcast from server -> client
            data = await websocket.receive_text()
            # Handle incoming client messages if needed (e.g. ping)
    except WebSocketDisconnect:
        connection_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        connection_manager.disconnect(websocket)

@app.post("/api/terminal/command")
async def terminal_command(request: CommandRequest, token: str = Query(None)):
    verify_token(token)
    from src.services.notification_service import notification_service
    result = await notification_service.handle_dashboard_command(request.command, request.metadata)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result

# ─── SETTINGS API ───────────────────────────────────────────────────────────

class SettingsUpdateRequest(BaseModel):
    approval_threshold: float

@app.get("/api/settings")
async def get_settings(token: str = Query(None)):
    verify_token(token)
    return {"approval_threshold": settings.APPROVAL_THRESHOLD}

@app.post("/api/settings")
async def update_settings(request: SettingsUpdateRequest, token: str = Query(None)):
    verify_token(token)
    settings.APPROVAL_THRESHOLD = request.approval_threshold
    from src.config import save_settings_override
    save_settings_override({"APPROVAL_THRESHOLD": request.approval_threshold})
    await dashboard_state.add_message("SYSTEM", f"Auto-trade threshold updated to {request.approval_threshold} EUR")
    return {"status": "ok", "approval_threshold": settings.APPROVAL_THRESHOLD}

# ─── PAIRS API ──────────────────────────────────────────────────────────────

class PairConfig(BaseModel):
    ticker_a: str
    ticker_b: str

class PairsUpdateRequest(BaseModel):
    pairs: List[PairConfig]
    crypto_pairs: Optional[List[PairConfig]] = None
    apply_now: bool = True  # If True, hot-reload the monitor's universe.


def _safe_float(val) -> Optional[float]:
    """Convert NaN/inf/None to None so json.dumps doesn't blow up.
    FastAPI/starlette refuses non-finite floats per the JSON spec."""
    import math
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
    """Recursively walk a payload and replace any NaN/inf floats with None.
    Defensive net for endpoints whose data is stitched from multiple sources
    (Redis, numpy arrays, SQLAlchemy decimals) — one stray nan otherwise
    raises ValueError deep inside starlette and produces a 500."""
    import math
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: _scrub_non_finite(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_scrub_non_finite(v) for v in obj]
    return obj


def _serialize_pair(active_pair: dict) -> dict:
    """Convert monitor.active_pairs entry into a JSON-friendly payload."""
    ticker_a = active_pair.get("ticker_a", "")
    ticker_b = active_pair.get("ticker_b", "")
    is_crypto = "-USD" in ticker_a or "-USD" in ticker_b
    pair_id = active_pair.get("id", "")
    # Sector lookup: try direct id, then reversed id, then default by asset class.
    sector = settings.PAIR_SECTORS.get(
        pair_id,
        settings.PAIR_SECTORS.get(
            f"{ticker_b}_{ticker_a}",
            "Crypto" if is_crypto else "Unassigned",
        ),
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


@app.get("/api/pairs")
async def list_pairs(token: str = Query(None)):
    """Return both the live (monitor.active_pairs) and the configured pair lists,
    plus the most-recent z-score per pair from Redis (if available)."""
    verify_token(token)
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

    # Pull the latest z-score per active pair from Redis (best-effort).
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
                # Per-pair failures shouldn't poison the entire response.
                pass
    except Exception as e:
        logger.warning(f"DASHBOARD: Could not fetch z-scores from Redis: {e}")

    # Enrich active list with last_check + z_score
    for entry in active_serialized:
        pid = entry["id"]
        entry["last_cointegration_check"] = last_check_map.get(pid)
        entry["last_z_score"] = z_score_map.get(pid)

    return _scrub_non_finite({
        "active_pairs": active_serialized,
        "configured_pairs": settings.ARBITRAGE_PAIRS,
        "crypto_test_pairs": settings.CRYPTO_TEST_PAIRS,
        "dev_mode": settings.DEV_MODE,
    })


@app.post("/api/pairs")
async def update_pairs(request: PairsUpdateRequest, token: str = Query(None)):
    """Persist a new pair universe to data/pairs.json and (optionally) hot-reload
    the monitor so the changes take effect on the next scan tick."""
    verify_token(token)

    # Basic sanity: dedupe + uppercase tickers.
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

    # 1. Persist to disk so the change survives a restart.
    save_pairs_override(cleaned, crypto_cleaned)
    # 2. Mutate live settings so any code that reads settings.* sees the new list.
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
        except Exception as e:
            reload_error = str(e)
            logger.error(f"DASHBOARD: Hot-reload of pairs failed: {e}")

    await dashboard_state.add_message(
        "SYSTEM",
        f"Pair universe updated ({len(cleaned)} pairs)"
        + (" — hot-reloaded" if reloaded else " — restart required to apply"),
    )

    return {
        "status": "ok",
        "saved_pairs": len(cleaned),
        "reloaded": reloaded,
        "reload_error": reload_error,
    }


@app.get("/api/positions")
async def list_open_positions(token: str = Query(None)):
    """Return open positions with current PnL (computed against latest prices)."""
    verify_token(token)
    from src.services.persistence_service import persistence_service
    from src.services.data_service import data_service

    try:
        signals = await persistence_service.get_open_signals()
    except Exception as e:
        logger.error(f"DASHBOARD: Failed to fetch open signals: {e}")
        return {"positions": []}

    if not signals:
        return {"positions": []}

    # Collect tickers across all open legs and fetch current prices in one shot.
    all_tickers: list = []
    for sig in signals:
        for leg in sig.get("legs", []):
            all_tickers.append(leg["ticker"])
    latest_prices: dict = {}
    try:
        if all_tickers:
            latest_prices = await data_service.get_latest_price(list(set(all_tickers)))
    except Exception as e:
        logger.warning(f"DASHBOARD: Could not fetch latest prices for positions: {e}")

    positions: list = []
    for sig in signals:
        legs = sig.get("legs", [])
        if len(legs) < 2:
            continue
        leg_a, leg_b = legs[0], legs[1]
        # Best-effort PnL: sum of per-leg directional MTM.
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
        positions.append({
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
        })

    return _scrub_non_finite({"positions": positions})


# ROOT DASHBOARD ROUTE (Authenticated)

frontend_path = "frontend/dist" if os.path.exists("frontend/dist") else "dashboard"

@app.get("/")
async def get_dashboard(token: str = Query(None)):
    verify_token(token)
    # Return the index.html from the production build
    index_file = os.path.join(frontend_path, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return HTMLResponse(content="<h1>Dashboard Error</h1><p>index.html not found.</p>", status_code=404)

# STATIC ASSETS FALLBACK (Defined last)

if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path), name="ui")

class DashboardService:
    def __init__(self):
        self.server = None
        self.persistence = PersistenceManager(settings.DB_PATH)

    def attach_monitor(self, monitor):
        """Wire the running ArbitrageMonitor instance so dashboard endpoints can
        introspect monitor.active_pairs and trigger hot-reloads."""
        dashboard_state.monitor = monitor

    async def start(self):
        try:
            from src.services.telemetry_service import telemetry_service
            telemetry_service.start_broadcast_loop()
            
            config = uvicorn.Config(app, host="0.0.0.0", port=8080, log_level="info")
            self.server = uvicorn.Server(config)
            asyncio.create_task(self.server.serve())
            asyncio.create_task(self._poll_metrics())
            logger.info("!!! DASHBOARD SERVER STARTED ON PORT 8080 !!!")
        except Exception as e:
            logger.error(f"DASHBOARD STARTUP ERROR: {e}")

    async def _poll_metrics(self):
        """Independently fetches cash balances and PnL for both T212 and WEB3
        venues, computing separate and global metrics every 10 seconds."""
        while True:
            try:
                from src.services.persistence_service import persistence_service
                from src.services.budget_service import budget_service
                today = datetime.now().date().isoformat()

                # ── T212 venue ──────────────────────────────────────────────
                t212_cash: Optional[float] = None
                t212_pending: float = 0.0
                if not settings.PAPER_TRADING or settings.is_t212_demo:
                    try:
                        t212_cash = await asyncio.to_thread(brokerage_service.get_account_cash)
                        t212_pending = await brokerage_service.get_pending_orders_value()
                    except Exception as e:
                        logger.warning(f"DASHBOARD: Could not fetch T212 cash: {e}")

                t212_budget_info = budget_service.get_venue_budget_info("T212")
                t212_daily_budget = t212_budget_info["total"] if t212_budget_info["total"] > 0 else (
                    (t212_cash * 0.25) if t212_cash is not None else None
                )
                t212_daily_used = t212_budget_info["used"]

                t212_daily_pnl = await persistence_service.get_daily_pnl_for_date(today, venue="T212")
                t212_total_pnl = await persistence_service.get_total_pnl(venue="T212")
                t212_invested = await persistence_service.get_current_investment(venue="T212")

                # ── WEB3 venue ──────────────────────────────────────────────
                web3_cash: Optional[float] = None
                if settings.web3_enabled:
                    try:
                        web3_cash = await brokerage_service.get_web3_account_cash()
                    except Exception as e:
                        logger.warning(f"DASHBOARD: Could not fetch WEB3 cash: {e}")

                web3_budget_info = budget_service.get_venue_budget_info("WEB3")
                web3_daily_budget = web3_budget_info["total"] if web3_budget_info["total"] > 0 else (
                    (web3_cash * 0.25) if web3_cash is not None else None
                )
                web3_daily_used = web3_budget_info["used"]

                web3_daily_pnl = await persistence_service.get_daily_pnl_for_date(today, venue="WEB3")
                web3_total_pnl = await persistence_service.get_total_pnl(venue="WEB3")
                web3_invested = await persistence_service.get_current_investment(venue="WEB3")

                # ── Global totals (sum of both venues) ──────────────────────
                global_cash = sum(c for c in [t212_cash, web3_cash] if c is not None) or None
                global_pending = t212_pending  # WEB3 has no pending-order concept
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
                    "daily_usage_pct": (
                        (global_daily_used / global_daily_budget * 100)
                        if global_daily_budget and global_daily_budget > 0
                        else None
                    ),
                    "t212": {
                        "available_cash": t212_cash,
                        "pending_orders_value": t212_pending,
                        "spendable_cash": (t212_cash - t212_pending) if t212_cash is not None else None,
                        "daily_budget": t212_daily_budget,
                        "daily_used": t212_daily_used,
                        "daily_usage_pct": (
                            (t212_daily_used / t212_daily_budget * 100)
                            if t212_daily_budget and t212_daily_budget > 0
                            else None
                        ),
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
                        "daily_usage_pct": (
                            (web3_daily_used / web3_daily_budget * 100)
                            if web3_daily_budget and web3_daily_budget > 0
                            else None
                        ),
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
            except Exception as e:
                logger.error(f"DASHBOARD POLLING ERROR: {e}")
            await asyncio.sleep(10)

    async def update_metrics(self, metrics: dict):
        """Proxy to dashboard_state and broadcast."""
        await dashboard_state.update_metrics(metrics)

    async def update(self, stage: str, details: str, pnl: float = None, signals: int = None, active_signals: list = None):
        """Proxy for high-level status updates."""
        await dashboard_state.update(stage, details, pnl, signals, active_signals)

    async def update_state(self, stage: str, details: str, pnl: float = None, signals: int = None, active_signals: list = None):
        await dashboard_state.update(stage, details, pnl, signals, active_signals)

dashboard_service = DashboardService()
