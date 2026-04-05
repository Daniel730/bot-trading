# Feature Specification: Embedded Telegram Terminal

**Feature Branch**: `012-embedded-telegram-terminal`  
**Created**: 2026-04-04  
**Status**: Draft  
**Input**: User request: "is there a way for the interface to have a button so when the user clicks it opens a modal or a new card anywhere in the app that opens a direct integrated telegram direct to the chatbot conversation. That way the user can skip the 'goes to telegram anywhere to validate'. The user also can do that, but having the option to do so inside the dashboard is better"

## User Scenarios & Testing

### User Story 1 - One-Click Approval (Priority: P1)

Como investidor, eu quero aprovar sinais de trade diretamente do dashboard, para economizar tempo e manter o foco na estação de comando sem precisar alternar para o aplicativo do Telegram.

**Acceptance Scenarios**:
1. **Given** um sinal aguardando aprovação, **When** eu clico no botão "OPEN TERMINAL" no dashboard, **Then** um modal ou card é exibido com a interface de chat vinculada ao bot.
2. **Given** a interface de chat aberta, **When** eu clico no botão "APPROVE" gerado pelo bot, **Then** o comando é enviado ao bot e o monitor processa a execução.

## Requirements

### Functional Requirements
- **FR-001**: O sistema MUST fornecer um botão de acesso rápido à conversa com o bot.
- **FR-002**: O dashboard MUST exibir um modal flutuante ou card fixo contendo a interface do Telegram.
- **FR-003**: O sistema SHOULD permitir a integração via `tg://` URL scheme ou Telegram Web Widget (se aplicável).
- **FR-004**: O sistema MUST permitir que o usuário envie comandos básicos (`/status`, `/stop`, `/approve`) diretamente da interface integrada.

### Non-Functional Requirements
- **NFR-001**: A integração não deve comprometer a segurança das chaves de API do bot.
- **NFR-002**: O tempo de resposta entre o clique no dashboard e a visualização da resposta do bot no Telegram deve ser < 1s.

## Success Criteria
- **SC-001**: O usuário consegue completar um ciclo de aprovação de trade sem trocar de aba no navegador ou abrir o app mobile.
- **SC-002**: O modal de terminal é responsivo e funciona em diferentes resoluções.
