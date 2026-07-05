# Análise do Bot de Trading — Diagnóstico para MVP Demo

> **Abordagem:** Análise em 6 contextos simultâneos: Correctness de código, Fluxo de execução de trades, Resiliência/Infraestrutura, Segurança e segredos, Integração com Trading 212 API, e Completude de features para Demo.

---

## 🔴 BUGS CRÍTICOS — Bloqueiam o MVP (Corrigir Agora)

### 1. `NameError` no Orchestrator — Uso de variável antes de definição

**Ficheiro:** `src/agents/orchestrator.py`, linhas 83–84

```python
# LINHA 80-85: telemetry_service.broadcast é chamado com score_a e score_b
telemetry_service.broadcast("thought", {
    "agent_name": "SEC_AGENT",
    "thought": f"Structural Integrity Scores: {ticker_a}={score_a}, {ticker_b}={score_b}",  # ← CRASH
    "verdict": "VETO" if score_a < 40 or score_b < 40 else "NEUTRAL"
})
```

`score_a` e `score_b` só são **definidas nas linhas 107 e 117**, depois dos resultados do `asyncio.gather`. Este broadcast causa `NameError` em cada ciclo de análise. **Nenhum trade chega a ser avaliado.**

**Correção:** Mover este bloco de telemetria para depois da linha 124.

---

### 2. `execute_trade` no `monitor.py` usa mock puro — Nunca executa trades reais

**Ficheiro:** `src/monitor.py`, linhas 166–201

```python
# "Mock execution results"
order_id_a = str(uuid.uuid4())   # IDs fake
order_id_b = str(uuid.uuid4())   # IDs fake
# Logs imediatos como COMPLETED — nunca chama brokerage_service nem execution_service_client
```

O método `execute_trade` no monitor regista trades na base de dados com IDs gerados localmente e status `COMPLETED`, mas **nunca chama** `brokerage_service.place_market_order()` nem `execution_service_client.execute_trade()`. O bot detecta sinais, pede aprovação ao Telegram, recebe "Approve" e depois… não faz nada no broker.

**Correção:** Integrar `brokerage_service` ou `execution_service_client` em `monitor.execute_trade()`.

---

### 3. `ConnectionManager` usa `List` sem import em `dashboard_service.py`

**Ficheiro:** `src/services/dashboard_service.py`, linha 19

```python
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []  # ← NameError: List not imported
```

`List` não está importado no topo do ficheiro (`from typing import List` está ausente). O dashboard falha a arrancar com um `NameError` imediato.

---

### 4. `data_service.get_latest_price` é `async` mas `_handle_cash` em `notification_service.py` chama-a de forma síncrona

**Ficheiro:** `src/services/notification_service.py`, linha 156

```python
prices = data_service.get_latest_price([sweep_ticker])   # ← Falta await
price = prices.get(sweep_ticker, 0.0)
```

`get_latest_price` é `async def`. Sem `await`, `prices` será um objeto coroutine, e `.get()` lança `AttributeError`. O comando `/cash` do Telegram crashará sempre.

---

### 5. `shadow_service.get_active_portfolio_with_sectors` é `async` mas é chamada como síncrona

**Ficheiros:** `src/services/notification_service.py` linha 176, e `src/services/dashboard_service.py` (indirectamente via `handle_dashboard_command`)

```python
portfolio = shadow_service.get_active_portfolio_with_sectors()  # ← Falta await
exposures = risk_service.get_all_sector_exposures(portfolio)    # recebe coroutine
```

`get_active_portfolio_with_sectors` é `async def`. Os comandos `/exposure` do Telegram e do dashboard falham com dados inválidos.

---

### 6. `risk_service.get_all_sector_exposures` não existe

**Ficheiros:** `src/services/notification_service.py` linhas 176–177, e `src/services/dashboard_service.py` linha (handle_dashboard_command)

O método `get_all_sector_exposures` é chamado em múltiplos lugares mas **não está definido** em `RiskService`. Qualquer chamada a `/exposure` lança `AttributeError`.

---

### 7. `src/models/persistence.py` — Módulo referenciado mas inexistente

**Ficheiros:** `dashboard_service.py`, `notification_service.py`

```python
from src.models.persistence import PersistenceManager
```

`src/models/` contém apenas `__init__.py`. Não existe `persistence.py` nem `PersistenceManager`. O dashboard e os comandos `/invest schedule`, `/portfolio define` lançam `ModuleNotFoundError` na startup.

---

### 8. `T212 API Auth` — Using Basic Auth com Key+Secret mas API pública é Key-only

**Ficheiro:** `src/services/brokerage_service.py`, linhas 23–36

O código constrói `Basic {base64(key:secret)}`. A [Trading 212 API v0](https://t212public-api-docs.redoc.ly/) usa apenas `Authorization: {API_KEY}` — **não é Basic Auth**. Todas as chamadas ao broker retornam `401 Unauthorized`.

---

## 🟡 PROBLEMAS SÉRIOS — Alta Prioridade (Bloqueia Demo Robusto)

### 9. `PerformanceService.get_portfolio_metrics` retorna sempre valores hardcoded

```python
return {"sharpe_ratio": 1.5, "max_drawdown": 0.02}  # TODO nunca implementado
```

O RiskService usa este valor para calcular `risk_multiplier`. Com Sharpe sempre 1.5, o bot nunca reduz posição por performance degradada. Esta é uma feature de safety crítica.

---

### 10. Sector exposure no `ShadowService` retorna `"General"` para todos os tickers

```python
portfolio.append({"ticker": ..., "size": ..., "sector": "General"})
```

A lógica de cluster exposure (máx 30% por sector) está completamente ineficaz. O bot pode acumular 100% de exposição em Technology sem qualquer aviso.

---

### 11. `execute_trade` usa tamanho fixo de $100 sem considerar capital disponível

```python
target_cash = 100.0   # Simplified for brevity — nunca removido
```

Independentemente do capital na conta, o bot calcula sempre $100 por par. Ignora totalmente o Kelly Criterion e o `risk_multiplier` calculado.

---

### 12. Pairs inicializados com `ARBITRAGE_PAIRS` mesmo em `DEV_MODE`

**Ficheiro:** `src/monitor.py`, linha 80

```python
pairs_to_init = settings.ARBITRAGE_PAIRS  # Ignora DEV_MODE e CRYPTO_TEST_PAIRS
```

Mesmo com `DEV_MODE=true`, o bot tenta inicializar 21 pares NYSE/NASDAQ fora do horário de mercado, falha em obter preços, e acaba sem nenhum par activo. `CRYPTO_TEST_PAIRS` é configurado mas nunca usado.

---

### 13. `get_symbol_metadata` — Fetch on demand sem cache, endpoint incorreto

```python
url = f"{self.base_url}/instruments"  # Busca TODOS os instrumentos a cada ordem
```

Cada chamada a `place_market_order` ou `place_value_order` faz um GET de toda a lista de instrumentos (potencialmente milhares de registos) para extrair 1 ticker. Causará erros 429 rapidamente.

---

### 14. `data_service.stream_realtime_data` — Polygon WebSocket nunca é iniciado

A versão gratuita do Polygon não suporta streaming de stocks em tempo real. Além disso, o `WebSocketClient` nunca é iniciado no loop principal. O bot depende exclusivamente de polling com `yfinance` (15s de delay), o que é inadequado para arbitragem.

---

### 15. Kalman Filter — `calculate_spread_and_zscore` divide pelo `innovation_variance` do update anterior, não do atual

O Z-score usa `self.innovation_variance` que é atualizado no `update()` do mesmo tick. Isto está correto conceptualmente, mas a sessão de `calculate_spread_and_zscore` chamada depois do `update()` usa a variância do tick atual, não uma janela histórica rolante — o Z-score pode ser muito volátil nas primeiras iterações.

---

## 🟠 GAPS DE FUNCIONALIDADE — MVP Incompleto

### 16. Exit Strategy — Nunca implementada

O bot abre posições (mock) mas **nunca fecha**. Não existe lógica de:
- Stop-loss sintético
- Take-profit quando z-score reverte a zero
- Timeout de posição
- Fechamento por `DEGRADED_MODE`

Um bot de arbitragem sem exits é apenas metade de um sistema.

---

### 17. `DEV_MODE` — Lógica de redirecionamento de tickers nunca aplicada na execução

`DEV_EXECUTION_TICKERS` está definido (`BTC-USD → MSFT`, etc.) mas `execute_trade` não o usa. Em DEV_MODE, o bot tentaria negociar `BTC-USD` na Trading 212, que não suporta esse ticker no formato yfinance.

---

### 18. Position sizing — Nunca conectado ao Kelly/Risk

O `KellyCalculator` e o `RiskService.validate_trade` existem mas nunca são chamados no fluxo principal de `monitor.execute_trade`. O sizing é sempre $100 fixo.

---

### 19. `LIVE_CAPITAL_DANGER=false` mas ausência de validações de startup em Demo

Com `LIVE_CAPITAL_DANGER=false`, os baselines de entropia L2 não são verificados. Para Demo, isto é aceitável, mas o bot deveria verificar:
- Conectividade com Redis e PostgreSQL antes de iniciar
- Autenticação T212 bem-sucedida (test_connection)
- Pelo menos 1 par activo antes de entrar no loop

---

### 20. Profit/Loss não é calculado nem reportado

`persistence_service.close_trade` aceita `pnl` como argumento mas nunca é chamado (não existe lógica de fecho de posição). O dashboard mostra `daily_profit: 0.0` permanentemente.

---

## 🟢 O QUE ESTÁ BEM IMPLEMENTADO (Não tocar)

| Componente | Status |
|---|---|
| Kalman Filter (matemática) | ✅ Correto, com NaN/Inf guard |
| Cointegration check (OLS + ADF com `add_constant`) | ✅ Correto |
| Redis Kalman warm-start | ✅ Implementado |
| Idempotency no `ExecutionServiceClient` (gRPC) | ✅ Redis SET NX |
| Idempotency no `BrokerageService` (`clientOrderId` UUID) | ✅ Implementado |
| Circuit Breaker (DEGRADED_MODE) | ✅ Implementado |
| Rate limit cache (5s TTL, threading.Lock) | ✅ Implementado |
| Exponential backoff no DataService (tenacity) | ✅ Implementado |
| Transaction recovery após timeout (BrokerageService) | ✅ Implementado |
| Slippage guard (limitPrice ±1%) | ✅ Implementado |
| Friction check para micro-trades | ✅ Implementado |
| Tick size rounding (quantityIncrement) | ✅ Implementado |
| ReconciliationSweeper (zombie locks) | ✅ Implementado |
| DRIP Safety cap (min dividend, available_cash) | ✅ Implementado |
| EU UCITS hedge mapping + bypass alert | ✅ Implementado |
| Telegram approval flow (InlineKeyboard + Future) | ✅ Implementado |
| Dashboard SSE + WebSocket | ✅ Implementado |
| SEC Worker daemon | ✅ Implementado |
| gRPC client_order_id (feature 027) | ✅ Implementado |

---

## 📋 ROADMAP PARA MVP DEMO FUNCIONAL

### Sprint A — Bugs Críticos (2-3 días)

| # | Tarefa | Ficheiro |
|---|---|---|
| A1 | Mover broadcast `SEC_AGENT` **depois** de `score_a`/`score_b` serem definidos | `orchestrator.py` |
| A2 | Implementar `execute_trade` real (chamar `brokerage_service`) | `monitor.py` |
| A3 | Adicionar `from typing import List` no `dashboard_service.py` | `dashboard_service.py` |
| A4 | Corrigir `await` em chamadas async no `notification_service.py` | `notification_service.py` |
| A5 | Corrigir auth T212 para `Authorization: {KEY}` (não Basic Auth) | `brokerage_service.py` |
| A6 | Criar `src/models/persistence.py` com `PersistenceManager` (wrapper SQLite) | `[NEW FILE]` |
| A7 | Implementar `risk_service.get_all_sector_exposures()` | `risk_service.py` |

### Sprint B — Fluxo Funcional (3-5 días)

| # | Tarefa | Ficheiro |
|---|---|---|
| B1 | Usar `CRYPTO_TEST_PAIRS` quando `DEV_MODE=true` na inicialização | `monitor.py` |
| B2 | Aplicar `DEV_EXECUTION_TICKERS` no `execute_trade` | `monitor.py` |
| B3 | Integrar Kelly + `risk_multiplier` no sizing de posição | `monitor.py` |
| B4 | Implementar stop-loss / take-profit (z-score reverte para ±0.5) | `monitor.py` |
| B5 | Cache de metadados de instrumentos (buscar 1x ao startup) | `brokerage_service.py` |
| B6 | Sector lookup real no `ShadowService` (usar `PAIR_SECTORS` do config) | `shadow_service.py` |

### Sprint C — Observabilidade e Robustez (2-3 días)

| # | Tarefa | Ficheiro |
|---|---|---|
| C1 | Implementar `PerformanceService.get_portfolio_metrics` real via SQL | `performance_service.py` |
| C2 | Verificação de startup: conexão T212, Redis, PostgreSQL | `monitor.py` |
| C3 | Relatório de PnL real no dashboard | `dashboard_service.py` |
| C4 | Adicionar `test_connection()` no startup e alertar via Telegram se falhar | `monitor.py` |

### Sprint D — Validação Demo (1-2 días)

| # | Tarefa |
|---|---|
| D1 | Correr `docker-compose -f docker-compose.backend.yml up` e validar todos os serviços healthy |
| D2 | Activar `DEV_MODE=true`, `T212_DEMO=true`, `DRY_RUN=true` |
| D3 | Observar pelo menos 1 ciclo completo: preços → Kalman → sinal → Telegram → aprovação → ordem Demo |
| D4 | Verificar no dashboard T212 Demo que a ordem aparece com ClientOrderId correto |
| D5 | Verificar que após reverter z-score, a posição é fechada |

---

## ⚡ Prioridade Imediata (Fix Agora)

Se tiveres de escolher apenas **3 coisas** para corrigir hoje:

1. **Bug #1** — `NameError` no Orchestrator (nenhum sinal passa sequer pela análise AI)
2. **Bug #8** — T212 Auth errada (nenhuma chamada ao broker funciona)
3. **Bug #2** — `execute_trade` mock (aprovações Telegram não executam nada)

Estes 3 bugs em conjunto significam que **o bot não faz literalmente nada de útil** mesmo funcionando.
