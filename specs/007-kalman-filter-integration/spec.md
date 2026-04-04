# Feature Specification: Dynamic Arbitrage with Kalman Filter

**Feature Branch**: `007-kalman-filter-integration`  
**Created**: 2026-03-31  
**Status**: Draft  
**Input**: User request: "Improve the bot to an even more efficient bot"

## User Scenarios & Testing

### User Story 1 - Real-time Hedge Ratio Tracking (Priority: P1)

Como investidor quantitativo, eu quero que o sistema ajuste o hedge ratio (`beta`) dinamicamente com cada novo dado de mercado, para que o spread permaneça relevante mesmo durante mudanças graduais na correlação dos ativos.

**Why this priority**: Crucial para o Princípio II (Racionalidade Mecânica). Elimina o erro de "beta drift" que invalida modelos OLS estáticos em janelas longas.

**Independent Test**: Alimentar o sistema com dados onde a correlação entre dois ativos muda deliberadamente (ex: KO e PEP mudando de um rácio de 1:1 para 1:1.2) e verificar se o filtro de Kalman converge para o novo rácio em menos de 10 iterações.

**Acceptance Scenarios**:

1. **Given** um par monitorado, **When** um novo preço é recebido, **Then** o estado do filtro de Kalman deve ser atualizado e um novo `hedge_ratio` calculado.
2. **Given** um estado inicial, **When** o preço do Ativo B se move 5% e o Ativo A se move 6%, **Then** o beta deve ajustar-se recursivamente para refletir a nova sensibilidade.

---

### User Story 2 - Resilient Z-Score Generation (Priority: P1)

Como trader, eu quero que o Z-score seja calculado com base no spread dinâmico do Kalman Filter, para reduzir sinais falsos gerados por anomalias temporárias de curta duração.

**Why this priority**: Reduz o custo operacional e o risco de capital (Princípio I) ao filtrar "ruído" que o OLS simples confundiria com uma oportunidade de arbitragem.

**Independent Test**: Comparar o sinal gerado por um Z-score OLS estático vs um Z-score Kalman durante um pico de volatilidade isolado e verificar se o Kalman é mais "suave" e evita entradas precipitadas.

**Acceptance Scenarios**:

1. **Given** um novo par de dados, **When** o Z-score excede 2.5, **Then** o sistema deve garantir que o desvio é estatisticamente significativo em relação à variância do erro do filtro (Q-matrix).

## Requirements

### Functional Requirements

- **FR-001**: O sistema MUST implementar um Filtro de Kalman recursivo (State-Space Model) para estimar o intercepto e o declive (beta) do spread.
- **FR-002**: O `ArbitrageService` MUST atualizar o estado do filtro a cada ciclo de polling (12-15s) sem recalcular toda a janela histórica.
- **FR-003**: O sistema MUST utilizar a variância do erro de medição do filtro para normalizar o Z-score.
- **FR-004**: O sistema MUST permitir a configuração dos parâmetros `delta` (taxa de adaptação) e `V` (ruído de medição) via `.env`.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Redução de 20% na volatilidade do Z-score em comparação com o modelo OLS de janela fixa (medido via desvio padrão do sinal).
- **SC-002**: Convergência para novos regimes de correlação (rácio de preço) 5x mais rápida que uma média móvel de 30 dias.
- **SC-003**: 100% das atualizações de estado do Kalman devem ocorrer em < 50ms (baixa latência computacional).

## Assumptions

- O `pykalman` ou uma implementação `numpy` customizada será usada para evitar overhead de bibliotecas pesadas.
- O filtro operará em "Online Learning Mode" (um dado por vez).
