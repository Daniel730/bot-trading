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
        self.global_accuracy = 0.5
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

# ─── PAIRS API ──────────────────────────────────────────────────────────────

class PairConfig(BaseModel):
    ticker_a: str
    ticker_b: str

class PairsUpdateRequest(BaseModel):
    pairs: List[PairConfig]
    crypto_pairs: Optional[List[PairConfig]] = None
    apply_now: bool = True  # If True, hot-reload the monitor's universe.


def _serialize_pair(active_pair: dict) -> dict:
    """Convert monitor.active_pairs entry into a JSON-friendly payload."""
    return {
        "id": active_pair.get("id"),
        "ticker_a": active_pair.get("ticker_a"),
        "ticker_b": active_pair.get("ticker_b"),
        "hedge_ratio": active_pair.get("hedge_ratio"),
        "mean": active_pair.get("mean"),
        "std": active_pair.get("std"),
        "is_cointegrated": active_pair.get("is_cointegrated"),
        "sector": settings.PAIR_SECTORS.get(
            active_pair.get("id", ""),
            settings.PAIR_SECTORS.get(
                f"{active_pair.get('ticker_b','')}_{active_pair.get('ticker_a','')}",
                "Unassigned",
            ),
        ),
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
                    z_score_map[pair_id] = float(state["z_score"])
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

    return {
        "active_pairs": active_serialized,
        "configured_pairs": settings.ARBITRAGE_PAIRS,
        "crypto_test_pairs": settings.CRYPTO_TEST_PAIRS,
        "dev_mode": settings.DEV_MODE,
    }


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
            "qty_a": float(leg_a["quantity"]),
            "qty_b": float(leg_b["quantity"]),
            "entry_a": float(leg_a["price"]),
            "entry_b": float(leg_b["price"]),
            "current_a": latest_prices.get(leg_a["ticker"]),
            "current_b": latest_prices.get(leg_b["ticker"]),
            "cost_basis": float(sig.get("total_cost_basis", 0.0)),
            "current_value": current_value,
            "pnl": pnl,
            "opened_at": opened_at,
        })

    return {"positions": positions}


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
        while True:
            try:
                is_shadow = settings.TRADING_212_MODE.lower() == "demo" or settings.DEV_MODE
                
                total_cash = None
                pending_value = None
                
                # Fetch cash if not paper trading OR if we are in DEMO mode with a valid key
                if not settings.PAPER_TRADING or settings.is_t212_demo:
                    try:
                        total_cash = await asyncio.to_thread(brokerage_service.get_account_cash)
                        pending_value = await brokerage_service.get_pending_orders_value()
                        
                        # US-032: Remove hardcoded fallback. If API is down, send None to trigger 'ERR' in UI.
                        if total_cash == 0 and settings.is_t212_demo and not settings.PAPER_TRADING:
                            # Only if key is actually valid but balance is 0? 
                            # If it's 401, brokerage_service usually returns 0.0 on catching except.
                            # We'll trust the None fallback below.
                            pass
                    except Exception as e:
                        logger.warning(f"DASHBOARD: Could not fetch brokerage cash: {e}")
                
                spendable_cash = (total_cash - pending_value) if total_cash is not None and pending_value is not None else None
                daily_allocation = (total_cash * 0.25) if total_cash is not None else None
                daily_invested = self.persistence.get_daily_invested(datetime.now().date().isoformat(), is_shadow=is_shadow)
                
                metrics = {
                    "total_revenue": self.persistence.get_total_revenue(is_shadow=is_shadow),
                    "total_invested": self.persistence.get_current_investment(is_shadow=is_shadow),
                    "daily_profit": self.persistence.get_daily_pnl(datetime.now().date().isoformat(), is_shadow=is_shadow),
                    "available_cash": total_cash,
                    "pending_orders_value": pending_value,
                    "spendable_cash": spendable_cash,
                    "daily_budget": daily_allocation,
                    "daily_usage_pct": (daily_invested / daily_allocation * 100) if daily_allocation and daily_allocation > 0 else None
                }
                
                # Fetch Intelligence Data
                from src.services.persistence_service import persistence_service
                regime = await persistence_service.get_latest_market_regime()
                accuracy_str = await persistence_service.get_system_state("global_strategy_accuracy", "0.5")
                
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
        """Proxy to dashboard_init_state and broadcast."""
        await dashboard_state.update_metrics(metrics)

    async def update(self, stage: str, details: str, pnl: float = None, signals: int = None, active_signals: list = None):
        """Proxy for high-level status updates."""
        await dashboard_state.update(stage, details, pnl, signals, active_signals)

    async def update_state(self, stage: str, details: str, pnl: float = None, signals: int = None, active_signals: list = None):
        await dashboard_state.update(stage, details, pnl, signals, active_signals)

dashboard_service = DashboardService()
