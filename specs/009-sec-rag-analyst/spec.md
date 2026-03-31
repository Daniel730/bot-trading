# Feature Specification: Agentic SEC RAG Analyst

**Feature Branch**: `009-sec-rag-analyst`  
**Created**: 2026-03-31  
**Status**: Draft  
**Input**: User request: "Improve the bot to an even more efficient bot"

## User Scenarios & Testing

### User Story 1 - Structural Risk Detection (Priority: P1)

Como investidor, eu quero que o bot analise os documentos 10-K/10-Q mais recentes de cada ativo quando um sinal de arbitragem for detetado, para identificar se a divergência de preço é justificada por riscos fundamentais (ex: litígios, dívida, quebra de contratos).

**Why this priority**: Mandato do Princípio II (Racionalidade Mecânica). Transforma a validação de "ruído" (notícias) em "factos fundamentais" (filings legais).

**Independent Test**: Simular um sinal de arbitragem para uma empresa com um "Risk Factor" conhecido no seu último 10-Q (ex: perda de um cliente principal) e verificar se o Gemini identifica este fator e recomenda "NO-GO".

**Acceptance Scenarios**:

1. **Given** um sinal de Z-score válido, **When** o bot consulta a API da SEC, **Then** ele deve extrair as secções de "Risk Factors" e "Management's Discussion" para análise RAG.
2. **Given** múltiplos documentos, **When** o agente analisa o contexto, **Then** ele deve emitir uma pontuação de "Structural Integrity" (0-100).

## Requirements

### Functional Requirements

- **FR-001**: O sistema MUST integrar com a API SEC EDGAR para buscar filings recentes por ticker (CIK mapping).
- **FR-002**: O sistema MUST implementar uma pipeline RAG (Retrieval-Augmented Generation) para processar secções específicas de documentos longos.
- **FR-003**: O `NewsAnalyst` MUST ser evoluído para `FundamentalAnalyst`, utilizando os filings como fonte de verdade primária.
- **FR-004**: O sistema MUST persistir os resumos dos riscos detetados no Thought Journal.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Redução de "False Positives" em sinais de divergência estrutural em 40% (comparado com análise de notícias simples).
- **SC-002**: Tempo de processamento RAG (retrieval + inference) < 20s.
- **SC-003**: 100% de precisão na extração do CIK (Central Index Key) a partir dos tickers de mercado.

## Assumptions

- Utilização da biblioteca `sec-api` ou scraping direto da SEC EDGAR (respeitando rate limits).
- Os embeddings serão processados via Gemini API (nativa) para minimizar latência.
