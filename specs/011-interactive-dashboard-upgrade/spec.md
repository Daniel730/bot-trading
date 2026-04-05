# Feature Specification: Interactive Dashboard Upgrade

**Feature Branch**: `011-interactive-dashboard-upgrade`  
**Created**: 2026-04-04  
**Status**: Draft  
**Input**: User request: "the dashboard is too simple. It should take real data from the bot. Let's create a simple application for the frontend for it to look even better, the bot as well. The interface should be more interactive and should show the real data that the bot is working. Revenue, investments, sell, possible sell, possible buy, production of profit"

## User Scenarios & Testing

### User Story 1 - Real-Time Dashboard (Priority: P1)

Como investidor, eu quero ver em tempo real os dados de performance do bot (investimentos totais, lucro acumulado, sinais ativos), para acompanhar as operações sem precisar consultar logs ou o banco de dados diretamente.

**Acceptance Scenarios**:
1. **Given** o bot está rodando, **When** eu acesso a URL do dashboard, **Then** eu vejo o valor atual do "Total Investido" e "Lucro Produzido" atualizado dinamicamente.
2. **Given** um novo sinal de arbitragem detetado, **When** o bot inicia a análise, **Then** o dashboard exibe o sinal como "Analyzing" e mostra o Z-score em tempo real.

### User Story 2 - Visual Trading Signals (Priority: P1)

Como investidor, eu quero uma visualização clara de sinais de "Possible Buy" e "Possible Sell", para entender o que o bot está monitorando e por que decisões estão sendo tomadas.

**Acceptance Scenarios**:
1. **Given** o sistema de monitoramento de pares, **When** um Z-score ultrapassa o limiar, **Then** o par é destacado no frontend como uma oportunidade ativa.

## Requirements

### Functional Requirements
- **FR-001**: O dashboard MUST consumir dados em tempo real do `DashboardService` via SSE (Server-Sent Events) ou WebSockets.
- **FR-002**: O sistema MUST exibir métricas de portfólio: Investimento Total, Cash Disponível, Lucro/Prejuízo Realizado e Não Realizado.
- **FR-003**: O frontend MUST ser uma aplicação reativa (React ou Vanilla JS moderna) com design responsivo e interativo.
- **FR-004**: O sistema MUST exibir o log de decisões (Thought Journal) das últimas operações diretamente na interface.
- **FR-005**: O dashboard MUST incluir gráficos de performance (ex: curva de equity, distribuição por setor).

### Non-Functional Requirements
- **NFR-001**: Latência de atualização de dados no dashboard < 2s.
- **NFR-002**: O frontend não deve exigir autenticação complexa (inicialmente protegido por ambiente/VPN ou simples token).
- **NFR-003**: Estilização moderna e "clean" (Dark mode por padrão).

## Success Criteria
- **SC-001**: O dashboard mostra dados consistentes com o banco de dados SQLite.
- **SC-002**: O dashboard carrega em menos de 3 segundos em conexões padrão.
