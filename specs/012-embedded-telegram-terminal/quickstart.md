# Quickstart: Integrated Terminal

## Setup
1. **Enable Dashboard**: Ensure `DASHBOARD_TOKEN` is set in your `.env`.
2. **Restart Bot**: Run `python src/monitor.py`.
3. **Open Dashboard**: Visit `http://localhost:8080/?token=your-token`.

## Usage
1. Click the **NEON TERMINAL** button (located in the header).
2. The terminal modal will open, displaying the live conversation with ARBI ELITE.
3. Use the input box to send commands:
   - `/status`: Get current bot state.
   - `/exposure`: Check sector limits.
   - `/approve [id]`: Approve a pending trade (if a signal is awaiting HITL).
4. For trade approvals, click the "Approve" button that appears directly in the terminal message.

## Verification
- Sent commands should appear in the `journal-log` on the dashboard footer.
- The same messages should be reflected in your Telegram app (Bi-directional).
