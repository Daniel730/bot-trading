"""
End-to-end Trading 212 smoke test.

Run from the repo root:
    python scripts/test_t212_e2e.py            # uses ticker AAPL on demo
    python scripts/test_t212_e2e.py --ticker MSFT
    python scripts/test_t212_e2e.py --keep     # don't cancel the test order

What it does (in order):
    1.  Loads T212_API_KEY / T212_API_SECRET / TRADING_212_MODE from .env
    2.  Refuses to proceed if TRADING_212_MODE=live (use --allow-live to override)
    3.  GET  /equity/account/cash         -- proves auth + account access
    4.  GET  /equity/portfolio            -- lists current holdings
    5.  GET  /equity/metadata/instruments -- looks up the test ticker
    6.  POST /equity/orders/limit         -- places a tiny limit order WAY
                                             below market so it stays pending.
                                             Uses the EXACT payload shape the
                                             bot sends. Auto-recovers from:
                                               - min-quantity-exceeded (parses
                                                 the required min, retries)
                                               - quantity-precision-mismatch
                                                 (rounds qty to fewer decimals)
                                               - 429 rate-limit (backs off)
    7.  GET  /equity/orders               -- proves the order is pending
    8.  DELETE /equity/orders/{id}        -- cancels it (unless --keep)
    9.  GET  /equity/orders               -- proves it's gone
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
from pathlib import Path

import requests


class C:
    R = "\033[31m"; G = "\033[32m"; Y = "\033[33m"; B = "\033[34m"
    M = "\033[35m"; DIM = "\033[2m"; BOLD = "\033[1m"; END = "\033[0m"


def banner(t): print(f"\n{C.BOLD}{C.B}========== {t} =========={C.END}")
def ok(msg):   print(f"{C.G}[PASS]{C.END} {msg}")
def fail(msg): print(f"{C.R}[FAIL]{C.END} {msg}")
def info(msg): print(f"{C.DIM}[..]{C.END}   {msg}")


def load_env(env_path: Path) -> dict:
    if not env_path.exists():
        return {}
    out = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def http(method, url, headers, body=None, label=""):
    print(f"{C.M}> {method} {url}{C.END}")
    if body is not None:
        print(f"  payload: {json.dumps(body)}")
    t0 = time.time()
    try:
        r = requests.request(method, url, headers=headers, json=body, timeout=15)
    except requests.RequestException as e:
        elapsed = (time.time() - t0) * 1000
        fail(f"{label or method} network error after {elapsed:.0f} ms: {e}")
        return None, str(e)
    elapsed = (time.time() - t0) * 1000
    body_preview = r.text[:600]
    color = C.G if 200 <= r.status_code < 300 else C.R
    print(f"  {color}<- {r.status_code} {r.reason}{C.END} ({elapsed:.0f} ms)")
    if body_preview:
        print(f"  body: {body_preview}")
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, r.text


def main():
    parser = argparse.ArgumentParser(description="T212 end-to-end smoke test")
    parser.add_argument("--ticker", default="AAPL", help="Symbol to test (default AAPL)")
    parser.add_argument("--keep", action="store_true",
                        help="Do not cancel the test order at the end")
    parser.add_argument("--allow-live", action="store_true",
                        help="DANGEROUS - allow running against live mode")
    parser.add_argument("--limit-price", type=float, default=1.00,
                        help="Limit price USD (default 1.00 -- far below market)")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    env = load_env(repo_root / ".env")
    api_key = env.get("T212_API_KEY") or env.get("TRADING_212_API_KEY") or os.getenv("T212_API_KEY", "")
    api_secret = env.get("T212_API_SECRET") or os.getenv("T212_API_SECRET", "")
    mode = (env.get("TRADING_212_MODE") or os.getenv("TRADING_212_MODE") or "demo").lower()
    api_key = api_key.strip()
    api_secret = api_secret.strip()

    banner("CONFIGURATION")
    info(f"Repo root: {repo_root}")
    info(f"Mode: {mode}")
    info(f"Key:  {api_key[:4]}...{api_key[-4:]} ({len(api_key)} chars)")
    info(f"Secret: {'<set,'+str(len(api_secret))+' chars>' if api_secret else '<empty>'}")
    info(f"Test ticker: {args.ticker}")

    if not api_key:
        fail("No T212_API_KEY in .env. Aborting.")
        sys.exit(1)
    if mode == "live" and not args.allow_live:
        fail("TRADING_212_MODE=live in .env. Refusing to run smoke test on LIVE.")
        fail("Re-run with --allow-live if you really want to (NOT recommended).")
        sys.exit(2)

    base_url = ("https://demo.trading212.com/api/v0"
                if mode != "live" else "https://live.trading212.com/api/v0")
    info(f"Base URL: {base_url}")

    if api_key and api_secret:
        creds = base64.b64encode(f"{api_key}:{api_secret}".encode()).decode()
        headers = {"Content-Type": "application/json",
                   "Authorization": f"Basic {creds}"}
        info("Auth: BASIC (key+secret)")
    else:
        headers = {"Content-Type": "application/json", "Authorization": api_key}
        info("Auth: DIRECT (key only)")

    results = {}

    # --- Step 1: Auth + cash ---
    banner("STEP 1 / AUTH: GET /equity/account/cash")
    code, body = http("GET", f"{base_url}/equity/account/cash", headers, label="cash")
    if code == 200 and isinstance(body, dict) and "free" in body:
        ok(f"Auth works. Free cash = {body.get('free')}")
        results["auth"] = True
    elif code == 401:
        fail("401 Unauthorized -- API key/secret rejected.")
        results["auth"] = False
    else:
        fail(f"Unexpected response on cash: status={code}, body={body!r}")
        results["auth"] = False

    if not results["auth"]:
        banner("RESULT")
        fail("Cannot proceed without auth. Stopping.")
        sys.exit(3)

    time.sleep(1.0)

    # --- Step 2: Portfolio ---
    banner("STEP 2 / PORTFOLIO: GET /equity/portfolio")
    code, body = http("GET", f"{base_url}/equity/portfolio", headers, label="portfolio")
    if code == 200 and isinstance(body, list):
        ok(f"Portfolio retrieved ({len(body)} positions).")
        for pos in body[:5]:
            info(f"  {pos.get('ticker')} qty={pos.get('quantity')}")
        results["portfolio"] = True
    else:
        fail(f"Portfolio endpoint failed: status={code}")
        results["portfolio"] = False

    time.sleep(1.0)

    # --- Step 3: Instrument metadata ---
    banner("STEP 3 / METADATA: GET /equity/metadata/instruments")
    code, body = http("GET", f"{base_url}/equity/metadata/instruments",
                      headers, label="instruments")

    def _fmt_t212(t: str) -> str:
        if "_" in t: return t
        if t.endswith(".DE"): return t.replace(".DE", "_DE_EQ")
        if t.endswith(".PA"): return t.replace(".PA", "_PA_EQ")
        if t.endswith(".L"):  return t.replace(".L", "_L_EQ")
        return f"{t}_US_EQ"

    t212_ticker = _fmt_t212(args.ticker)
    instrument = None
    if code == 200 and isinstance(body, list):
        ok(f"Instrument catalogue size: {len(body)}")
        for inst in body:
            if inst.get("ticker") == t212_ticker:
                instrument = inst
                break
        if instrument:
            ok(f"Test ticker {args.ticker!r} resolved to {t212_ticker!r}")
            info(f"  minTradeQuantity = {instrument.get('minTradeQuantity')}")
            info(f"  maxOpenQuantity  = {instrument.get('maxOpenQuantity')}")
            info(f"  currencyCode     = {instrument.get('currencyCode')}")
            info(f"  workingScheduleId= {instrument.get('workingScheduleId')}")
            results["metadata"] = True
        else:
            fail(f"{t212_ticker!r} NOT in T212 catalogue. Try a different --ticker.")
            results["metadata"] = False
    else:
        fail(f"Metadata endpoint failed: status={code}")
        results["metadata"] = False

    if not results["metadata"]:
        banner("RESULT")
        fail("Cannot proceed without a valid test ticker.")
        sys.exit(4)

    # --- Step 4: Place a tiny pending limit order ---
    banner("STEP 4 / PLACE LIMIT: POST /equity/orders/limit")

    limit_price = float(args.limit_price)
    qty = 0.01
    qty_decimals = 8  # start with 8, decrease on precision-mismatch errors
    placed = None
    placed_id = None
    max_attempts = 8

    def _round(q: float, d: int) -> float:
        return float(f"{round(q, d):.{max(d,0)}f}")

    for attempt in range(1, max_attempts + 1):
        send_qty = _round(qty, qty_decimals)
        payload = {
            "ticker": t212_ticker,
            "quantity": send_qty,
            "limitPrice": limit_price,
            "timeValidity": "DAY",
        }
        info(f"Attempt {attempt}: limit ${limit_price:.2f}, qty {send_qty} "
             f"(precision={qty_decimals}, notional ~${send_qty * limit_price:.4f})")
        code, body = http("POST", f"{base_url}/equity/orders/limit",
                          headers, body=payload, label="place_limit")

        time.sleep(2.0)  # pace requests

        if 200 <= (code or 0) < 300 and isinstance(body, dict):
            placed = body
            placed_id = body.get("id")
            ok(f"Order accepted. id={placed_id}, status={body.get('status')}")
            results["place"] = True
            break

        # min-quantity-exceeded -> bump qty
        if isinstance(body, dict) and "min-quantity-exceeded" in str(body.get("type", "")):
            m = re.search(r"at least\s+([\d.]+)", str(body.get("detail", "")))
            if m:
                required = float(m.group(1))
                qty = required * 1.10
                info(f"T212 minimum: {required}. Retrying with qty={qty:.8f}")
                continue

        # quantity-precision-mismatch -> round more aggressively
        if isinstance(body, dict) and "precision" in str(body.get("type", "")):
            if qty_decimals > 4:
                qty_decimals = 4
            elif qty_decimals > 2:
                qty_decimals = 2
            elif qty_decimals > 0:
                qty_decimals = 0
            else:
                info("Already at integer precision. Cannot reduce further.")
                break
            # When dropping precision, also bump qty by enough to stay above min.
            qty = qty + 0.05  # small bump to avoid landing under min after rounding
            info(f"Reducing precision to {qty_decimals} decimals (qty -> {qty:.4f})")
            continue

        # 429 -> back off
        if code == 429:
            info("Rate-limited (429). Backing off 8 s before retry...")
            time.sleep(8.0)
            continue

        info(f"Non-recoverable rejection at attempt {attempt}: status={code}")
        break

    if not placed:
        fail("Order placement failed. Inspect the broker response above.")
        results["place"] = False

    # --- Step 5: Verify pending ---
    if results.get("place"):
        banner("STEP 5 / VERIFY PENDING: GET /equity/orders")
        time.sleep(1.0)
        code, body = http("GET", f"{base_url}/equity/orders", headers,
                          label="pending_orders")
        if code == 200 and isinstance(body, list):
            match = [o for o in body if str(o.get("id")) == str(placed_id)]
            if match:
                ok(f"Test order {placed_id} found in pending orders.")
                info(f"  details: {json.dumps(match[0])[:400]}")
                results["verify_pending"] = True
            else:
                fail(f"Test order {placed_id} NOT in pending list. "
                     f"It may have been filled or rejected.")
                results["verify_pending"] = False
        else:
            fail(f"Pending list fetch failed: status={code}")
            results["verify_pending"] = False
    else:
        results["verify_pending"] = False

    time.sleep(1.0)

    # --- Step 6: Cancel ---
    if results.get("place") and not args.keep:
        banner("STEP 6 / CANCEL: DELETE /equity/orders/{id}")
        code, body = http("DELETE", f"{base_url}/equity/orders/{placed_id}",
                          headers, label="cancel")
        if 200 <= (code or 0) < 300:
            ok(f"Cancellation accepted for order {placed_id}.")
            results["cancel"] = True
        else:
            fail(f"Cancel failed: status={code}, body={body!r}")
            results["cancel"] = False

        # --- Step 7: Verify gone ---
        banner("STEP 7 / VERIFY CANCELLED: GET /equity/orders")
        time.sleep(2.0)
        code, body = http("GET", f"{base_url}/equity/orders", headers,
                          label="post_cancel_list")
        if code == 200 and isinstance(body, list):
            still_there = [o for o in body if str(o.get("id")) == str(placed_id)]
            if still_there:
                fail(f"Order {placed_id} still pending after cancel. "
                     f"State: {still_there[0]}")
                results["verify_cancel"] = False
            else:
                ok(f"Order {placed_id} no longer pending. Clean cancel confirmed.")
                results["verify_cancel"] = True
        else:
            fail(f"Verification fetch failed: status={code}")
            results["verify_cancel"] = False
    elif args.keep and results.get("place"):
        banner("STEP 6 / CANCEL: skipped (--keep)")
        info(f"Order {placed_id} left pending. Cancel manually if desired.")
        results["cancel"] = "skipped"
        results["verify_cancel"] = "skipped"

    # --- Summary ---
    banner("RESULT SUMMARY")
    expected = ["auth", "portfolio", "metadata", "place", "verify_pending"]
    if not args.keep:
        expected += ["cancel", "verify_cancel"]
    all_ok = True
    for step in expected:
        v = results.get(step)
        tag = "PASS" if v is True else ("SKIP" if v == "skipped" else "FAIL")
        color = C.G if tag == "PASS" else (C.Y if tag == "SKIP" else C.R)
        print(f"  {color}{tag:5s}{C.END} {step}")
        if v is not True and v != "skipped":
            all_ok = False
    print()
    if all_ok:
        print(f"{C.BOLD}{C.G}*** ALL CHECKS PASSED ***{C.END}")
        print(f"{C.G}Bot <-> Trading 212 (DEMO) workflow is fully operational.{C.END}")
        sys.exit(0)
    else:
        print(f"{C.BOLD}{C.R}*** SOME CHECKS FAILED -- review the steps above ***{C.END}")
        sys.exit(5)


if __name__ == "__main__":
    main()
