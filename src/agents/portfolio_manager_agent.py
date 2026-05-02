import logging
import asyncio
import inspect
import requests
import io
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
    def __init__(self, db=None):
        from src.models.persistence import PersistenceManager

        self.db = db or PersistenceManager(settings.DB_PATH)
        self.data_service = DataService()
        self.arbitrage_service = ArbitrageService()
        self._sp500_cache: pd.DataFrame = None
        self._last_cache_update: datetime = None

    @agent_trace("PortfolioManagerAgent.generate_investment_thesis")
    async def generate_investment_thesis(self, ticker: str) -> str:
        ticker = ticker.upper()
        with self.db._get_connection() as conn:
            thoughts = conn.execute(
                """
                SELECT signal_id, bull, bear, news, verdict, timestamp
                FROM thought_journal
                ORDER BY timestamp DESC
                LIMIT 5
                """
            ).fetchall()
            logs = conn.execute(
                """
                SELECT signal_id, message, source, timestamp
                FROM logs
                WHERE message LIKE ? OR metadata LIKE ?
                ORDER BY timestamp DESC
                LIMIT 5
                """,
                (f"%{ticker}%", f"%{ticker}%"),
            ).fetchall()

        lines = [f"🛡️ **Investment Thesis for {ticker}**", ""]
        if logs:
            lines.append("Recent execution context:")
            for row in logs:
                signal = row["signal_id"] or "N/A"
                lines.append(f"- [{signal}] {row['source']}: {row['message']}")
            lines.append("")
        if thoughts:
            lines.append("Agent debate:")
            for row in thoughts:
                signal = row["signal_id"] or "N/A"
                if row["bull"]:
                    lines.append(f"- Bull ({signal}): {row['bull']}")
                if row["bear"]:
                    lines.append(f"- Bear ({signal}): {row['bear']}")
                if row["news"]:
                    lines.append(f"- News ({signal}): {row['news']}")
                if row["verdict"]:
                    lines.append(f"- Verdict ({signal}): {row['verdict']}")
        if len(lines) == 2:
            lines.append("No internal thesis logs found yet.")
        return "\n".join(lines)

    @agent_trace("PortfolioManagerAgent.allocate_funds")
    async def allocate_funds(self, strategy_id: str, amount: float):
        from src.services.brokerage_service import BrokerageService

        strategy = self.db.get_portfolio_strategy(strategy_id)
        brokerage = BrokerageService()
        results = []
        for asset in strategy:
            value = float(amount) * float(asset["weight"])
            result = brokerage.place_value_order(asset["ticker"], value, "BUY")
            if inspect.isawaitable(result):
                result = await result
            results.append(result)
        return results

    def get_current_horizon(self, user_id: str) -> str:
        from datetime import date

        today = date.today()
        relevant_dates = []
        for goal in self.db.get_investment_goals():
            try:
                relevant_dates.append(datetime.fromisoformat(goal["deadline"]).date())
            except Exception:
                continue
        for event in self.db.get_user_life_events(user_id):
            try:
                relevant_dates.append(datetime.fromisoformat(event["event_date"]).date())
            except Exception:
                continue
        if not relevant_dates:
            return "Long-Term"
        nearest_days = min((target - today).days for target in relevant_dates)
        return "Short-Term" if nearest_days <= 180 else "Long-Term"

    @agent_trace("PortfolioManagerAgent.get_sp500_universe")
    async def get_sp500_universe(self) -> pd.DataFrame:
        """
        Return the S&P 500 constituents with their company names and sectors, using a cached copy when available.
        
        Returns:
            pd.DataFrame: DataFrame with columns `Ticker`, `Company`, and `Sector`. The result is cached for up to 7 days; on failure or if required columns cannot be identified, returns an empty DataFrame.
        """
        if self._sp500_cache is not None and (datetime.now() - self._last_cache_update) < timedelta(days=7):
            return self._sp500_cache

        try:
            url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10)
            response.raise_for_status()
            
            # Use 'bs4' (BeautifulSoup) as it's often more robust than lxml on Windows for large HTML files.
            # We wrap this in a thread because pd.read_html is synchronous and can be slow for large pages.
            try:
                tables = await asyncio.to_thread(pd.read_html, io.StringIO(response.text), flavor='bs4')
            except Exception as inner_e:
                logger.warning(f"pd.read_html with bs4 failed: {inner_e}. Retrying with default parser.")
                tables = await asyncio.to_thread(pd.read_html, io.StringIO(response.text))
            
            if not tables:
                logger.error("S&P 500 Scraper: No tables found in the Wikipedia response.")
                return pd.DataFrame()
            
            df = None
            for table in tables:
                # The constituents table is typically the first large table found.
                if len(table) > 400: 
                    df = table
                    break
            
            if df is None:
                logger.warning("S&P 500 Scraper: Could not identify the main constituents table by row count. Falling back to the first table.")
                df = tables[0]

            # Identify columns by keyword search (Wikipedia column names change occasionally)
            ticker_col = next((c for c in df.columns if 'symbol' in str(c).lower() or 'ticker' in str(c).lower()), None)
            sector_col = next((c for c in df.columns if 'sector' in str(c).lower() or 'industry' in str(c).lower()), None)
            company_col = next((c for c in df.columns if 'security' in str(c).lower() or 'company' in str(c).lower()), None)

            if not ticker_col or not sector_col:
                logger.error(f"S&P 500 Scraper: Failed to identify Ticker or Sector columns. Columns found: {df.columns.tolist()}")
                return pd.DataFrame()

            df = df.rename(columns={ticker_col: 'Ticker', sector_col: 'Sector', company_col: 'Company'})
            
            # Normalize tickers for yfinance (e.g., BRK.B to BRK-B)
            df['Ticker'] = df['Ticker'].astype(str).str.replace('.', '-', regex=False)
            df = df[['Ticker', 'Company', 'Sector']]
            
            self._sp500_cache = df
            self._last_cache_update = datetime.now()
            logger.info(f"S&P 500 Universe Cached. {len(df)} tickers.")
            return df
        except Exception as e:
            import traceback
            # Capture specific error name to avoid massive string dumps if the exception contains the HTML
            err_name = type(e).__name__
            logger.error(f"S&P 500 Scraper Error ({err_name}): {str(e)[:500]}")
            logger.error(traceback.format_exc())
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
        df = await self.data_service.get_historical_data_async(
            tickers,
            "1y",
            "1d",
            timeout=settings.MARKET_DATA_TIMEOUT_SECONDS * 2,
        )
        if df is None or df.empty:
            logger.warning(f"No historical data for optimization: {tickers}")
            return {t: 1.0/len(tickers) for t in tickers}
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
        Scan the S&P 500 sector for cointegrated ticker pairs and persist newly discovered candidates.
        
        Fetches the sector tickers (using a cached/wrapped scraper and a hardcoded fallback when scraping fails), skips pairs already recorded, analyzes adjacent ticker pairs for cointegration and spread performance metrics, and bulk-saves any newly discovered UniverseCandidate entries. The method logs progress, warnings when falling back to hardcoded lists, and errors per-pair when analysis fails.
        
        Parameters:
            sector (str): The exact sector name to scan (e.g., "Information Technology", "Health Care").
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
                continue

            try:
                df = await self.data_service.get_historical_data_async(
                    [t_a, t_b],
                    "1y",
                    "1d",
                    timeout=settings.MARKET_DATA_TIMEOUT_SECONDS * 2,
                )
                if df is None or df.empty or t_a not in df.columns or t_b not in df.columns:
                    continue
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

    @agent_trace("PortfolioManagerAgent.scan_crypto_universe")
    async def scan_crypto_universe(self):
        """
        Scan a fixed list of top crypto tickers for cointegrated pairs and persist discovered universe candidates.
        
        For each unique pair among a predefined top-crypto list, the method:
        - Skips pairs already present in the persisted candidate IDs.
        - Loads up to one year of daily historical price data and skips the pair if data is missing or incomplete.
        - Tests for cointegration; if cointegrated, computes the spread and its daily returns, then derives annualized metrics:
          - `expected_return` (mean of spread returns annualized using 365 days),
          - `volatility` (standard deviation annualized using sqrt(365)),
          - `sortino` (using the agent's Sortino calculation on the spread returns),
          - `p_value` and `correlation`.
        - Creates and persists a UniverseCandidate for each discovered pair and logs discoveries.
        
        Pairs with missing data or pairs that raise exceptions during processing are skipped silently; newly discovered candidates are saved in bulk at the end.
        """
        logger.info("Scanning crypto universe...")
        top_crypto = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "ADA-USD", "AVAX-USD", "DOT-USD", "LINK-USD", "NEAR-USD", "MATIC-USD"]
        
        existing_ids = await persistence_service.get_existing_candidate_ids("Crypto")
        new_candidates = []

        for i in range(len(top_crypto)):
            for j in range(i + 1, len(top_crypto)):
                t_a, t_b = top_crypto[i], top_crypto[j]
                pair_id = f"{t_a}_{t_b}"
                
                if pair_id in existing_ids:
                    continue

                try:
                    df = await self.data_service.get_historical_data_async(
                        [t_a, t_b],
                        "1y",
                        "1d",
                        timeout=settings.MARKET_DATA_TIMEOUT_SECONDS * 2,
                    )
                    if df is None or df.empty or t_a not in df.columns or t_b not in df.columns:
                        continue
                        
                    is_coint, p_val, hedge = self.arbitrage_service.check_cointegration(df[t_a], df[t_b])
                    
                    if is_coint:
                        spread = df[t_a] - (hedge * df[t_b])
                        spread_returns = spread.pct_change().dropna()
                        pair_sortino = self.calculate_sortino_ratio(np.array([1.0]), pd.DataFrame(spread_returns))
                        
                        new_candidates.append(UniverseCandidate(
                            pair_id=pair_id,
                            sector="Crypto",
                            p_value=p_val,
                            correlation=df[t_a].corr(df[t_b]),
                            expected_return=spread_returns.mean() * 365,
                            volatility=spread_returns.std() * np.sqrt(365),
                            sortino=pair_sortino
                        ))
                        logger.info(f"Found new crypto candidate: {pair_id} (Sortino: {pair_sortino:.2f})")
                except Exception as e:
                    continue

        if new_candidates:
            await persistence_service.save_universe_candidates(new_candidates)
            logger.info(f"Successfully inserted {len(new_candidates)} new crypto candidates.")

    async def get_optimization_advice(self, new_ticker: str) -> Dict:
        """
        Assess whether adding the given ticker would improve the portfolio's Sortino ratio.
        
        Returns:
            result (dict): Recommendation and metrics with keys:
                - is_recommended (bool): `True` if adding `new_ticker` increases the portfolio's Sortino ratio, `False` otherwise.
                - improvement (float): The change in Sortino ratio (new_sortino - current_sortino).
                - target_weight (float): Suggested weight for `new_ticker` in the optimized portfolio.
                - optimized_portfolio (dict): Mapping of tickers to optimized weights (present when optimization completed).
        """
        try:
            current_tickers = await persistence_service.get_active_portfolio_tickers()
        except Exception as e:
            logger.warning("Portfolio optimization advice using empty portfolio fallback: %s", e)
            current_tickers = []
        if not current_tickers:
            return {"is_recommended": True, "improvement": 0.0, "target_weight": 0.20}

        all_tickers = list(set(current_tickers + [new_ticker]))
        
        # Fetch data for all
        df = await self.data_service.get_historical_data_async(
            all_tickers,
            "1y",
            "1d",
            timeout=settings.MARKET_DATA_TIMEOUT_SECONDS * 2,
        )
        if df is None or df.empty:
            logger.warning("Portfolio optimization advice skipped: historical data unavailable for %s", all_tickers)
            return {"is_recommended": True, "improvement": 0.0, "target_weight": 0.20}
        returns = df.pct_change().dropna()
        if returns.empty or any(ticker not in returns.columns for ticker in current_tickers):
            logger.warning("Portfolio optimization advice skipped: returns unavailable for %s", all_tickers)
            return {"is_recommended": True, "improvement": 0.0, "target_weight": 0.20}
        
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
        Perform a conditional sector scan based on the market regime of a beacon ticker.
        
        Parameters:
        	sector (str): Name of the sector to scan (e.g., "Information Technology").
        	beacon_ticker (str): Ticker symbol used as the market regime beacon.
        
        Returns:
        	result (dict): If the beacon's regime is "BEARISH" or "EXTREME_VOLATILITY", returns {"status": "VETOED", "reason": "<explanation>"}. Otherwise returns {"status": "COMPLETED", "sector": sector} after initiating the sector scan.
        """
        regime = await macro_economic_agent.get_ticker_regime(beacon_ticker)
        
        if regime in ["BEARISH", "EXTREME_VOLATILITY"]:
            logger.warning(f"NARRATIVE VETO: Sector {sector} scan cancelled. Beacon {beacon_ticker} is {regime}.")
            return {"status": "VETOED", "reason": f"Beacon {beacon_ticker} in {regime} regime"}

        logger.info(f"NARRATIVE APPROVED: Sector {sector} Leader {beacon_ticker} is BULLISH. Scanning followers...")
        await self.scan_sector_universe(sector)
        return {"status": "COMPLETED", "sector": sector}

    @agent_trace("PortfolioManagerAgent.run_discovery")
    async def run_discovery(self):
        """
        Orchestrates discovery of cointegrated trading pairs across selected S&P 500 sectors and the crypto universe.
        
        Runs sector scans for a fixed set of sectors and a subsequent crypto scan; errors for individual sectors or the crypto scan are logged and do not stop the overall cycle. This is intended as a long-running background task.
        
        Returns:
            result (dict): A completion summary with keys:
                - "status": a string status, e.g., "COMPLETED".
                - "timestamp": ISO 8601 timestamp when the run finished.
        """
        logger.info("Starting global pair discovery cycle...")
        sectors = ["Financials", "Information Technology", "Consumer Staples", "Health Care"]
        
        # Scan sectors
        for sector in sectors:
            try:
                await self.scan_sector_universe(sector)
            except Exception as e:
                logger.error(f"Discovery failed for sector {sector}: {e}")
        
        # Scan crypto
        try:
            await self.scan_crypto_universe()
        except Exception as e:
            logger.error(f"Discovery failed for crypto universe: {e}")
            
        logger.info("Global pair discovery cycle completed.")
        return {"status": "COMPLETED", "timestamp": datetime.now().isoformat()}

    @agent_trace("PortfolioManagerAgent.rotate_pairs")
    async def rotate_pairs(self):
        """
        Rotate active trading pairs by replacing them with the top scout candidates ranked by Sortino.
        
        Fetches all TradingPair rows with status "Active" and the top UniverseCandidate rows ordered by descending `sortino`. If there are scout pairs not already active, sets all TradingPair rows' status to "Scout", upserts the selected scout pairs as Active TradingPair rows (using the scout `pair_id` to populate `ticker_a` and `ticker_b`, with `hedge_ratio=0.0` and `is_cointegrated=True`), commits the transaction, and logs the rotation. If there are no active pairs or no scouts, or no scouts to activate, the method returns without making changes.
        """
        from src.services.persistence_service import TradingPair, UniverseCandidate
        from sqlalchemy import select, update, desc
        
        logger.info("Starting pair rotation audit...")
        
        async with persistence_service.AsyncSessionLocal() as session:
            # 1. Get current active pairs
            active_stmt = select(TradingPair).where(TradingPair.status == "Active")
            active_pairs = (await session.execute(active_stmt)).scalars().all()
            
            # 2. Get top candidates (Scouts)
            scout_stmt = select(UniverseCandidate).order_by(desc(UniverseCandidate.sortino)).limit(settings.MAX_ACTIVE_PAIRS)
            scouts = (await session.execute(scout_stmt)).scalars().all()
            
            if not active_pairs or not scouts:
                logger.info("Rotation skipped: Insufficient active pairs or scouts.")
                return
            
            # Sort active pairs by Sortino (if we have it, otherwise we'd need to calculate it)
            # For now, let's assume we want to ensure we have the best Sortino pairs in Active
            
            active_ids = {p.id for p in active_pairs}
            scout_ids = {s.pair_id for s in scouts}
            
            to_activate = scout_ids - active_ids
            if not to_activate:
                logger.info("Rotation completed: No better candidates found.")
                return

            logger.info(f"Identified {len(to_activate)} potential improvements.")
            
            # Simple rotation: swap worst active for best scout
            # In a more advanced version, we'd check PnL and current volatility
            
            # For now, let's just make sure we don't exceed MAX_ACTIVE_PAIRS
            # and that we have the top Sortino pairs active.
            
            # 1. Deactivate all
            await session.execute(update(TradingPair).values(status="Scout"))
            
            # 2. Activate top Sortino scouts
            for scout in scouts:
                # Upsert into TradingPair
                ticker_a, ticker_b = scout.pair_id.split('_')
                p = TradingPair(
                    id=scout.pair_id,
                    ticker_a=ticker_a,
                    ticker_b=ticker_b,
                    hedge_ratio=0.0, # Will be re-calculated by monitor
                    is_cointegrated=True,
                    status="Active"
                )
                await session.merge(p)
            
            await session.commit()
            logger.info(f"Rotated {len(scouts)} pairs into Active status.")

portfolio_manager_agent = PortfolioManagerAgent()
portfolio_manager = portfolio_manager_agent
