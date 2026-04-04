import asyncio
import json
import logging
import os
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
import uvicorn
from src.models.persistence import PersistenceManager
from src.config import settings

logger = logging.getLogger(__name__)

class DashboardState:
    def __init__(self):
        self.stage = "Booting up..."
        self.details = "Initializing core components and services."
        self.portfolio_metrics = {
            "total_revenue": 0.0,
            "total_invested": 0.0,
            "daily_profit": 0.0,
            "available_cash": 0.0,
            "daily_allocation": 0.0,
            "daily_usage_pct": 0.0
        }
        self.active_signals = [] # List of {ticker_a, ticker_b, z_score, status}
        self.terminal_messages = [] # List of {type, text, timestamp, metadata}
        self.listeners = []
        self._lock = asyncio.Lock()

    async def add_message(self, msg_type: str, text: str, metadata: dict = None):
        """Adds a message to the terminal and notifies listeners."""
        async with self._lock:
            msg = {
                "id": str(os.urandom(4).hex()),
                "type": msg_type,
                "text": text,
                "timestamp": datetime.now().isoformat(),
                "metadata": metadata or {}
            }
            self.terminal_messages.append(msg)
            if len(self.terminal_messages) > 50:
                self.terminal_messages.pop(0)
            
            await self._broadcast()

    async def _broadcast(self):
        """Helper to send current state to all SSE listeners."""
        message = json.dumps({
            "stage": self.stage, 
            "details": self.details,
            "metrics": self.portfolio_metrics,
            "active_signals": self.active_signals,
            "terminal_messages": self.terminal_messages,
            "timestamp": datetime.now().isoformat()
        })
        for q in self.listeners:
            await q.put(message)

    async def update(self, stage: str, details: str, pnl: float = None, signals: int = None, active_signals: list = None):
        async with self._lock:
            self.stage = stage
            self.details = details
            if active_signals is not None:
                self.active_signals = active_signals
            
            logger.info(f"DASHBOARD: {stage} - {details[:50]}...")
            await self._broadcast()

    async def update_metrics(self, metrics: dict):
        async with self._lock:
            self.portfolio_metrics.update(metrics)
            await self._broadcast()

# Global state
dashboard_state = DashboardState()

# SIMPLE AUTH (NFR-002)
def verify_token(token: str = Query(None)):
    secret = os.getenv("DASHBOARD_TOKEN", "arbi-elite-2026")
    if token != secret:
        raise HTTPException(status_code=403, detail="Invalid Dashboard Token")
    return token

from pydantic import BaseModel
from typing import Optional

class CommandRequest(BaseModel):
    command: str
    metadata: Optional[dict] = None

app = FastAPI(title="Arbitrage Dashboard")

# Add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="dashboard"), name="static")

@app.get("/")
async def get_dashboard(token: str = Query(None)):
    verify_token(token)
    paths = [
        "/app/dashboard/index.html",
        os.path.join(os.getcwd(), "dashboard", "index.html"),
        "dashboard/index.html"
    ]
    for p in paths:
        if os.path.exists(p):
            return FileResponse(p)
    
    return HTMLResponse(content=f"<h1>Dashboard Error</h1><p>index.html not found. Current Dir: {os.getcwd()}</p>", status_code=404)

@app.get("/stream")
async def message_stream(request: Request, token: str = Query(None)):
    """SSE endpoint to stream bot state changes."""
    verify_token(token)
    q = asyncio.Queue()
    
    async with dashboard_state._lock:
        dashboard_state.listeners.append(q)
        # Send initial state immediately
        initial_data = json.dumps({
            "stage": dashboard_state.stage, 
            "details": dashboard_state.details,
            "metrics": dashboard_state.portfolio_metrics,
            "active_signals": dashboard_state.active_signals,
            "terminal_messages": dashboard_state.terminal_messages,
            "timestamp": datetime.now().isoformat()
        })
        await q.put(initial_data)

    async def event_generator():
        try:
            while True:
                # If client closes connection, stop sending events
                if await request.is_disconnected():
                    break
                
                # Wait for new message
                data = await q.get()
                yield {
                    "event": "message",
                    "data": data
                }
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

@app.post("/api/terminal/command")
async def terminal_command(request: CommandRequest, token: str = Query(None)):
    """Receives a command from the dashboard and forwards to NotificationService."""
    verify_token(token)
    from src.services.notification_service import notification_service
    result = await notification_service.handle_dashboard_command(request.command, request.metadata)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result

class DashboardService:
    def __init__(self):
        self.server = None
        self.persistence = PersistenceManager(settings.DB_PATH)

    async def start(self):
        """Starts the uvicorn server and background tasks."""
        try:
            config = uvicorn.Config(app, host="0.0.0.0", port=8080, log_level="info")
            self.server = uvicorn.Server(config)
            # Use create_task but don't block
            asyncio.create_task(self.server.serve())
            
            # Start background polling
            asyncio.create_task(self._poll_metrics())
            
            logger.info("!!! DASHBOARD SERVER & POLLING STARTED ON PORT 8080 !!!")
        except Exception as e:
            logger.error(f"DASHBOARD STARTUP ERROR: {e}")

    async def _poll_metrics(self):
        """Periodically polls SQLite for portfolio metrics."""
        while True:
            try:
                is_shadow = settings.TRADING_212_MODE.lower() == "demo" or settings.DEV_MODE
                
                # We need to import BrokerageService here to avoid circular imports if any
                from src.services.brokerage_service import BrokerageService
                brokerage = BrokerageService()
                total_cash = brokerage.get_account_cash()
                daily_allocation = total_cash * 0.25 # Principle I: 25% Daily Limit
                daily_invested = self.persistence.get_daily_invested(datetime.now().date().isoformat(), is_shadow=is_shadow)
                
                metrics = {
                    "total_revenue": self.persistence.get_total_revenue(is_shadow=is_shadow),
                    "total_invested": self.persistence.get_current_investment(is_shadow=is_shadow),
                    "daily_profit": self.persistence.get_daily_pnl(datetime.now().date().isoformat(), is_shadow=is_shadow),
                    "available_cash": total_cash,
                    "daily_budget": daily_allocation,
                    "daily_usage_pct": (daily_invested / daily_allocation * 100) if daily_allocation > 0 else 0
                }
                
                await dashboard_state.update_metrics(metrics)
            except Exception as e:
                logger.error(f"DASHBOARD POLLING ERROR: {e}")
            
            await asyncio.sleep(10)

    async def update_state(self, stage: str, details: str, pnl: float = None, signals: int = None, active_signals: list = None):
        """Updates the UI state."""
        await dashboard_state.update(stage, details, pnl, signals, active_signals)

dashboard_service = DashboardService()
