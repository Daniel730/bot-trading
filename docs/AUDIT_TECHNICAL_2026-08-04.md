# Relatório de Auditoria Técnica — Alpha Arbitrage

**Data:** 2026-08-04  
**Âmbito:** código atual do monorepo (`master` + branch de soak `cursor/full-day-audit-f7a8`)  
**Método:** leitura adversarial do código real (não da documentação). Sem correções aplicadas neste passo.  
**Postura:** tentar quebrar garantias de capital, modo, auth e ledger.

---

## Tabela-resumo por severidade

| Severidade | Qtd | IDs |
|---|---|---|
| Critical | 2 | F-001, F-002 |
| High | 4 | F-003, F-004, F-005, F-006 |
| Medium | 5 | F-007, F-008, F-009, F-010, F-011 |
| Low | 2 | F-012, F-013 |

---

## Checklist de invariantes P0 / P1

| Invariante | Veredicto | Confiança | Notas |
|---|---|---|---|
| Fonte única de modo (SHADOW / BROKER_PAPER / LIVE) | **Parcialmente OK** | Verificado | `settings.execution_lane` + `resolve_execution_lane`; `opening_shadow` usa só `PAPER_TRADING` (não o lane resolver) — ver F-003 |
| Auto-aprovação alinhada com o mesmo critério de routing | **Parcialmente OK** | Verificado | `should_auto_approve_trades` = PAPER ∨ broker_paper; path LIVE tem atalho `APPROVAL_THRESHOLD` — ver F-001 |
| `LIVE_CAPITAL_DANGER` em todos os despachos Alpaca real | **Parcialmente OK** | Verificado | Obrigatório no boot se `PAPER_TRADING=false`; **não** revalidado em cada `place_*` — ver F-004 |
| Secrets `POSTGRES_PASSWORD` / `DASHBOARD_TOKEN` hard-fail | **OK** | Verificado | `validate_secrets` rejeita vazio/default |
| Provider ≠ ALPACA falha no arranque | **OK** | Verificado | `_validate_supported_brokerage_provider` |
| Java `DRY_RUN=false` recusa boot | **OK** | Verificado | `Application.main` + `LiveBroker` stub |
| T212 / Web3 inatingíveis | **OK** | Verificado | Provider force-ALPACA; `web3_enabled=False`; BrokerageService só Alpaca |
| Dashboard auth fail-closed (Telegram **ou** TOTP) | **OK** | Verificado | Sem OTP + Telegram down → 503; sem fallback só-token |
| Sessão/2FA em controlos sensíveis | **Parcialmente OK** | Verificado | Keys sensíveis exigem 2FA; `APPROVAL_THRESHOLD` **não** é sensitive — F-001 |
| `signal_id` preservado reasoning→ledger→close | **OK (caminhos principais)** | Verificado parcialmente | Shadow propaga `signal_id`; broker usa `{signal_id}-A/B`; closes usam metadata de lane |
| `execution_lane` / `is_shadow` em troca de modo | **OK** | Verificado | `close_uses_broker` + mixed-lane guard no open |
| Idempotência de ordens (client_order_id) | **OK (happy path)** | Verificado parcialmente | Derivado de `signal_id`; reconciliação de duplicate; crash mid-submit → NEEDS_MANUAL_RECONCILIATION |
| Ensemble / dados não fail-open em LIVE | **Parcialmente OK** | Verificado | Fundamentos fail-closed se `PAPER_TRADING=false`; shadow fail-open por design; timeouts → DEGRADED |
| Whale INACTIVE sem side-effects | **OK** | Verificado | Stub `active=False`; efeitos gated |
| FastMCP sem escrita de execução | **OK (execução)** | Verificado | `execute_trade` sempre rejeita; auth token opcional — F-008 |
| Circuit-breaker de perda diária / drawdown agregado | **FALHA** | Verificado | `MAX_DRAWDOWN` não enforçado; `daily_halted` morto — F-002 |
| Limites de exposição / open book | **OK** | Verificado | `MAX_OPEN_PAIRS`, `MAX_PAIR_GROSS`, `MAX_PORTFOLIO_GROSS`, shared-leg, sector |
| Aprovação humana: timeout → deny | **OK** | Verificado | `wait_for` 300s → `False` |
| Venue só via `BrokerageService.get_venue()` | **OK (path ativo)** | Verificado parcialmente | Dispatcher Alpaca-only; sem grep de venue hardcode no hot path de execução |

---

## Achados

### [F-001] Severidade: Critical  
**Categoria:** K / A  
**Localização:** `src/services/notification_service.py:662-666`; `src/services/dashboard_service.py:1056`; callers em `src/monitor.py:2296-2300` usam `force_manual=True`  
**Descrição:** Em modo LIVE (não auto-approve), se Telegram estiver **ligado** e `force_manual=False` (default da API), qualquer trade com `trade_value <= APPROVAL_THRESHOLD` (default **100.0**) é **auto-aprovado sem clique humano**. `APPROVAL_THRESHOLD` é editável no dashboard com `sensitive: False` (só sessão, sem step-up 2FA).  
**Evidência:**
```python
# notification_service.request_approval — após o gate should_auto_approve
if not force_manual and trade_value is not None and trade_value <= settings.APPROVAL_THRESHOLD:
    self._schedule_paper_notify(...)
    return True
```
O path principal do monitor passa `force_manual=True` hoje, mas o default da função e o knob não-sensitive criam um landmine de capital real.  
**Impacto:** Ordem LIVE abaixo do threshold sem aprovação explícita, se algum caller (atual futuro/regressão) omitir `force_manual=True`, ou se o flag for removido por engano.  
**Confiança:** Verificado (código); Suspeito quanto a exploit imediato nos callers atuais (só 2 callers, ambos com `force_manual=True`).  
**Recomendação:** Remover o atalho de threshold em LIVE; ou exigir `force_manual=True` sempre fora de `should_auto_approve_trades`; marcar `APPROVAL_THRESHOLD` como sensitive + 2FA; adicionar teste que LIVE+Telegram+`force_manual=False` **nunca** auto-aprova.

---

### [F-002] Severidade: Critical  
**Categoria:** I  
**Localização:** `src/config.py:299` (`MAX_DRAWDOWN`); `src/monitor.py:279` (`daily_halted = False` apenas); `src/services/risk_service.py:317-332` (kill switch **por posição**)  
**Descrição:** Não existe circuit-breaker de **perda diária / drawdown de portefólio** que pare novas entradas. `MAX_DRAWDOWN` está em Settings e é editável no dashboard, mas **não é lido** em nenhum gate de trading. `daily_halted` nunca é posto a `True`. O que existe: (a) `FINANCIAL_KILL_SWITCH_PCT` por posição aberta, (b) `RISK_DRAWDOWN_ZERO_PCT` a escalar tamanho, (c) caps de notional/open pairs.  
**Evidência:** `rg MAX_DRAWDOWN src/` → só definição + UI config; `rg daily_halted` → só inicialização a `False`.  
**Impacto:** Sequência de perdas em LIVE/BROKER_PAPER pode continuar a abrir pares até esgotar caps de notional, sem halt automático diário.  
**Confiança:** Verificado.  
**Recomendação:** Implementar halt diário (PnL do dia ≤ −X% ou −$Y) que seta `operational_status` e bloqueia `execute_trade`; ligar `MAX_DRAWDOWN` a esse gate; testes de integração.

---

### [F-003] Severidade: High  
**Categoria:** A / J  
**Localização:** `src/config.py:980-990`, `1010-1022`; `src/monitor.py:2686-2691`; `src/services/data_service.py:451-455`  
**Descrição:** `DEV_MODE=true` com `PAPER_TRADING=false` **desativa** `is_broker_paper_trading` e força `execution_lane=LIVE`, mesmo que `ALPACA_BASE_URL` seja paper-api. Em paralelo, `DEV_MODE` **randomiza preços** (±1.5%). Combinação `DEV_MODE` + URL live + `LIVE_CAPITAL_DANGER` pode gerar sinais artificiais sobre capital real (ainda com aprovação humana, mas com dados falsos).  
**Evidência:**
```python
# is_broker_paper_trading
if self.PAPER_TRADING or self.DEV_MODE:
    return False
# data_service
if settings.DEV_MODE:
    return value * (1 + random.uniform(-0.015, 0.015))
```
**Impacto:** Confusão de lane (LIVE label em paper-api); pior caso — sinais baseados em preços randomizados aprovados para Alpaca real.  
**Confiança:** Verificado.  
**Recomendação:** Hard-fail se `DEV_MODE and not PAPER_TRADING`; ou forçar shadow quando DEV_MODE; nunca randomizar se endpoint ≠ paper / se `LIVE_CAPITAL_DANGER`.

---

### [F-004] Severidade: High  
**Categoria:** A  
**Localização:** `src/config.py:1082-1083`; `src/services/brokerage/alpaca.py:286+` (sem recheck de lane); hot-reload em `dashboard_service.update_dashboard_config:2012-2015`  
**Descrição:** `LIVE_CAPITAL_DANGER` é exigido no boot/`validate_secrets` quando `PAPER_TRADING=false`, mas **cada** `place_market_order` / `place_value_order` não revalida modo nem `LIVE_CAPITAL_DANGER`. Um hot-reload via dashboard pode alterar `PAPER_TRADING`, `ALPACA_BASE_URL`, `DEV_MODE` em runtime (com 2FA). O mixed-lane guard mitiga opens mistos, mas o broker client já configurado pode enviar para a URL atual sem um “live capital assert” no submit.  
**Impacto:** Janela de configuração inconsistente entre aprovação e submit se settings mudarem mid-flight.  
**Confiança:** Suspeito (caminho de hot-reload verificado; race concreta não reproduzida).  
**Recomendação:** Snapshot atómico `{lane, paper_trading, base_url, auto_approve}` no início de `execute_trade` e revalidar no submit; bloquear mudança de `PAPER_TRADING`/`ALPACA_BASE_URL` com posições abertas.

---

### [F-005] Severidade: High  
**Categoria:** A  
**Localização:** `src/config.py:975-977`  
**Descrição:** Detecção de paper endpoint por **substring**: `"paper-api.alpaca.markets" in url`. Um URL malicioso controlado via env/dashboard (`https://evil.example/paper-api.alpaca.markets`) classificaria o endpoint como paper → `should_auto_approve_trades=True` e `requires_l2_entropy_baselines=False`, enquanto as ordens iriam para o host atacante ou um proxy.  
**Impacto:** Auto-aprovação e skips de gates de live sob classificação errada de endpoint.  
**Confiança:** Verificado (lógica); exploração requer controlo de `ALPACA_BASE_URL` (já sensitive+2FA no dashboard, mas env/file no host não).  
**Recomendação:** Parse de URL (`urlparse`) e comparar `hostname` exacto `paper-api.alpaca.markets` (e allowlist).

---

### [F-006] Severidade: High  
**Categoria:** F / P2  
**Localização:** `src/agents/orchestrator.py:354-378`; soak local 2026-08-04  
**Descrição:** Guard fundamental fail-closed usa `not settings.PAPER_TRADING` — logo **BROKER_PAPER** (`PAPER_TRADING=false`) trata miss SEC como veto (bom). Em **SHADOW**, misses usam `ORCH_FUNDAMENTAL_DEFAULT_SCORE=50` (fail-open por design). Separadamente, na soak yfinance, equities overnight falharam rolling coint a **0.32** vs knob **0.40** — o mesmo knob em bot-server com barras Alpaca passou; risco de admitir/bench inconsistente por fonte de dados.  
**Impacto:** Shadow pode validar com scores neutros; paper-broker em produção depende da qualidade das barras.  
**Confiança:** Verificado.  
**Recomendação:** Documentar explicitamente BROKER_PAPER = fail-closed SEC; não baixar `COINTEGRATION_ROLLING_PASS_RATE` sem soak na **mesma** fonte de dados do deploy.

---

### [F-007] Severidade: Medium  
**Categoria:** E  
**Localização:** `src/monitor.py:2810-2845`, `3064+`  
**Descrição:** Crash entre aprovação e submit de Leg A: no restart, o sinal pode ser reprocessado (novo `signal_id`) se o estado ACTIVE/OPEN não ficou persistido. Crash **após** Leg A submitted com status conhecido: há path `NEEDS_MANUAL_RECONCILIATION` / emergency close. Crash com `status=unknown` + `requires_reconciliation` bloqueia Leg B (bom). Duplicados no broker mitigados por `client_order_id={signal_id}-A`.  
**Impacto:** Possível re-entrada lógica após crash pré-ledger; baixo risco de double-fill no broker se o mesmo `signal_id` for reutilizado (hoje gera-se UUID novo por sinal).  
**Confiança:** Verificado parcialmente (código; sem fault-injection neste âmbito).  
**Recomendação:** Persistir “APPROVED_PENDING_EXECUTION” com `signal_id` antes do primeiro `place_*`; no boot, reconciliar esses rows.

---

### [F-008] Severidade: Medium  
**Categoria:** G  
**Localização:** `src/mcp_server.py:63-78`, `117-147`  
**Descrição:** `execute_trade` MCP rejeita sempre (OK). `MCP_TOOL_TOKEN` é **opcional** — se unset, tools read Redis sem auth (mitigado por bind loopback). `get_market_data` pode ler preços do shadow book.  
**Impacto:** Em host partilhado ou publish acidental de `:8000`, leitura de estado sem token.  
**Confiança:** Verificado.  
**Recomendação:** Exigir `MCP_TOOL_TOKEN` não-vazio em non-DEV; teste de compose.

---

### [F-009] Severidade: Medium  
**Categoria:** D / cobertura  
**Localização:** closes legacy sem metadata — `execution_lane.close_uses_broker:84-92`  
**Descrição:** Rows antigas **sem** `execution_lane`/`is_shadow` fazem fallback para `not paper_trading` atual. Um flip para LIVE com orphans untagged pode tentar closes no broker para fills que eram shadow (ou o inverso).  
**Impacto:** Close errado pós-migração / hot-reload.  
**Confiança:** Verificado (código); Suspeito em DBs já migradas com backfill.  
**Recomendação:** Fail-closed se open signal sem lane explícita; exigir backfill antes de LIVE.

---

### [F-010] Severidade: Medium  
**Categoria:** B  
**Localização:** `src/services/dashboard_service.py:2645-2678` (`/api/approvals/{id}/approve|reject`)  
**Descrição:** Endpoints de aprovação de trade usam `verify_token` (sessão), **sem** `require_step_up_2fa`. Com sessão roubada (XSS/local), um atacante aprova LIVE.  
**Impacto:** Bypass de segundo fator na ação mais sensível.  
**Confiança:** Verificado.  
**Recomendação:** Step-up TOTP em approve/reject quando 2FA enabled e modo ≠ SHADOW.

---

### [F-011] Severidade: Medium  
**Categoria:** C / docs vs código  
**Localização:** `frontend/README.md` (menciona fallback token-only em docs históricas); código `_login` fail-closed  
**Descrição:** Documentação legada do frontend ainda pode sugerir login só com token; o código exige OTP ou challenge Telegram. Divergência docs↔código (já notada em AGENTS.md).  
**Impacto:** Operadores confusos; não é bypass.  
**Confiança:** Verificado.  
**Recomendação:** Corrigir README frontend; não tratar docs como fonte de verdade.

---

### [F-012] Severidade: Low  
**Categoria:** H  
**Localização:** `src/config.py:139-140`, `323-336` (campos T212/WEB3 ainda no Settings)  
**Descrição:** Credenciais/knobs T212/WEB3 permanecem no modelo Settings embora o provider os rejeite. Código legado em `legacy/` e campos mortos aumentam superfície de confusão. Runtime ativo força Alpaca.  
**Impacto:** Baixo se validate_provider se mantiver.  
**Confiança:** Verificado.  
**Recomendação:** Remover ou isolar knobs legacy; teste CI que importa `BrokerageService` e garante só Alpaca.

---

### [F-013] Severidade: Low  
**Categoria:** P3 / cobertura  
**Localização:** `tests/unit/test_should_auto_approve_trades.py` (bom); ausência de teste LIVE+`force_manual=False`+threshold  
**Descrição:** Cobertura forte para auto-approve paper e fail-closed sem Telegram; **falta** teste regressão para F-001 (LIVE nunca auto-aprova por threshold).  
**Impacto:** Regressão silenciosa possível.  
**Confiança:** Verificado.  
**Recomendação:** Adicionar teste vermelho para o cenário F-001 antes de corrigir.

---

## Caminhos traçados (resumo)

### SHADOW (`PAPER_TRADING=true`)
Sinal → orchestrator → `request_approval` → `should_auto_approve_trades=True` → `shadow_service.execute_simulated_trade(signal_id=…)` → ledger `execution_lane=SHADOW`.  
**OK** se secrets válidos.

### BROKER_PAPER (`PAPER_TRADING=false`, paper-api, `LIVE_CAPITAL_DANGER=true`)
Auto-approve via `is_broker_paper_trading` → `place_value_order` com `client_order_id={signal_id}-A/B`. Entropy L2 skipped. Fundamentos fail-closed (porque `PAPER_TRADING=false`).

### LIVE (api.alpaca.markets)
`should_auto_approve=False` → Telegram/dashboard com timeout deny; **exceto** landmine F-001 se `force_manual=False`. Entropy baselines obrigatórias se `LIVE_CAPITAL_DANGER`.

### Java sidecar
`DRY_RUN=false` → `IllegalStateException` no boot; `LiveBroker` lança se chamado. Não é path default do monitor.

### FastMCP
`execute_trade` sempre `rejected`; read Redis only.

---

## Divergências docs ↔ código (amostra)

| Doc | Afirma | Código |
|---|---|---|
| `frontend/README` (legado) | Login token-only | Fail-closed OTP/Telegram (`_login`) |
| `docs/tofix.md` (parcialmente stale) | Vários itens “working tree” | Verificar data; vários já merged |
| `AGENTS.md` | Placeholder Alpaca OK em paper | Verdadeiro para **SHADOW**; BROKER_PAPER precisa keys válidas (confirmado na soak local: unauthorized → 0 pares antes do skip de asset gate) |

---

## Notas da soak local (contexto, não achados de código)

- Keys Alpaca injetadas: **unauthorized** → soak em SHADOW.
- RSS ~330 MiB estável; 0 ERROR pós-fix de cash poll.
- BTC/ETH & ETH/SOL frequentemente `extreme_kalman_beta` (|β|>25).
- Equities GOOGL/GOOG, UNH/ELV, VLO/MPC: rolling pass_rate **0.32** vs threshold **0.40** (yfinance).

---

## Prioridade sugerida de remediação (sem aplicar aqui)

1. **F-001** — neutralizar auto-approve por threshold em LIVE + teste.  
2. **F-002** — circuit-breaker diário ligado a `MAX_DRAWDOWN` / PnL.  
3. **F-003** — isolar `DEV_MODE` de qualquer path broker/live.  
4. **F-005** — hostname allowlist Alpaca.  
5. **F-010** — step-up 2FA em approve de trades.  
6. Restantes Medium/Low conforme capacidade.

---

## Status de remediação (mesmo dia, pós-auditoria)

| ID | Estado | Notas |
|---|---|---|
| F-001 | **Corrigido** | Removido atalho LIVE por `APPROVAL_THRESHOLD`; knob marcado `sensitive`; `/api/settings` exige 2FA; teste de regressão. |
| F-002 | **Corrigido** | `capital_halt_service` + gate no início de `execute_trade` (fail-closed); persiste `DAILY_LOSS_HALT` / `MAX_DRAWDOWN_HALT`. |
| F-003 | **Corrigido** | `validate_secrets` rejeita `DEV_MODE` sem `PAPER_TRADING`; randomização de preço só se ambos. |
| F-005 | **Corrigido** | `is_alpaca_paper_endpoint` via hostname exact match (`urlparse`). |
| F-008 | **Corrigido** | MCP rejeita se `MCP_TOOL_TOKEN` ausente/placeholder. |
| F-009 | **Corrigido** | Untagged legacy nunca inventa close broker. |
| F-010 | **Corrigido** | Approve/reject exigem step-up 2FA; UI pede OTP em 403. |
| F-004 / F-006 / F-007 / F-011+ | **Pendente** | Fora deste lote (snapshot atômico, crash recovery status, etc.). |

*Relatório original preservado acima; esta secção regista o follow-up de correções.*
