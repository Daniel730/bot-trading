"""
Seed a Trading212 wallet by buying the bot's equity universe equally.

Default mode is a dry run:
    python scripts/seed_equal_wallet.py --budget 1000

To place real/demo Trading212 BUY orders using your .env API key:
    python scripts/seed_equal_wallet.py --budget 1000 --execute

The amount is split as evenly as cents allow across every ticker in
STOCK_TICKERS. Existing positions are not considered; this spends the new
budget equally across the list.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable
from urllib import error, parse, request


REPO_ROOT = Path(__file__).resolve().parents[1]
METADATA_CACHE_PATH = REPO_ROOT / "data" / "t212_instruments_cache.json"

STOCK_TICKERS = (
    "KO", "PEP", "MA", "V", "XOM", "CVX", "JPM", "BAC", "WMT", "TGT",
    "GOOGL", "GOOG", "MSFT", "AAPL", "DAL", "UAL", "UPS", "FDX", "HD",
    "LOW", "GM", "F", "INTC", "AMD", "PYPL", "AFRM", "NKE", "ADS.DE",
    "PG", "CL", "BA", "AIR.PA", "T", "VZ", "VLO", "MPC", "COF", "SYF",
    "GS", "MS", "BTCE.DE", "ZETH.DE", "NVDA", "TSLA", "RIVN", "COIN",
    "MSTR", "META", "SNAP", "NFLX", "DIS", "UBER", "LYFT", "MU", "SMCI",
    "SBUX", "MCD", "SLB", "HAL", "AMZN", "SHOP", "PLTR", "BBAI", "BRK-B",
    "BMW.DE", "MBG.DE", "VOW3.DE", "PAH3.DE", "CON.DE", "PUM.DE", "DBK.DE",
    "CBK.DE", "BNP.PA", "GLE.PA", "ACA.PA", "MC.PA", "RMS.PA", "KER.PA",
    "OR.PA", "EL.PA", "RWE.DE", "EOAN.DE", "ENGI.PA", "ORA.PA", "SHEL.L",
    "BP.L", "RIO.L", "BHP.L", "AAL.L", "GLEN.L", "LLOY.L", "BARC.L",
    "HSBA.L", "STAN.L", "AV.L", "LGEN.L", "TSCO.L", "SBRY.L", "ULVR.L",
    "RKT.L", "BATS.L", "IMB.L", "ASML.AS", "ASM.AS", "LRCX", "AMAT",
    "AVGO", "QCOM", "KLAC", "ASML", "TXN", "ADI", "MCHP", "NXPI", "WDC",
    "STX", "HPQ", "HPE", "CRM", "ADBE", "NOW", "TEAM", "SNOW", "WDAY",
    "SAP", "ADSK", "PTC", "ZS", "CRWD", "PANW", "FTNT", "DDOG", "NET",
    "OKTA", "MDB", "C", "WFC", "BLK", "TROW", "SCHW", "IBKR", "PNC",
    "USB", "BX", "KKR", "SPGI", "MCO", "CME", "ICE", "MET", "PRU",
    "AIG", "TRV", "COST", "BJ", "LULU", "DG", "DLTR", "TJX", "ROST",
    "ULTA", "BKNG", "EXPE", "MAR", "HLT", "YUM", "QSR", "MDLZ", "HSY",
    "KMB", "PSX", "COP", "EOG", "CAT", "DE", "LMT", "NOC", "GD", "RTX",
    "WM", "RSG", "UNP", "NSC", "CSX", "CP", "ETN", "EMR", "URI", "HRI",
    "VMC", "MLM", "GE", "HON", "PFE", "MRK", "JNJ", "ABBV", "LLY",
    "NVO", "UNH", "ELV", "CI", "HUM", "ISRG", "SYK", "BSX", "MDT",
    "TMO", "A", "AMGN", "GILD", "ZTS", "IDXX", "REGN", "VRTX", "MCK",
    "COR", "AMT", "CCI", "PLD", "PSA", "O", "ADC", "DUK", "SO", "NEE",
    "D", "AEP", "SRE", "CMCSA", "CHTR", "SPOT", "WMG",
)


def parse_money(value: str) -> Decimal:
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError(f"Invalid money value: {value}") from exc
    if amount <= 0:
        raise argparse.ArgumentTypeError("Budget must be greater than zero.")
    return amount


def unique_ordered(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in values:
        ticker = raw.strip().upper()
        if ticker and ticker not in seen:
            seen.add(ticker)
            result.append(ticker)
    return result


def build_equal_plan(total_budget: Decimal, tickers: list[str]) -> list[tuple[str, Decimal]]:
    cents = int((total_budget * Decimal("100")).to_integral_value())
    if cents < len(tickers):
        raise ValueError(
            f"Budget {total_budget} is too small for {len(tickers)} tickers; "
            "each ticker needs at least 0.01."
        )

    base_cents = cents // len(tickers)
    extra_cents = cents % len(tickers)
    plan: list[tuple[str, Decimal]] = []
    for index, ticker in enumerate(tickers):
        ticker_cents = base_cents + (1 if index < extra_cents else 0)
        plan.append((ticker, Decimal(ticker_cents) / Decimal("100")))
    return plan


def load_env_values() -> dict[str, str]:
    values = dict(os.environ)
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return values

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        values.setdefault(key, value)
    return values


def t212_config() -> tuple[str, dict[str, str]]:
    env = load_env_values()
    api_key = (env.get("T212_API_KEY") or env.get("TRADING_212_API_KEY") or "").strip()
    api_secret = (env.get("T212_API_SECRET") or "").strip()
    mode = (env.get("TRADING_212_MODE") or "demo").strip().lower()
    if not api_key:
        raise RuntimeError("Missing T212_API_KEY or TRADING_212_API_KEY in .env/environment.")

    base_url = (
        "https://demo.trading212.com/api/v0"
        if mode == "demo"
        else "https://live.trading212.com/api/v0"
    )
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "bot-trading-seed-wallet/1.0",
    }
    if api_secret:
        token = base64.b64encode(f"{api_key}:{api_secret}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {token}"
    else:
        headers["Authorization"] = api_key
    return base_url, headers


def http_json(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    payload: dict | None = None,
    params: dict | None = None,
    timeout: float = 20.0,
):
    if params:
        url = f"{url}?{parse.urlencode(params)}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        method=method,
        headers=headers or {"Accept": "application/json", "User-Agent": "bot-trading-seed-wallet/1.0"},
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            if not body:
                return {}
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return {"raw": body}
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {"status": "error", "http_status": exc.code, "message": body}


def is_access_denied_1010(result) -> bool:
    if not isinstance(result, dict):
        return False
    message = str(result.get("message", ""))
    return "error code: 1010" in message.lower()


def is_too_many_requests(result) -> bool:
    if not isinstance(result, dict):
        return False
    text = json.dumps(result).lower()
    return "toomanyrequests" in text or "too many requests" in text or result.get("http_status") == 429


def is_entity_not_found(result) -> bool:
    if not isinstance(result, dict):
        return False
    text = json.dumps(result).lower()
    return "entity-not-found" in text or "ticker does not exist" in text


def is_instrument_disabled(result) -> bool:
    if not isinstance(result, dict):
        return False
    text = json.dumps(result).lower()
    return "instrument-disabled" in text or "instrument is disabled" in text


def raise_for_t212_access(result, action: str) -> None:
    if is_access_denied_1010(result):
        raise RuntimeError(
            f"Trading212 blocked the request while trying to {action} (Cloudflare error 1010). "
            "This is a network/access block, not a ticker/order-size problem. "
            "Try disabling VPN/proxy, using a normal home/mobile network, or contacting Trading212 "
            "support with the Access Denied reference."
        )


def format_t212_ticker(ticker: str) -> str:
    if "_" in ticker:
        return ticker
    suffixes = {
        ".DE": "_DE_EQ",
        ".PA": "_PA_EQ",
        ".L": "_L_EQ",
        ".AS": "_AS_EQ",
        ".SW": "_SW_EQ",
        ".MI": "_MI_EQ",
    }
    for suffix, replacement in suffixes.items():
        if ticker.endswith(suffix):
            return ticker.removesuffix(suffix) + replacement
    return f"{ticker}_US_EQ"


def fetch_t212_metadata(base_url: str, headers: dict[str, str]) -> dict[str, dict]:
    data = http_json("GET", f"{base_url}/equity/metadata/instruments", headers=headers)
    raise_for_t212_access(data, "load instrument metadata")
    if isinstance(data, dict) and data.get("status") == "error":
        if METADATA_CACHE_PATH.exists():
            print(f"Warning: metadata request failed; using cached Trading212 metadata from {METADATA_CACHE_PATH}.")
            cached = json.loads(METADATA_CACHE_PATH.read_text(encoding="utf-8"))
            return {item.get("ticker"): item for item in cached if item.get("ticker")}
        raise RuntimeError(
            f"Could not load Trading212 metadata and no cache exists: {data.get('message')}"
        )
    if not isinstance(data, list):
        return {}
    METADATA_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    METADATA_CACHE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return {item.get("ticker"): item for item in data if item.get("ticker")}


def t212_candidates(ticker: str) -> list[str]:
    ticker = ticker.upper()
    candidates = [format_t212_ticker(ticker)]
    if "-" in ticker:
        candidates.append(format_t212_ticker(ticker.replace("-", ".")))
    if "." not in ticker and "_" not in ticker:
        candidates.append(ticker)
    return unique_ordered(candidates)


def resolve_t212_ticker(ticker: str, metadata: dict[str, dict]) -> str | None:
    for candidate in t212_candidates(ticker):
        if candidate in metadata:
            return candidate
    return None


def is_metadata_tradeable(instrument: dict) -> bool:
    return True


def preflight_t212_access(base_url: str, headers: dict[str, str]) -> None:
    result = http_json("GET", f"{base_url}/equity/account/cash", headers=headers)
    raise_for_t212_access(result, "read account cash")
    if isinstance(result, dict) and result.get("status") == "error":
        raise RuntimeError(
            f"Trading212 account-cash preflight failed: HTTP {result.get('http_status')} "
            f"{result.get('message')}"
        )


def yahoo_latest_price(ticker: str) -> Decimal:
    symbol = parse.quote(ticker, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    data = http_json(
        "GET",
        url,
        headers={"User-Agent": "Mozilla/5.0"},
        params={"range": "1d", "interval": "1m"},
        timeout=15.0,
    )
    try:
        meta = data["chart"]["result"][0]["meta"]
    except Exception as exc:
        raise RuntimeError(f"Yahoo price unavailable for {ticker}") from exc

    price = (
        meta.get("regularMarketPrice")
        or meta.get("previousClose")
        or meta.get("chartPreviousClose")
    )
    if not price or float(price) <= 0:
        raise RuntimeError(f"Invalid Yahoo price for {ticker}: {price}")
    return Decimal(str(price))


def round_to_increment(value: Decimal, increment: Decimal, rounding=ROUND_HALF_UP) -> Decimal:
    if increment <= 0:
        return value
    return (value / increment).quantize(Decimal("1"), rounding=rounding) * increment


def build_t212_buy_payload(
    ticker: str,
    t212_ticker: str,
    amount: Decimal,
    price: Decimal,
    metadata: dict[str, dict],
    slippage: Decimal,
    quantity_decimals: int,
) -> dict:
    instrument = metadata.get(t212_ticker, {})
    qty_increment = Decimal("1").scaleb(-quantity_decimals)
    min_qty = Decimal(str(instrument.get("minTradeQuantity", "0") or "0"))
    tick_size = Decimal(str(instrument.get("tickSize", "0.01") or "0.01"))

    quantity = round_to_increment(amount / price, qty_increment, rounding=ROUND_DOWN)
    if quantity <= 0:
        raise RuntimeError(f"Quantity rounds to zero for {ticker}.")
    if min_qty > 0 and quantity < min_qty:
        raise RuntimeError(f"Quantity {quantity} below Trading212 minTradeQuantity {min_qty}.")

    limit_price = round_to_increment(price * (Decimal("1") + slippage), tick_size)
    return {
        "ticker": t212_ticker,
        "quantity": float(quantity),
        "limitPrice": float(limit_price),
        "timeValidity": "DAY",
    }


def print_plan(plan: list[tuple[str, Decimal]], total_budget: Decimal, execute: bool) -> None:
    mode = "EXECUTE" if execute else "DRY RUN"
    print(f"\nMode: {mode}")
    print(f"Tickers: {len(plan)}")
    print(f"Total budget: {total_budget:.2f}")
    print(f"Per ticker: {plan[-1][1]:.2f} to {plan[0][1]:.2f}")
    print("\nOrders:")
    for idx, (ticker, amount) in enumerate(plan, start=1):
        print(f"{idx:>3}. BUY {ticker:<8} value={amount:.2f}")


def confirm_execution(plan: list[tuple[str, Decimal]], total_budget: Decimal) -> None:
    print(
        f"\nThis will place {len(plan)} BUY orders for about {total_budget:.2f} "
        "total using the Trading212 API configured in .env."
    )
    answer = input("Type BUY ALL to continue: ").strip()
    if answer != "BUY ALL":
        raise SystemExit("Aborted.")


async def execute_plan(
    plan: list[tuple[str, Decimal]],
    delay_seconds: float,
    slippage: Decimal,
    quantity_decimals: int,
    rate_limit_wait: float,
    max_retries: int,
) -> int:
    base_url, headers = t212_config()
    preflight_t212_access(base_url, headers)
    metadata = fetch_t212_metadata(base_url, headers)
    total_budget = sum(amount for _, amount in plan)
    resolved: dict[str, str] = {}
    skipped: list[tuple[str, str]] = []

    for ticker, _ in plan:
        t212_ticker = resolve_t212_ticker(ticker, metadata)
        if not t212_ticker:
            skipped.append((ticker, "not found in Trading212 instruments"))
            continue
        if not is_metadata_tradeable(metadata.get(t212_ticker, {})):
            skipped.append((ticker, f"{t212_ticker} is not tradeable"))
            continue
        resolved[ticker] = t212_ticker

    if skipped:
        print(f"\nSkipping {len(skipped)} unsupported/disabled tickers before order placement:")
        for ticker, reason in skipped:
            print(f"  SKIP {ticker:<8} {reason}")

    if not resolved:
        print("No Trading212-supported tickers left after filtering.")
        return len(plan)

    if len(resolved) != len(plan):
        plan = build_equal_plan(total_budget, list(resolved))
        print(
            f"\nRebalanced {total_budget:.2f} across {len(plan)} supported tickers "
            f"({plan[-1][1]:.2f} to {plan[0][1]:.2f} each)."
        )

    failures = 0

    for idx, (ticker, amount) in enumerate(plan, start=1):
        t212_ticker = resolved[ticker]
        print(f"[{idx}/{len(plan)}] BUY {ticker} ({t212_ticker}) value={amount:.2f} ...", flush=True)
        try:
            price = await asyncio.to_thread(yahoo_latest_price, ticker)
            payload = build_t212_buy_payload(
                ticker,
                t212_ticker,
                amount,
                price,
                metadata,
                slippage,
                quantity_decimals,
            )
            result = None
            for attempt in range(max_retries + 1):
                result = await asyncio.to_thread(
                    http_json,
                    "POST",
                    f"{base_url}/equity/orders/limit",
                    headers,
                    payload,
                )
                raise_for_t212_access(result, f"place BUY order for {ticker}")
                if not is_too_many_requests(result):
                    break
                if attempt >= max_retries:
                    break
                wait = rate_limit_wait * (attempt + 1)
                print(f"  RATE LIMITED: waiting {wait:.1f}s before retry {attempt + 1}/{max_retries} ...")
                await asyncio.sleep(wait)
        except Exception as exc:
            failures += 1
            print(f"  ERROR: {exc}")
        else:
            if result.get("status") == "error":
                if is_entity_not_found(result) or is_instrument_disabled(result):
                    print(f"  SKIPPED PERMANENTLY: {result.get('message', result)}")
                else:
                    failures += 1
                    print(f"  REJECTED: {result.get('message', result)}")
            else:
                order_id = result.get("orderId") or result.get("order_id") or result.get("id") or "N/A"
                print(f"  OK: order_id={order_id}, payload={payload}")

        if idx < len(plan) and delay_seconds > 0:
            await asyncio.sleep(delay_seconds)

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Buy the bot stock universe with an equal value per ticker."
    )
    parser.add_argument("--budget", type=parse_money, help="Total amount to split across all tickers.")
    parser.add_argument("--execute", action="store_true", help="Actually place Trading212 BUY orders.")
    parser.add_argument("--yes", action="store_true", help="Skip the BUY ALL confirmation prompt.")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds to wait between orders.")
    parser.add_argument("--slippage", type=parse_money, default=Decimal("0.01"), help="Limit-order slippage, e.g. 0.01 for 1%%.")
    parser.add_argument("--quantity-decimals", type=int, default=2, help="Decimal places for share quantity. Trading212 commonly accepts 2.")
    parser.add_argument("--rate-limit-wait", type=float, default=5.0, help="Seconds to wait after a TooManyRequests response.")
    parser.add_argument("--max-retries", type=int, default=2, help="Retries per order after rate limits.")
    parser.add_argument(
        "--tickers",
        nargs="+",
        help="Optional custom ticker subset. Defaults to the full STOCK_TICKERS list.",
    )
    parser.add_argument(
        "--max-tickers",
        type=int,
        help="Optional first-N ticker limit for testing a small dry run.",
    )
    args = parser.parse_args()

    total_budget = args.budget
    if total_budget is None:
        total_budget = parse_money(input("Total amount to spend: ").strip())

    tickers = unique_ordered(args.tickers or STOCK_TICKERS)
    if args.max_tickers:
        tickers = tickers[: args.max_tickers]
    if not tickers:
        raise SystemExit("No tickers selected.")

    plan = build_equal_plan(total_budget, tickers)
    print_plan(plan, total_budget, execute=args.execute)

    if not args.execute:
        print("\nDry run only. Add --execute to place orders.")
        return 0

    if not args.yes:
        confirm_execution(plan, total_budget)

    failures = asyncio.run(
        execute_plan(
            plan,
            delay_seconds=max(0.0, args.delay),
            slippage=args.slippage,
            quantity_decimals=max(0, args.quantity_decimals),
            rate_limit_wait=max(1.0, args.rate_limit_wait),
            max_retries=max(0, args.max_retries),
        )
    )
    print(f"\nDone. Success={len(plan) - failures}, failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
