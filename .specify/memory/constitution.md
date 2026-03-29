<!--
  SYNC IMPACT REPORT
  - Version change: 1.0.0 → 1.1.0
  - List of modified principles:
    - I. Horário de Operação Estrito → II. Safety-Critical (Horário NYSE)
    - II. Gestão de Risco e Capital → V. Human-in-the-loop (Aprovação Telegram)
    - III. Neutralidade de Mercado → I. Library-First (Bibliotecas Independentes)
    - IV. Segurança da API → III. Atomicidade (Transação Única)
    - V. Validação Estratégica via IA → IV. State Management (Persistência Local)
  - Added sections: None
  - Removed sections: None
  - Templates requiring updates:
    - .specify/templates/plan-template.md (✅ verified)
    - .specify/templates/spec-template.md (✅ verified)
    - .specify/templates/tasks-template.md (✅ verified)
  - Follow-up TODOs:
    - TODO(TELEGRAM_THRESHOLD): Definir o valor limite para aprovação via Telegram.
-->

# Project Arbitrage-AI Constitution

## Core Principles

### I. Library-First
A lógica de cálculo estatístico e os wrappers da API devem ser bibliotecas independentes. Isto garante que a inteligência do bot e a comunicação com a corretora possam ser testadas, versionadas e reutilizadas sem depender da infraestrutura de orquestração ou do servidor MCP.

### II. Safety-Critical
O bot nunca deve operar fora do horário regular da NYSE (14:30-21:00 WET). Operações fora deste intervalo (pre-market ou after-hours) são estritamente proibidas para evitar spreads alargados e volatilidade extrema que invalidam modelos estatísticos de reversão à média.

### III. Atomicidade
Operações de swap (venda de ativo A e compra simultânea de ativo B) devem ser tratadas como uma transação lógica única. O sistema deve garantir que ambas as pernas da arbitragem sejam executadas ou que o estado seja revertido/compensado para evitar exposição direcional não planejada.

### IV. State Management
O estado das "Pies Virtuais" (alocações e pesos) deve ser persistido localmente e reconciliado com a corretora a cada ciclo de execução. A persistência local é a fonte da verdade para a estratégia, enquanto a reconciliação garante que a realidade da corretora reflete o estado pretendido.

### V. Human-in-the-loop
Transações que excedam um valor limite pré-definido (threshold) exigem aprovação explícita via Telegram antes de serem enviadas para a corretora. Este mecanismo serve como um "circuit breaker" físico contra anomalias algorítmicas ou condições de mercado imprevistas.

## Padrões Técnicos e Integração

O sistema utiliza o framework FastMCP para expor ferramentas de dados e corretagem. A integração com a Trading 212 é feita via API Pública oficial. A lógica de "Pies Virtuais" é implementada no nível da aplicação para permitir granularidade total sobre os ativos sem as limitações das ferramentas nativas da corretora.

## Workflow de Desenvolvimento e Conformidade

O desenvolvimento segue o ciclo Spec -> Plan -> Task -> Implement. Toda mudança técnica deve ser validada contra estes princípios (Constitution Check). Violações, especialmente nos princípios de Segurança (Safety-Critical) e Atomicidade, impedem a promoção do código para produção.

## Governance

Esta constituição é o documento supremo do "Project Arbitrage-AI". Alterações seguem o versionamento semântico:
- MAJOR: Remoção ou alteração profunda de princípios.
- MINOR: Adição de novos princípios ou clarificações materiais.
- PATCH: Correções de texto e ajustes não semânticos.

**Version**: 1.1.0 | **Ratified**: 2026-03-27 | **Last Amended**: 2026-03-27
