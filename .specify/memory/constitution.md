<!--
  SYNC IMPACT REPORT
  - Version change: 1.1.0 → 2.0.0
  - List of modified principles:
    - I. Library-First → II. Racionalidade Mecânica (Redefinido: Foco em dados estruturados e MCP)
    - II. Safety-Critical → IV. Operação Estrita (Mantido e Reforçado: Horário NYSE/NASDAQ)
    - III. Atomicidade → V. Virtual-Pie First (Evoluído: Gestão programática acima da API)
    - IV. State Management → V. Virtual-Pie First (Consolidado: Persistência e Reconciliação)
    - V. Human-in-the-loop → I. Prioridade à Preservação de Capital (Elevado: Veto de Risco e Kelly Criterion)
  - Added sections: III. Auditabilidade Total (Thought Journal + SHAP/LIME)
  - Removed sections: None
  - Templates requiring updates:
    - .specify/templates/plan-template.md (✅ updated)
    - .specify/templates/spec-template.md (✅ updated)
    - .specify/templates/tasks-template.md (✅ updated)
  - Follow-up TODOs: None
-->

# Project Arbitrage-Elite-Python Constitution

## Core Principles

### I. Prioridade à Preservação de Capital
A preservação de capital é o mandato supremo. O sistema possui uma camada de "Percepção de Risco" que precede qualquer lógica de negociação e detém poder de veto absoluto sobre sinais de execução. O dimensionamento de posição deve seguir rigorosamente o Critério de Kelly Fracionário (máximo 0.25x), com limites rígidos de 2% de risco por transação e 10% de drawdown total do portfólio.

### II. Racionalidade Mecânica
Toda decisão operacional deve ser fundamentada em dados estruturados (ex: Z-score de cointegração) e validada por lógica semântica via LLM para filtrar ruídos macroeconômicos. A conectividade com fontes de dados e corretoras deve ser padronizada via Model Context Protocol (MCP), utilizando ferramentas determinísticas para cálculos financeiros críticos em vez de confiar na aritmética interna de modelos de linguagem.

### III. Auditabilidade Total
O sistema opera sob o regime de "Caixa Branca". Toda transação, tentativa ou veto deve gerar um log de raciocínio persistente (Thought Journal). As decisões do motor de IA devem ser acompanhadas de justificativas técnicas auditáveis (ex: SHAP ou LIME values) que identifiquem os fatores de influência, permitindo a reconstituição completa do processo decisório.

### IV. Operação Estrita
O bot está autorizado a operar exclusivamente durante o horário regular de pregão da NYSE/NASDAQ (tipicamente 14:30 às 21:00 WET), respeitando feriados oficiais dos mercados americanos. A operação fora deste intervalo é estritamente proibida para mitigar riscos de baixa liquidez, spreads anormais e volatilidade de fechamento/abertura que invalidam modelos de reversão à média.

### V. Virtual-Pie First
A gestão de ativos deve priorizar uma abordagem de "Virtual-Pie", tratando as alocações como estruturas programáticas independentes das limitações nativas da API da Trading 212. O bot é responsável pelo reequilíbrio dinâmico, cálculo de pesos e reconciliação de estado, garantindo granularidade e controle total sobre a execução da estratégia de arbitragem.

## Padrões Técnicos e Integração

O sistema utiliza o framework FastMCP para orquestração de ferramentas e dados. A arquitetura deve garantir a separação estrita entre a aquisição de dados, a lógica de estratégia estatística e o motor de execução. A persistência de dados (sinais, logs e estado) deve ser feita em banco de dados robusto (ex: SQLite ou PostgreSQL) para garantir a integridade histórica.

## Workflow de Desenvolvimento e Conformidade

Todo desenvolvimento segue o ciclo SDD (Specification-Driven Development). Nenhuma funcionalidade é implementada sem que sua especificação e plano de tarefas estejam alinhados com esta constituição. Violações dos princípios de Risco (Princípio I) e Operação (Princípio IV) são consideradas falhas críticas e impedem qualquer execução em ambiente real.

## Governance

Esta constituição é o documento governante do "Project Arbitrage-Elite-Python". Alterações seguem o versionamento semântico:
- MAJOR: Mudanças estruturais ou remoção de princípios fundamentais.
- MINOR: Adição de novos princípios ou clarificações materiais.
- PATCH: Ajustes gramaticais ou de formatação sem alteração de sentido.

**Version**: 2.0.0 | **Ratified**: 2026-03-27 | **Last Amended**: 2026-03-29
