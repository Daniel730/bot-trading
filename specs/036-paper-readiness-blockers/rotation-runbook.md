# Credential Rotation Runbook

**Context**: The Gemini API key, Polygon API key, Trading 212 key+secret, and Telegram bot token currently in `.env` were exposed in a prior session transcript. They are not in git history (`.env` is gitignored and untracked) but the plaintext values are recoverable from the transcript, so every one of them must be rotated.

**Ground rules**:

- Revoke each old credential at the provider **before** writing the new one locally. Order matters — if a live component re-reads `.env` mid-rotation you want the old value dead rather than half-overwritten.
- Do not paste any rotated value into any log, screenshot, Telegram chat, or non-gitignored file.
- Restart `python src/monitor.py` after all four are rotated. Long-lived processes (the Telegram listener, etc.) cached the old values at import.

## 1 — Gemini (Google AI Studio)

1. Go to <https://aistudio.google.com/app/apikey>.
2. Find the key starting with `AIzaSyBFmq5INV…` → ⋯ menu → **Delete**.
3. Click **Create API Key** → choose your existing GCP project (or create one) → copy the new `AIza…` value.
4. Paste into `.env` on the `GEMINI_API_KEY=` line.

## 2 — Polygon.io

1. Go to <https://polygon.io/dashboard/keys>.
2. Find the key starting with `cFpOgdp…` → **Regenerate** (or **Delete** then **Create**).
3. Copy the new key.
4. Paste into `.env` on the `POLYGON_API_KEY=` line.

## 3 — Trading 212

1. Open Trading 212 → Settings → API → **Demo** tab (since `TRADING_212_MODE=demo`).
2. Find the key starting with `46755752Z…`. Trading 212 does not expose rotation directly; the path is:
   - **Revoke** the existing key.
   - **Generate new key** with the same scopes (read portfolio, place orders). Copy both the API key and the secret.
3. Paste into `.env`:
   - `T212_API_KEY=` (new key)
   - `TRADING_212_API_KEY=` (same new key — the codebase reads both for legacy reasons)
   - `T212_API_SECRET=` (new secret)

## 4 — Telegram Bot

1. Open Telegram → message `@BotFather`.
2. `/mybots` → select the bot whose token starts with `8694704444:…`.
3. **API Token** → **Revoke current token** → confirm.
4. BotFather immediately issues a new token; copy it.
5. Paste into `.env` on the `TELEGRAM_BOT_TOKEN=` line. `TELEGRAM_CHAT_ID` does not change (it's your user/group ID, not the bot's).

## 5 — Verify & restart

```bash
# Confirm .env is still gitignored and untracked:
git ls-files | grep -E '^\.env$'          # must print nothing
git check-ignore .env                     # must print ".env"

# Quick sanity pings (each should succeed with the new values):
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe" | jq .ok  # expect: true
curl -s "https://api.polygon.io/v3/reference/tickers?limit=1&apiKey=${POLYGON_API_KEY}" | jq '.status'  # expect: "OK"

# Restart the bot so the Telegram listener and config singleton reload:
pkill -f "python src/monitor.py" 2>/dev/null
python src/monitor.py
```

## 6 — Mark old values revoked

If any of the four providers still returns `200` for the old value after revocation, treat that as a security incident and escalate (the key may not have been fully revoked). Typical behavior:

| Provider | Response when probing old value after revocation |
|----------|--------------------------------------------------|
| Gemini | `400` "API key not valid" |
| Polygon | `401` "Unknown API key" |
| Trading 212 | `401` / `403` |
| Telegram `getMe` | `401` `Unauthorized` |
