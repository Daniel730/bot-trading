# Feature Specification: Multi-Agent Arbitrage Engine

**Feature Branch**: `005-arbitrage-multiagent-engine`  
**Created**: 2026-03-29  
**Status**: Draft  
**Input**: User description: "Criar a especificação para o motor de arbitragem multiagente. 1. Monitorizar pares de concorrentes via Cointegração e Z-score dinâmico. 2. Implementar debate adversarial entre agentes (Bull vs Bear) para validar trocas. 3. Integrar analista de notícias via Gemini para detetar 'Event Spikes' (earnings/SEC filings). 4. Implementar sistema de notificações Telegram com botões de aprovação manual para trades > $X. 5. Modo 'Shadow Trading' para simulação em tempo real sem capital real para validação de confiança."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Shadow Strategy Validation (Priority: P1)

Como gestor de risco, eu quero executar a estratégia de arbitragem em tempo real sem arriscar capital real (Shadow Trading), para que eu possa validar a confiança no modelo estatístico e no tempo de execução antes de ativar o trading live.

**Why this priority**: Crucial para cumprir o Princípio I (Preservação de Capital) da constituição, permitindo validação empírica sem risco.

**Independent Test**: Pode ser testado verificando se o sistema gera sinais, processa debates e "executa" ordens em um ledger virtual local, comparando os resultados com os preços de mercado em tempo real.

**Acceptance Scenarios**:

1. **Given** o modo 'Shadow Trading' está ativo, **When** um sinal de arbitragem é validado, **Then** o sistema deve registrar a execução no ledger virtual e persistir o log de raciocínio.
2. **Given** uma posição simulada aberta, **When** o spread converge para a média, **Then** o sistema deve fechar a posição virtualmente e calcular o PnL hipotético incluindo taxas simuladas.

---

### User Story 2 - Automated Statistical Monitoring (Priority: P1)

Como analista quantitativo, eu quero que o sistema monitorize pares de ativos cointegrados continuamente usando Z-score dinâmico, para identificar oportunidades de reversão à média assim que o spread se desviar significativamente.

**Why this priority**: É a base funcional do bot; sem a detecção de sinais estatísticos, não há operação.

**Independent Test**: Pode ser testado alimentando dados históricos/em tempo real conhecidos por terem desvios de Z-score e verificando se o sistema detecta os gatilhos corretamente.

**Acceptance Scenarios**:

1. **Given** um par de ativos configurado, **When** o Z-score do spread ultrapassa o limite configurado (ex: ±2.0), **Then** um sinal de alerta de arbitragem deve ser gerado para o Decision Core.
2. **Given** um par monitorado, **When** o teste de cointegração (ADF test) falha (p-valor > 0.05), **Then** o par deve ser marcado como 'instável' e novas operações devem ser suspensas.

---

### User Story 3 - Adversarial Signal Validation (Priority: P2)

Como operador de trading, eu quero que cada sinal estatístico seja debatido entre agentes 'Bull' e 'Bear' e filtrado por um analista de notícias, para reduzir falsos positivos causados por eventos fundamentais ou sentimento irracional.

**Why this priority**: Garante a "Racionalidade Mecânica" (Princípio II) e a "Auditabilidade Total" (Princípio III), elevando a qualidade dos sinais.

**Independent Test**: Inserir um sinal técnico válido durante um evento de notícias negativo (ex: earnings miss simulado) e verificar se o debate resulta em um veto ou redução de confiança.

**Acceptance Scenarios**:

1. **Given** um sinal técnico de entrada, **When** o agente 'Bear' apresenta contra-argumentos baseados em volume ou momentum, **Then** o sistema deve reduzir a probabilidade de vitória (P) usada no cálculo de Kelly.
2. **Given** um sinal detectado, **When** o analista de notícias Gemini identifica um "Event Spike" (ex: Earnings Report iminente), **Then** o sinal deve ser bloqueado para evitar volatilidade binária.

---

### User Story 4 - High-Value Trade Approval (Priority: P3)

Como investidor, eu quero receber notificações no Telegram com botões de aprovação manual para transações que excedam um valor limite ($X), para manter o controle final sobre grandes alocações de capital.

**Why this priority**: Implementa o mecanismo de "Human-in-the-loop" para gestão de risco excepcional.

**Independent Test**: Simular um trade que ultrapassa o threshold e verificar se a execução fica pendente até a recepção do comando 'Aprovar' via Telegram.

**Acceptance Scenarios**:

1. **Given** um sinal aprovado pelo Decision Core, **When** o valor da posição excede $100, **Then** a ordem deve ser retida e uma notificação interativa deve ser enviada ao Telegram.
2. **Given** uma ordem pendente de aprovação, **When** o usuário clica em 'Rejeitar', **Then** a transação deve ser cancelada e o motivo registrado no Thought Journal.

### Edge Cases

- **Contradição Irresolúvel**: O que acontece se os agentes Bull e Bear tiverem níveis de confiança idênticos e opostos? (Default: Veto por precaução).
- **Staleness de Dados**: Como o sistema lida com a interrupção parcial do feed de notícias ou preços durante um trade aberto? (Default: Fechamento de emergência se o atraso exceder 30s).
- **Falha de Conetividade Telegram**: Se o bot não conseguir enviar a notificação de aprovação manual em 60s, a ordem deve ser cancelada automaticamente.
- **Divergência de Cointegração Súbita**: Se a cointegração quebrar logo após a entrada, o sistema deve priorizar a saída rápida mesmo com prejuízo mínimo.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema MUST calcular dinamicamente a cointegração e o Z-score para um universo configurável de 20 pares de ativos iniciais.
- **FR-002**: O Decision Core MUST implementar um debate entre pelo menos dois agentes LLM (Bullish vs Bearish) antes de cada trade.
- **FR-003**: O analista de notícias MUST consumir feeds em tempo real (via Gemini/News MCP) para identificar eventos de alta relevância (earnings, SEC filings).
- **FR-004**: O sistema MUST persistir cada etapa do raciocínio (Thought Journal) em um banco de dados auditável, incluindo as métricas SHAP/LIME da decisão.
- **FR-005**: O modo Shadow Trading MUST replicar todas as etapas de uma transação real, exceto o envio da ordem para a corretora live.
- **FR-006**: O bot Telegram MUST suportar botões `inline` para aprovação/rejeição de ordens e consulta de status do portfólio virtual.
- **FR-007**: O sistema MUST respeitar os horários de operação configurados (NYSE/NASDAQ) conforme a Constituição do projeto.
- **FR-008**: O dimensionamento de posição MUST ser calculado via Critério de Kelly Fracionário baseado na confiança gerada pelo debate.

### Key Entities

- **Arbitrage Pair**: Par de ativos (ex: KO vs PEP) com métricas de cointegração, hedge ratio e status de monitoramento.
- **Signal**: Registro de um desvio de Z-score, contendo timestamp, valores brutos e contexto de mercado.
- **Thought Journal**: Registro persistente do debate entre agentes, análise de notícias e justificativas técnicas da decisão.
- **Virtual Ledger**: Registro de transações (Shadow ou Live) para gestão de "Virtual Pies" e acompanhamento de PnL.
- **Event Spike**: Alerta de notícia ou evento macro que impacta a validade de um sinal estatístico.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: O sistema deve processar o debate adversarial e a análise de notícias em menos de 10 segundos após a detecção do sinal técnico.
- **SC-002**: Redução de pelo menos 30% nos trades em "regimes de mercado voláteis" comparado a um bot puramente estatístico (medido via Shadow Trading).
- **SC-003**: 100% das transações devem possuir um registro completo no Thought Journal antes da execução (Live ou Shadow).
- **SC-004**: Latência de notificação Telegram para aprovação manual deve ser inferior a 5 segundos (excluindo tempo de resposta do usuário).
- **SC-005**: O desvio de preço entre a execução no Shadow Trading e a cotação real de mercado deve ser inferior a 0.2% (slippage simulado).

## Assumptions

- O usuário fornecerá chaves de API válidas para o Gemini (analista de notícias) e para a corretora (via MCP).
- O ambiente de execução possui persistência local confiável (SQLite/PostgreSQL).
- O servidor de notificações Telegram possui conectividade estável para recepção de webhooks/polling.
- O universo de pares monitorados será definido em arquivo de configuração.
