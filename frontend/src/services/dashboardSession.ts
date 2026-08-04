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
    if (
      typeof parsed.sessionToken !== 'string'
      || !parsed.sessionToken
      || typeof parsed.expiresAt !== 'string'
      || !parsed.expiresAt
    ) {
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
      actor: typeof parsed.actor === 'string' ? parsed.actor : undefined,
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
  // 403 is only auth when the security token itself was rejected — not OTP/2FA config gates.
  if (
    err instanceof ApiError
    && err.status === 403
    && /invalid dashboard token/i.test(message)
  ) {
    return true;
  }
  return /dashboard session|dashboard login is required|invalid dashboard token/i.test(message);
}

/** Strip auth secrets from the address bar before React paints (referrer / screenshot leak surface). */
export function scrubAuthQueryParamsFromUrl() {
  if (typeof window === 'undefined') return;
  try {
    const currentUrl = new URL(window.location.href);
    if (!currentUrl.searchParams.has('token') && !currentUrl.searchParams.has('session')) return;
    currentUrl.searchParams.delete('token');
    currentUrl.searchParams.delete('session');
    window.history.replaceState({}, document.title, currentUrl.toString());
  } catch {
    // History API can be unavailable in some embedded contexts.
  }
}
