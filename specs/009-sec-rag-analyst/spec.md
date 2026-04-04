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
  - **FR-001.1**: Profundidade: Analisar apenas o documento mais recente (10-K ou 10-Q).
- **FR-002**: O sistema MUST implementar uma pipeline RAG (Retrieval-Augmented Generation) para processar secções específicas de documentos longos.
  - **FR-002.1**: Secções obrigatórias: Item 1A (Risk Factors) e Item 7 (MD&A) para 10-K; Part II Item 1A e Part I Item 2 para 10-Q.
- **FR-003**: O `NewsAnalyst` MUST ser evoluído para `FundamentalAnalyst`, utilizando os filings como fonte de verdade primária.
- **FR-004**: O sistema MUST persistir os resumos dos riscos detetados no Thought Journal e implementar um VETO automático (Confiança Final = 0) se o 'Structural Integrity Score' for inferior a 40/100.
  - **FR-004.1**: Rubrica de Pontuação: 
    - 0-30: Risco crítico imediato (falência, fraude, litígio material sem mitigação).
    - 31-40: Riscos estruturais elevados (quebra de covenants, dependência extrema de um cliente em declínio).
    - 41-70: Riscos operacionais normais com mitigação documentada.
    - 71-100: Estrutura sólida, riscos genéricos ou imateriais.
- **FR-005**: O sistema MUST implementar um fallback automático para News Analysis caso a API da SEC esteja indisponível, o ticker não possua filings recentes (< 1 ano), ou para ativos sem filings (ADRs/Recent IPOs).
  - **FR-005.1**: Em caso de fallback, o Orchestrator deve ignorar o 'Structural Integrity Score' e basear a decisão no 'Sentiment Score' e 'Z-score' originais.
- **FR-006 (Robustness)**: O sistema MUST utilizar uma arquitetura de "Adversarial Debate" (Prosecutor vs. Defender) para validação de riscos críticos.
  - **FR-006.1**: Isolamento: O Prosecutor e Defender devem ser instanciados com system prompts mutuamente exclusivos e sem visibilidade do raciocínio um do outro até a fase de julgamento.
  - **FR-006.2**: Debate Inconclusivo: Se a diferença de confiança entre Prosecutor e Defender for < 10% e o score estiver na zona cinzenta (35-45), o sistema deve assumir viés conservador e aplicar o VETO.

### Non-Functional Requirements (NFR)

- **NFR-001 (Resilience)**: O sistema MUST implementar retry com backoff exponencial para erros de rate limit (429) da SEC (limite de 10 req/s).
- **NFR-002 (Performance)**: O processamento total (retrieval + extraction + debate) MUST ser < 20s. Se o documento for excessivamente grande (> 500k tokens), o sistema deve extrair apenas os primeiros 100k tokens das secções alvo para evitar estouro de contexto do Gemini.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Redução de "False Positives" em 40% face ao baseline de News-only (Validado via `Backtest Benchmark` de 10 casos reais de falência/litígio).
- **SC-002**: Tempo de processamento RAG (retrieval + inference) < 20s.
- **SC-003**: 100% de precisão na extração do CIK a partir de tickers (Validado contra ground-truth de 50 tickers).
- **SC-004**: O sistema MUST disparar um 'Sector Freeze' em < 5s após a deteção de riscos correlacionados em 3+ ativos do mesmo cluster.

## Assumptions

- Utilização da biblioteca `sec-api` ou scraping direto da SEC EDGAR (respeitando rate limits).
- Os embeddings serão processados via Gemini API (nativa) para minimizar latência.
