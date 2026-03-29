# Feature Specification: 24/7 Crypto Development Mode

**Feature Branch**: `006-crypto-dev-testing`  
**Created**: 2026-03-29  
**Status**: Draft  
**Input**: User description: "/speckit.plan for development purposes, find a market that works 24/7 and weekends just to check if everything is working as it should be"

## User Scenarios & Testing

### User Story 1 - 24/7 Connectivity Test (Priority: P1)

Como desenvolvedor, eu quero que o bot suporte a monitorização de um mercado 24/7 (Cripto), para que eu possa validar a conetividade, o fluxo de dados e a lógica de agentes durante o fim de semana ou fora do horário da NYSE.

**Why this priority**: Essencial para depuração e validação contínua sem depender da abertura dos mercados tradicionais.

**Independent Test**: Ativar o modo 'Crypto-Dev' e verificar se o bot inicia o fluxo de dados para pares como BTC/USD e executa o ciclo de decisão.

**Acceptance Scenarios**:

1. **Given** o modo 'Crypto-Dev' está ativo, **When** é fim de semana, **Then** o bot NÃO deve entrar em modo 'Market closed' e deve continuar a monitorização.
2. **Given** um sinal de Z-score detetado em um par Cripto, **When** o orquestrador é chamado, **Then** os agentes Bull/Bear devem responder com base nos dados cripto.

## Requirements

### Functional Requirements

- **FR-001**: O sistema MUST permitir a configuração de um modo `DEVELOPMENT_MODE` que ignore as restrições de horário da NYSE.
- **FR-002**: O `DataService` MUST suportar tickers de criptomoedas (ex: BTC-USD, ETH-USD) via yfinance/Polygon.
- **FR-003**: O `ArbitrageMonitor` MUST aceitar uma lista de pares de teste que operam 24/7.

## Success Criteria

### Measurable Outcomes

- **SC-001**: O bot deve manter conetividade WebSocket/REST estável por mais de 1 hora durante o fim de semana.
- **SC-002**: Tempo de resposta do orquestrador para dados cripto deve ser < 10s.

## Assumptions

- O par de teste para arbitragem será simulado (ex: BTC-USD vs ETH-USD como "proxies") apenas para validar o fluxo técnico, uma vez que a cointegração real pode não ser forte o suficiente para lucro, mas serve para teste de código.
- As chaves de API existentes (Polygon/Gemini) suportam dados de Cripto.
