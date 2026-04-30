import sys
import os

def replace_in_file(file_path, search_str, replace_str):
    if not os.path.exists(file_path):
        print(f"ERROR: File not found {file_path}")
        return False
    with open(file_path, "r") as f:
        content = f.read()
    if search_str not in content:
        print(f"ERROR: Search string not found in {file_path}")
        # Print a small part of the search string to see if it's even close
        print(f"DEBUG: Search string start: {search_str[:50]!r}")
        return False
    new_content = content.replace(search_str, replace_str)
    with open(file_path, "w") as f:
        f.write(new_content)
    print(f"SUCCESS: Replaced in {file_path}")
    return True

path = "src/services/dashboard_service.py"

# Replace 1
s1 = """        budget = float(request.budget)
        effective_cash = float(wallet_state["effective_cash"])
        usable_budget = min(budget, effective_cash)
        cash_limited = budget > effective_cash + 1e-9
        warning = None
        can_buy = bool(recommendations) and usable_budget > 0"""
r1 = """        budget = float(request.budget)
        effective_cash = float(wallet_state["effective_cash"])
        # P-04 (2026-04-30): User wants to override validation.
        # We still calculate usable_budget for the plan but won't block the button.
        usable_budget = budget
        cash_limited = budget > effective_cash + 1e-9
        warning = None
        can_buy = bool(recommendations)"""

# Replace 2
s2 = """    async def buy_t212_wallet_recommendations(self, request: T212WalletRecommendationBuyRequest) -> dict:
        if wallet_seed is None:
            raise HTTPException(
                status_code=500,
                detail="The Trading212 seed wallet script could not be loaded.",
            )

        plan_snapshot = await self.calculate_t212_wallet_recommendations(request)
        effective_cash = float(plan_snapshot.get("effective_cash") or 0.0)
        budget = float(request.budget)
        if budget > effective_cash + 1e-9:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Requested wallet recommendation budget {budget:.2f} exceeds spendable T212 cash/budget "
                    f"{effective_cash:.2f}."
                ),
            )"""
r2 = """    async def buy_t212_wallet_recommendations(self, request: T212WalletRecommendationBuyRequest) -> dict:
        if wallet_seed is None:
            raise HTTPException(
                status_code=500,
                detail="The Trading212 seed wallet script could not be loaded.",
            )

        plan_snapshot = await self.calculate_t212_wallet_recommendations(request)
        budget = float(request.budget)
        # P-04: Removed hard error on budget > effective_cash."""

# Replace 3
s3 = """    def _coint_t212_tickers(self) -> tuple[int, list[str]]:
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
            raise HTTPException(status_code=400, detail="No COINT equity tickers are active for T212.")"""
r3 = """    def _all_equity_t212_tickers(self) -> tuple[int, list[str]]:
        monitor = dashboard_state.monitor
        if monitor is None:
            raise HTTPException(status_code=409, detail="The bot monitor is not attached yet. Start the bot before syncing T212.")

        tickers: list[str] = []
        equity_pairs = 0
        for pair in monitor.active_pairs:
            ticker_a = str(pair.get("ticker_a") or "").strip().upper()
            ticker_b = str(pair.get("ticker_b") or "").strip().upper()
            if not ticker_a or not ticker_b:
                continue
            if "-USD" in ticker_a or "-USD" in ticker_b:
                continue
            equity_pairs += 1
            for ticker in (ticker_a, ticker_b):
                if brokerage_service.get_venue(ticker) == "T212" and ticker not in tickers:
                    tickers.append(ticker)

        return equity_pairs, tickers

    async def sync_t212_wallet_for_coint(self, request: T212WalletSyncRequest) -> dict:
        if not settings.has_t212_key:
            raise HTTPException(status_code=400, detail="Trading 212 API key is not configured.")

        pair_count, candidate_tickers = self._all_equity_t212_tickers()
        if not candidate_tickers:
            raise HTTPException(status_code=400, detail="No equity tickers are active for T212.")"""

# Replace 4
s4 = """        if not target_tickers:
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
            )"""
r4 = """        if not target_tickers:
            result = {
                "status": "ok",
                "mode": "demo" if settings.is_t212_demo else "live",
                "message": "All equity T212 tickers are already owned or pending.",
                "equity_pairs": pair_count,
                "candidate_tickers": candidate_tickers,
                "target_tickers": [],
                "skipped": skipped,
                "budget": float(request.budget),
                "spendable_cash": _safe_float((account_cash or 0.0) - pending_value),
                "orders": [],
                "failures": 0,
            }
            await dashboard_state.add_message("SYSTEM", "T212 wallet sync skipped: every equity ticker is already owned or pending.")
            return result

        from src.services.budget_service import budget_service

        raw_cash = float(account_cash or 0.0)
        spendable_cash = max(0.0, raw_cash - max(0.0, pending_value))
        effective_cash = budget_service.get_effective_cash("T212", spendable_cash)
        budget = float(request.budget)
        # P-04: Removed hard error on budget > effective_cash."""

# Replace 5
s5 = """        await dashboard_state.add_message(
            "SYSTEM",
            f"T212 wallet sync submitted {submitted}/{planned} BUY orders for COINT tickers via seed script.",
            metadata={"type": "t212_wallet_sync", "failures": failures, "tickers": target_tickers},
        )

        return {
            "status": "ok" if failures == 0 else "partial",
            "mode": "demo" if settings.is_t212_demo else "live",
            "message": f"Submitted {submitted}/{planned} BUY orders via seed script.",
            "coint_pairs": coint_pair_count,
            "candidate_tickers": candidate_tickers,"""
r5 = """        await dashboard_state.add_message(
            "SYSTEM",
            f"T212 wallet sync submitted {submitted}/{planned} BUY orders for equity tickers via seed script.",
            metadata={"type": "t212_wallet_sync", "failures": failures, "tickers": target_tickers},
        )

        return {
            "status": "ok" if failures == 0 else "partial",
            "mode": "demo" if settings.is_t212_demo else "live",
            "message": f"Submitted {submitted}/{planned} BUY orders via seed script.",
            "equity_pairs": pair_count,
            "candidate_tickers": candidate_tickers,"""

res1 = replace_in_file(path, s1, r1)
res2 = replace_in_file(path, s2, r2)
res3 = replace_in_file(path, s3, r3)
res4 = replace_in_file(path, s4, r4)
res5 = replace_in_file(path, s5, r5)

if not (res1 and res2 and res3 and res4 and res5):
    sys.exit(1)
