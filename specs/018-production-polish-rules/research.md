# Phase 0 Research: Production-Grade Polish & Reliability Enforcement

## State Persistence

- **Decision**: Kalman Filter state persistence will be moved from `monitor.py` into `ArbitrageService` for better encapsulation.
- **Rationale**: The specification explicitly states `ArbitrageService` MUST persist and reload. This allows the service to manage its own state lifecycle regardless of the monitor implementation.
- **Implementation**: `ArbitrageService.get_or_create_filter` will be updated to attempt loading from `PersistenceManager` (SQLite) or `RedisService`.

## API Caching

- **Decision**: A 5-second TTL cache will be implemented in `BrokerageService` for `/portfolio` and `/orders` endpoints.
- **Rationale**: Prevents 429 Rate Limit API bans by serving recently fetched data for redundant requests (e.g., from different agents or the dashboard).
- **Implementation**: A simple `_cache` dictionary with timestamps will be used inside `BrokerageService`.

## Slippage Guards

- **Decision**: All fractional market orders in `BrokerageService` will include a `limitPrice` calculated as 1% offset from the current price.
- **Rationale**: Protects against "flash-crash" slippage where market orders could fill at highly unfavorable prices.
- **Implementation**: `place_market_order` will be modified to accept an optional `limit_price` or calculate it automatically using `data_service` if not provided.

## DRIP Safety

- **Decision**: Dividend reinvestment logic will cap execution value at `min(gross_dividend, available_free_cash)`.
- **Rationale**: Prevents "Insufficient Funds" errors by ensuring the bot doesn't attempt to reinvest more than the received dividend or the available account balance.
- **Implementation**: `check_dividends_and_reinvest` in `BrokerageService` will be fully implemented with this logic.

## Timezone Sync

- **Decision**: Update `config.py` to NYSE Regular Trading Hours (9:30 AM - 4:00 PM) and use `pytz` for explicit 'America/New_York' timezone management.
- **Rationale**: Ensures the bot operates strictly during periods of high liquidity and stays synchronized regardless of server location or DST changes.
- **Implementation**: `START_HOUR`, `START_MINUTE`, `END_HOUR`, `END_MINUTE` in `config.py` will be updated. `monitor.py` will use `pytz.timezone('America/New_York')`.
