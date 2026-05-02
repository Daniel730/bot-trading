import { ApiError, type AuthSession } from './api';

const DASHBOARD_SESSION_STORAGE_KEY = 'alpha-arbitrage.dashboardSession';

export interface StoredDashboardSession {
  sessionToken: string;
  expiresAt: string;
  actor?: string;
}

export function clearStoredDashboardSession() {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(DASHBOARD_SESSION_STORAGE_KEY);
  } catch {
    // Storage can be disabled by browser privacy settings.
  }
}

export function readStoredDashboardSession(): StoredDashboardSession | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(DASHBOARD_SESSION_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredDashboardSession>;
    if (!parsed.sessionToken || !parsed.expiresAt) {
      clearStoredDashboardSession();
      return null;
    }
    const expiresAtMs = Date.parse(parsed.expiresAt);
    if (!Number.isFinite(expiresAtMs) || expiresAtMs <= Date.now()) {
      clearStoredDashboardSession();
      return null;
    }
    return {
      sessionToken: parsed.sessionToken,
      expiresAt: parsed.expiresAt,
      actor: parsed.actor,
    };
  } catch {
    clearStoredDashboardSession();
    return null;
  }
}

export function writeStoredDashboardSession(session: AuthSession) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(
      DASHBOARD_SESSION_STORAGE_KEY,
      JSON.stringify({
        sessionToken: session.session_token,
        expiresAt: session.expires_at,
        actor: session.actor,
      } satisfies StoredDashboardSession),
    );
  } catch {
    // The in-memory session still works for this tab.
  }
}

export function isDashboardAuthError(err: unknown) {
  const message = err instanceof Error ? err.message : String(err ?? '');
  if (err instanceof ApiError && err.status === 401) return true;
  return /dashboard session|dashboard login is required|invalid dashboard token/i.test(message);
}
