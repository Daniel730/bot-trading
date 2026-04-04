# Research: Embedded Telegram Terminal

## Decision: Custom "Dashboard Terminal" Bridge

Instead of a native Telegram iframe (which is blocked by security headers) or a 3rd-party widget (which introduces privacy/cost concerns), we will implement a custom **Dashboard Terminal** that mirrors the bot's communication.

### Rationale
1. **Security**: Bypasses `X-Frame-Options: DENY` by using our own backend as a proxy.
2. **UX**: Provides a "one-click" experience within a modal, satisfying the requirement for an integrated feel.
3. **Control**: Allows us to customize the UI to match the "ARBI ELITE" cyberpunk aesthetic of the dashboard.
4. **Auditability**: Every command sent via the dashboard terminal can be easily logged to the `Thought Journal` (Principle III).

### Alternatives Considered

| Alternative | Rationale for Rejection |
|-------------|-------------------------|
| **Iframe `web.telegram.org`** | Blocked by Telegram's security headers. Cannot be bypassed without a proxy that violates ToS. |
| **Telegram Login Widget** | Only handles authentication. Does not provide a chat interface. |
| **Intergram (Open Source)** | Requires a 3rd party middleman bot. Adds complexity and potential latency. |
| **Native Popup (`window.open`)** | Disjointed UX. Feels like a separate app, not "integrated" into the dashboard. |

### Technical Implementation Details

#### 1. Backend Integration (`src/services/dashboard_service.py`)
- **New Endpoint**: `POST /api/terminal/command`
  - Body: `{"command": "string"}`
  - Logic: Forwards the command to `NotificationService` for processing.
- **SSE Enhancement**:
  - Add a `messages` array to the `DashboardState`.
  - When the bot sends a message to Telegram, it should also call `dashboard_state.add_bot_message(text)`.

#### 2. Notification Service (`src/services/notification_service.py`)
- Add a method `handle_dashboard_command(command: str)` that parses commands just like a Telegram user would.
- Ensure that `request_approval` messages are also sent to the `DashboardState` so they appear in the terminal.

#### 3. Frontend Integration (`dashboard/`)
- **Modal System**: Create a CSS/JS modal that overlays the center stage.
- **Terminal UI**:
  - Scrollable message area with distinct styles for "BOT" and "SYSTEM".
  - Text input field with auto-focus.
  - Quick-action buttons (e.g., `/status`, `/exposure`).
- **Trigger**: Add a neon "OPEN_TERMINAL" button in the dashboard header or header's system meta area.

## Needs Clarification Resolving
- **Embed Telegram chat?**: No, we will mirror it via a custom bridge.
- **Dashboard technology?**: Static HTML/Vanilla JS/CSS + FastAPI Backend.
- **Latency?**: SSE + Direct API calls will ensure < 200ms interaction latency.
