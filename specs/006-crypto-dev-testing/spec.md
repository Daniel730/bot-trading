# Feature Specification: 24/7 Crypto Development Mode

**Feature Branch**: `006-crypto-dev-testing`  
**Created**: 2026-03-29  
**Status**: Draft  
**Input**: User description: "/speckit.plan for development purposes, find a market that works 24/7 and weekends just to check if everything is working as it should be"

## Clarifications

### Session 2026-03-31
- Q: Salvaguarda de Segurança para o `DEV_MODE` → A: Imprimir um aviso crítico (`WARNING`) nos logs a cada 5 minutos relembrando o utilizador.
- Q: Validação da Estabilidade (SC-001) → A: Instrumentação de código para registar "Conetividade: 100%" nos logs a cada ciclo.

## User Scenarios & Testing

### User Story 1 - 24/7 Connectivity Test (Priority: P1)

Como desenvolvedor, eu quero que o bot suporte a monitorização de um mercado 24/7, para que eu possa validar a conetividade, o fluxo de dados e a lógica de agentes durante o fim de semana ou fora do horário da NYSE.

**Why this priority**: Essencial para depuração e validação contínua sem depender da abertura dos mercados tradicionais.

**Independent Test**: Ativar o modo `DEV_MODE=true` e verificar se o bot inicia o fluxo de dados para pares Cripto (via yfinance) e tenta execução de ordens com tickers Stocks compatíveis com a T212 (ex: KO, MA).

**Acceptance Scenarios**:

1. **Given** o `DEV_MODE` está ativo, **When** é fim de semana, **Then** o bot NÃO deve entrar em modo 'Market closed' e deve continuar a monitorização.
2. **Given** um sinal de Z-score detetado em um par de teste, **When** o orquestrador é chamado, **Then** os agentes Bull/Bear devem responder com base nos dados.

## Requirements

### Functional Requirements

- **FR-001**: O sistema MUST permitir a configuração de um modo `DEV_MODE` que ignore as restrições de horário da NYSE.
- **FR-002**: O `DataService` MUST suportar tickers de criptomoedas (ex: BTC-USD, ETH-USD) via yfinance/Polygon para fluxo de dados.
- **FR-003**: O `ArbitrageMonitor` MUST aceitar uma lista de pares de teste (Cripto para dados, Stocks para execução T212) que operam ou permitem submissão 24/7.
- **FR-004**: O sistema MUST emitir um log de aviso (`WARNING`) proeminente a cada 5 minutos enquanto o `DEV_MODE` estiver ativo, utilizando um banner ASCII para visibilidade.
- **FR-005 (Safety)**: Se `DEV_MODE=true`, todas as execuções devem ser forçadas para `is_shadow=True` por padrão, a menos que uma flag de bypass explícita seja fornecida.
- **FR-006 (Operations)**: Alterações no estado de `DEV_MODE` no ficheiro `.env` requerem o reinício completo do bot para terem efeito.
- **FR-007 (Error Handling)**: Em caso de falha de dados do `yfinance`, o bot deve registar um erro `CRITICAL` e manter o estado anterior por 3 ciclos antes de suspender a monitorização.

## Success Criteria

### Measurable Outcomes

- **SC-001**: O bot deve manter conetividade WebSocket/REST estável por mais de 1 hora durante o fim de semana (Definido como 100% de sucesso nas últimas 60 iterações do loop).
- **SC-002**: Tempo de resposta do orquestrador para dados cripto deve ser < 10s (Medido desde a receção do sinal até à decisão final do orquestrador).

## Assumptions

- O par de teste para arbitragem será simulado (ex: BTC-USD vs ETH-USD como "proxies") apenas para validar o fluxo técnico, uma vez que a cointegração real pode não ser forte o suficiente para lucro, mas serve para teste de código.
- As chaves de API existentes (Polygon/Gemini) suportam dados de Cripto.
