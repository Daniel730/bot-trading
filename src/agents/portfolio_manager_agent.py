import logging
import asyncio
import requests
import pandas as pd
import numpy as np
from scipy.optimize import minimize
from typing import Dict, List, Tuple
from datetime import datetime, timedelta

from src.config import settings
from src.services.persistence_service import persistence_service, TradeLedger, OrderStatus, OptimizedAllocation, UniverseCandidate
from src.services.data_service import DataService
from src.services.arbitrage_service import ArbitrageService
from src.services.agent_log_service import agent_trace
from src.agents.macro_economic_agent import macro_economic_agent

logger = logging.getLogger(__name__)

class PortfolioManagerAgent:
    def __init__(self):
        self.data_service = DataService()
        self.arbitrage_service = ArbitrageService()
        self._sp500_cache: pd.DataFrame = None
        self._last_cache_update: datetime = None

    @agent_trace("PortfolioManagerAgent.get_sp500_universe")
    async def get_sp500_universe(self) -> pd.DataFrame:
        """Fetches and caches the S&P 500 constituents and sectors from Wikipedia."""
        if self._sp500_cache is not None and (datetime.now() - self._last_cache_update) < timedelta(days=7):
            return self._sp500_cache

        try:
            url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            
            response = await asyncio.to_thread(requests.get, url, headers=headers)
            response.raise_for_status()
            
            tables = await asyncio.to_thread(pd.read_html, response.text)
            
            df = None
            for table in tables:
                if len(table) > 400: # The constituents table has 503 rows
                    df = table
                    break
            
            if df is None:
                df = tables[0]

            # Identify columns by keyword search
            ticker_col = next((c for c in df.columns if 'symbol' in str(c).lower() or 'ticker' in str(c).lower()), None)
            sector_col = next((c for c in df.columns if 'sector' in str(c).lower() or 'industry' in str(c).lower()), None)
            company_col = next((c for c in df.columns if 'security' in str(c).lower() or 'company' in str(c).lower()), None)

            if not ticker_col or not sector_col:
                print(f"DEBUG SCRAPER: Failed to identify columns in table (len {len(df)}). Found: {df.columns.tolist()}")
                return pd.DataFrame()

            df = df.rename(columns={ticker_col: 'Ticker', sector_col: 'Sector', company_col: 'Company'})
            df = df[['Ticker', 'Company', 'Sector']]
            
            self._sp500_cache = df
            self._last_cache_update = datetime.now()
            print(f"DEBUG SCRAPER: S&P 500 Universe Cached. {len(df)} tickers.")
            return df
        except Exception as e:
            # Avoid UnicodeEncodeError on Windows console by not printing full character junk
            logger.error(f"S&P 500 Scraper Exception: {type(e).__name__}")
            return pd.DataFrame()

    @agent_trace("PortfolioManagerAgent.calculate_sortino_ratio")
    def calculate_sortino_ratio(self, weights: np.array, returns: pd.DataFrame, risk_free_rate: float = 0.045) -> float:
        """
        Calculates the annualized Sortino Ratio.
        Formula: (Expected Return - RFR) / Downside Deviation
        """
        daily_rfr = (1 + risk_free_rate) ** (1/252) - 1
        portfolio_returns = returns.dot(weights)
        
        expected_return = portfolio_returns.mean() * 252
        
        # Downside deviation only considers returns below the target (RFR)
        downside_returns = portfolio_returns[portfolio_returns < daily_rfr] - daily_rfr
        if len(downside_returns) == 0:
            # If no downside, Sortino is theoretically infinite. 
            # We return a high representative value or just the annualized return.
            return expected_return * 100 
            
        downside_deviation = np.sqrt((downside_returns**2).sum() / len(portfolio_returns)) * np.sqrt(252)
        
        if downside_deviation == 0:
            return 0.0
            
        return (expected_return - risk_free_rate) / downside_deviation

    @agent_trace("PortfolioManagerAgent.optimize_portfolio")
    async def optimize_portfolio(self, tickers: List[str]) -> Dict[str, float]:
        """
        Uses SLSQP to maximize the Sortino Ratio.
        Constraints: Weights sum to 1.0, Max 20% per ticker.
        """
        if not tickers:
            return {}

        # 1. Fetch historical data (1 year)
        df = await asyncio.to_thread(self.data_service.get_historical_data, tickers, "1y", "1d")
        returns = df.pct_change().dropna()
        
        if returns.empty:
            logger.warning(f"No returns data for optimization: {tickers}")
            return {t: 1.0/len(tickers) for t in tickers}

        num_assets = len(tickers)
        initial_weights = np.array([1.0 / num_assets] * num_assets)
        
        # Constraints: sum(w) = 1
        constraints = ({'type': 'eq', 'fun': lambda w: np.sum(w) - 1})
        # Bounds: 0.0 to 0.20 (As requested: Max 20%)
        bounds = tuple((0, 0.20) for _ in range(num_assets))

        # Objective: Maximize Sortino (Minimize Negative Sortino)
        def objective(w):
            return -self.calculate_sortino_ratio(w, returns)

        result = minimize(objective, initial_weights, method='SLSQP', bounds=bounds, constraints=constraints)
        
        if not result.success:
            logger.error(f"Portfolio Optimization failed: {result.message}")
            return {t: 1.0/len(tickers) for t in tickers}

        optimized_weights = {tickers[i]: float(result.x[i]) for i in range(num_assets)}
        
        # Save to DB
        for ticker, weight in optimized_weights.items():
            await persistence_service.update_optimized_allocation(ticker, weight)
            
        return optimized_weights

    @agent_trace("PortfolioManagerAgent.scan_sector_universe")
    async def scan_sector_universe(self, sector: str):
        """
        Scans a specific S&P 500 sector for cointegrated pairs.
        Uses bulk search to avoid re-analyzing existing candidates and bulk inserts for speed.
        """
        universe = await self.get_sp500_universe()
        
        # Hardcoded fallback for key sectors if scraper fails
        fallback_universe = {
            'Financials': ['JPM', 'BAC', 'MS', 'GS', 'V', 'MA', 'AXP', 'C', 'BLK', 'WFC'],
            'Information Technology': ['AAPL', 'MSFT', 'NVDA', 'AVGO', 'CSCO', 'ACN', 'ORCL', 'INTC', 'CRM', 'AMD'],
            'Consumer Staples': ['KO', 'PEP', 'PG', 'WMT', 'COST', 'PM', 'EL', 'CL', 'MO', 'KMB'],
            'Health Care': ['JNJ', 'UNH', 'LLY', 'MRK', 'ABBV', 'PFE', 'TMO', 'AMGN', 'ISRG', 'GILD']
        }

        if universe.empty or 'Sector' not in universe.columns:
            logger.warning(f"Scraper failed. Using hardcoded fallback for sector {sector}.")
            sector_tickers = fallback_universe.get(sector, [])
        else:
            sector_tickers = universe[universe['Sector'] == sector]['Ticker'].tolist()
        
        if not sector_tickers:
            logger.error(f"No tickers found for sector {sector}.")
            return

        logger.info(f"Scanning sector {sector} with {len(sector_tickers)} tickers...")
        
        # Bulk fetch existing candidate IDs to avoid redundant analysis
        existing_ids = await persistence_service.get_existing_candidate_ids(sector)
        new_candidates = []

        # This is a placeholder for a more complex chunked scanning logic
        # In a real environment, this would run as a background task
        # Mocking 10 pairs for now
        for i in range(min(10, len(sector_tickers)-1)):
            t_a, t_b = sector_tickers[i], sector_tickers[i+1]
            pair_id = f"{t_a}_{t_b}"
            
            if pair_id in existing_ids:
                logger.info(f"Skipping existing candidate: {pair_id}")
                continue

            try:
                df = await asyncio.to_thread(self.data_service.get_historical_data, [t_a, t_b], "1y", "1d")
                is_coint, p_val, hedge = self.arbitrage_service.check_cointegration(df[t_a], df[t_b])
                
                if is_coint:
                    # Calculate estimated Sortino for this pair spread
                    spread = df[t_a] - (hedge * df[t_b])
                    spread_returns = spread.pct_change().dropna()
                    pair_sortino = self.calculate_sortino_ratio(np.array([1.0]), pd.DataFrame(spread_returns)) # Simplified for single spread
                    
                    # Add to bulk list
                    new_candidates.append(UniverseCandidate(
                        pair_id=pair_id,
                        sector=sector,
                        p_value=p_val,
                        correlation=df[t_a].corr(df[t_b]),
                        expected_return=spread_returns.mean() * 252,
                        volatility=spread_returns.std() * np.sqrt(252),
                        sortino=pair_sortino
                    ))
                    logger.info(f"Found new candidate: {pair_id} (Sortino: {pair_sortino:.2f})")
            except Exception as e:
                logger.error(f"Error analyzing {pair_id}: {e}")
                continue

        if new_candidates:
            await persistence_service.save_universe_candidates(new_candidates)
            logger.info(f"Successfully bulk inserted {len(new_candidates)} new candidates for {sector}.")

    async def get_optimization_advice(self, new_ticker: str) -> Dict:
        """
        Determines if adding a new ticker improves the portfolio's Sortino Ratio.
        Returns: {"is_recommended": bool, "improvement": float, "target_weight": float}
        """
        current_tickers = await persistence_service.get_active_portfolio_tickers()
        if not current_tickers:
            return {"is_recommended": True, "improvement": 0.0, "target_weight": 0.20}

        all_tickers = list(set(current_tickers + [new_ticker]))
        
        # Fetch data for all
        df = await asyncio.to_thread(self.data_service.get_historical_data, all_tickers, "1y", "1d")
        returns = df.pct_change().dropna()
        
        # Calculate current Sortino (equal weight for simplicity or fetch stored)
        curr_w = np.array([1.0/len(current_tickers)] * len(current_tickers))
        curr_sortino = self.calculate_sortino_ratio(curr_w, returns[current_tickers])
        
        # Calculate optimized Sortino with NEW ticker
        optimized_results = await self.optimize_portfolio(all_tickers)
        opt_w = np.array([optimized_results[t] for t in all_tickers])
        new_sortino = self.calculate_sortino_ratio(opt_w, returns)
        
        improvement = new_sortino - curr_sortino
        
        return {
            "is_recommended": improvement > 0,
            "improvement": improvement,
            "target_weight": optimized_results.get(new_ticker, 0.0),
            "optimized_portfolio": optimized_results
        }

    @agent_trace("PortfolioManagerAgent.run_narrative_scan")
    async def run_narrative_scan(self, sector: str, beacon_ticker: str):
        """
        Executes a sector scan only if the Beacon Asset (Leader) is in a healthy regime.
        """
        regime = await macro_economic_agent.get_ticker_regime(beacon_ticker)
        
        if regime in ["BEARISH", "EXTREME_VOLATILITY"]:
            logger.warning(f"NARRATIVE VETO: Sector {sector} scan cancelled. Beacon {beacon_ticker} is {regime}.")
            return {"status": "VETOED", "reason": f"Beacon {beacon_ticker} in {regime} regime"}

        logger.info(f"NARRATIVE APPROVED: Sector {sector} Leader {beacon_ticker} is BULLISH. Scanning followers...")
        await self.scan_sector_universe(sector)
        return {"status": "COMPLETED", "sector": sector}

portfolio_manager_agent = PortfolioManagerAgent()
