import asyncio
import json
import logging
import os
from typing import List
from datetime import datetime, timezone
from fastapi import FastAPI, Request, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
import uvicorn
from src.models.persistence import PersistenceManager
from src.config import settings
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
