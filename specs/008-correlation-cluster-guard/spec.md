# Feature Specification: Correlation Cluster Guard

**Feature Branch**: `008-correlation-cluster-guard`  
**Created**: 2026-03-31  
**Status**: Draft  
**Input**: User request: "Improve the bot to an even more efficient bot"

## User Scenarios & Testing

### User Story 1 - Cluster Veto (Priority: P1)

Como gestor de risco, eu quero que o sistema bloqueie novos sinais de entrada se o portfólio já estiver exposto a ativos altamente correlacionados (ex: mesmo setor), para evitar perdas catastróficas em eventos macro setoriais.

**Why this priority**: Mandato supremo do Princípio I (Preservação de Capital). Evita a "ilusão de diversificação" onde o bot abre 5 trades que dependem do mesmo fator (ex: taxas de juro).

**Independent Test**: Simular uma posição aberta em JPM/BAC e tentar abrir uma nova em GS/MS. O sistema deve emitir um veto automático por "Cluster Overlap: Financials".

**Acceptance Scenarios**:

1. **Given** uma posição aberta em um setor (ex: Tech), **When** um novo sinal surge para outro par no mesmo setor, **Then** o sistema deve reduzir a confiança (ou vetar) baseado no limite de concentração configurado.
2. **Given** múltiplos sinais simultâneos, **When** o sistema avalia a execução, **Then** ele deve priorizar o sinal com maior Z-score ou menor correlação com o portfólio atual.

## Requirements

### Functional Requirements

- **FR-001**: O sistema MUST permitir a atribuição de "Sectores" ou "Clusters" a cada `TradingPair` via `src/config.py`.
- **FR-002**: O `RiskService` MUST calcular a correlação histórica (ou simples sobreposição de sector) entre sinais ativos e posições abertas.
- **FR-003**: O sistema MUST implementar um limite configurável de "Concentração Máxima por Sector" (ex: 30% do portfólio).
- **FR-004**: O orquestrador Gemini MUST receber a informação de "Portfólio Overlap" como contexto para a sua decisão final.

## Success Criteria

### Measurable Outcomes

- **SC-001**: 100% dos trades abertos devem respeitar o limite de concentração setorial.
- **SC-002**: Redução do "Drawdown Máximo Simulado" em cenários de stress setorial (ex: crise bancária) em pelo menos 15%.
- **SC-003**: Tempo de verificação de cluster < 100ms.

## Assumptions

- O mapeamento de sectores será manual inicialmente no arquivo de configuração.
- O sistema considera posições em "Shadow" e "Live" para o cálculo de exposição.
