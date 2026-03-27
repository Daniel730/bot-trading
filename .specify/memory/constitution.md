<!--
SYNC IMPACT REPORT
- Version change: [TEMPLATE] → 1.0.0
- List of modified principles:
  - [PRINCIPLE_1_NAME] → I. Horário de Operação Estrito
  - [PRINCIPLE_2_NAME] → II. Gestão de Risco e Capital
  - [PRINCIPLE_3_NAME] → III. Neutralidade de Mercado
  - [PRINCIPLE_4_NAME] → IV. Segurança da API
  - [PRINCIPLE_5_NAME] → V. Validação Estratégica via IA
- Added sections:
  - Padrões Técnicos e Integração
  - Workflow de Desenvolvimento e Conformidade
- Removed sections: None
- Templates requiring updates:
  - .specify/templates/plan-template.md (✅ updated/verified)
  - .specify/templates/spec-template.md (✅ updated/verified)
  - .specify/templates/tasks-template.md (✅ updated/verified)
- Follow-up TODOs:
  - TODO(MAX_ALLOCATION_PERCENTAGE): Definir o valor exato de X% na configuração do sistema.
-->

# Bot Trading (Arbitragem Estatística) Constitution

## Core Principles

### I. Horário de Operação Estrito
O sistema só tem permissão para enviar ordens de compra/venda entre as 14:30 e as 21:00 (Fuso de Portugal), correspondendo ao horário regular de mercado (RTH) de Nova Iorque. Nenhuma ordem deve ser enviada em Extended Hours. Este princípio garante que as operações ocorram em momentos de maior liquidez e menor volatilidade atípica.

### II. Gestão de Risco e Capital
O bot deve utilizar um modelo de alocação de "Reserva Estratégica". Nunca deve alocar mais de 10% do saldo livre da conta numa única operação de arbitragem. O valor exato de X deve ser configurado via variáveis de ambiente e respeitado rigorosamente pelo orquestrador de ordens.

### III. Neutralidade de Mercado
A estratégia baseia-se em Pairs Trading (Arbitragem Estatística). A tomada de decisão deve ignorar a tendência direcional do mercado e focar-se exclusivamente no spread relativo entre os ativos cointegrados. O objetivo é lucrar com a reversão à média, independentemente do movimento geral do índice.

### IV. Segurança da API
As chaves de API da Trading 212 e tokens de notificação devem ser geridos via variáveis de ambiente (.env), nunca via código ou logs. O sistema deve falhar imediatamente se as credenciais necessárias não forem encontradas no ambiente de execução.

### V. Validação Estratégica via IA
Toda oportunidade identificada estatisticamente (ex: Z-score > 2.0) deve ser validada contextualmente via Gemini CLI antes da execução. A IA deve analisar notícias recentes para confirmar que o desvio não é resultado de uma mudança fundamental (ex: falência, fraude, mudança de liderança) que invalide a tese de reversão.

## Padrões Técnicos e Integração

O sistema utiliza o framework FastMCP para expor ferramentas de dados e corretagem ao Gemini CLI. A integração com a Trading 212 é feita via API Pública oficial. Como contingência à depreciação de endpoints de "Pies", o sistema implementa a lógica de "Pies Virtuais" no nível da aplicação, gerenciando pesos e rebalanceamentos de forma autônoma.

## Workflow de Desenvolvimento e Conformidade

O desenvolvimento segue rigorosamente o ciclo de Spec -> Plan -> Task -> Implement. Toda proposta técnica deve passar por um "Constitution Check" documentado no plano de implementação. Violações dos princípios (especialmente horário e risco) são impeditivas para a implementação.

## Governance

Esta constituição é o documento supremo do projeto. Alterações requerem um incremento de versão seguindo as regras de versionamento semântico (MAJOR para mudanças estruturais, MINOR para novos princípios, PATCH para correções). O cumprimento destes princípios deve ser verificado automaticamente durante o ciclo de decisão do bot (Pre-Trade Check).

**Version**: 1.0.0 | **Ratified**: 2026-03-27 | **Last Amended**: 2026-03-27
