/**
 * Tests for src/services/dashboardSession.ts
 *
 * Covers:
 *  - clearStoredDashboardSession: removes key from localStorage
 *  - readStoredDashboardSession: returns null for missing/invalid/expired sessions, valid session object otherwise
 *  - writeStoredDashboardSession: serialises AuthSession to localStorage with correct keys
 *  - isDashboardAuthError: detects ApiError 401, message patterns, and non-auth errors
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// We import ApiError directly so we can construct real instances in tests.
// Mock the api module so that getRuntimeApiBase (which accesses import.meta.env)
// does not cause issues in the test environment, while still exporting ApiError.
vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api')>();
  return {
    ...actual,
  };
});

import {
  clearStoredDashboardSession,
  isDashboardAuthError,
  readStoredDashboardSession,
  writeStoredDashboardSession,
} from './dashboardSession';
import { ApiError } from './api';

const STORAGE_KEY = 'alpha-arbitrage.dashboardSession';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function futureIso(offsetMs = 60_000): string {
  return new Date(Date.now() + offsetMs).toISOString();
}

function pastIso(offsetMs = 60_000): string {
  return new Date(Date.now() - offsetMs).toISOString();
}

function storeRaw(value: string) {
  window.localStorage.setItem(STORAGE_KEY, value);
}

// ---------------------------------------------------------------------------
// clearStoredDashboardSession
// ---------------------------------------------------------------------------

describe('clearStoredDashboardSession', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it('removes the session key from localStorage', () => {
    storeRaw(JSON.stringify({ sessionToken: 'tok', expiresAt: futureIso() }));
    clearStoredDashboardSession();
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it('does not throw when key does not exist', () => {
    expect(() => clearStoredDashboardSession()).not.toThrow();
  });

  it('silently swallows localStorage errors', () => {
    vi.spyOn(window.localStorage, 'removeItem').mockImplementation(() => {
      throw new Error('storage disabled');
    });
    expect(() => clearStoredDashboardSession()).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// readStoredDashboardSession
// ---------------------------------------------------------------------------

describe('readStoredDashboardSession', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it('returns null when localStorage is empty', () => {
    expect(readStoredDashboardSession()).toBeNull();
  });

  it('returns a valid session with all fields', () => {
    const expiresAt = futureIso();
    storeRaw(JSON.stringify({ sessionToken: 'tok123', expiresAt, actor: 'admin' }));
    const result = readStoredDashboardSession();
    expect(result).toEqual({ sessionToken: 'tok123', expiresAt, actor: 'admin' });
  });

  it('returns a valid session when actor is absent', () => {
    const expiresAt = futureIso();
    storeRaw(JSON.stringify({ sessionToken: 'tok123', expiresAt }));
    const result = readStoredDashboardSession();
    expect(result?.sessionToken).toBe('tok123');
    expect(result?.actor).toBeUndefined();
  });

  it('returns null and clears storage when sessionToken is missing', () => {
    storeRaw(JSON.stringify({ expiresAt: futureIso() }));
    expect(readStoredDashboardSession()).toBeNull();
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it('returns null and clears storage when expiresAt is missing', () => {
    storeRaw(JSON.stringify({ sessionToken: 'tok' }));
    expect(readStoredDashboardSession()).toBeNull();
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it('returns null and clears storage when session is expired', () => {
    storeRaw(JSON.stringify({ sessionToken: 'tok', expiresAt: pastIso() }));
    expect(readStoredDashboardSession()).toBeNull();
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it('returns null and clears storage when expiresAt is invalid date string', () => {
    storeRaw(JSON.stringify({ sessionToken: 'tok', expiresAt: 'not-a-date' }));
    expect(readStoredDashboardSession()).toBeNull();
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it('returns null and clears storage when raw value is invalid JSON', () => {
    storeRaw('not-json{{');
    expect(readStoredDashboardSession()).toBeNull();
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it('returns null and clears storage when raw value is empty string', () => {
    storeRaw('');
    expect(readStoredDashboardSession()).toBeNull();
  });

  it('silently handles localStorage.getItem throwing', () => {
    vi.spyOn(window.localStorage, 'getItem').mockImplementation(() => {
      throw new Error('storage error');
    });
    expect(readStoredDashboardSession()).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// writeStoredDashboardSession
// ---------------------------------------------------------------------------

describe('writeStoredDashboardSession', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it('writes session_token as sessionToken', () => {
    writeStoredDashboardSession({
      session_token: 'my-token',
      expires_at: futureIso(),
      actor: 'user1',
    } as any);
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const parsed = JSON.parse(raw!);
    expect(parsed.sessionToken).toBe('my-token');
  });

  it('writes expires_at as expiresAt', () => {
    const expiry = futureIso();
    writeStoredDashboardSession({
      session_token: 'tok',
      expires_at: expiry,
      actor: undefined,
    } as any);
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const parsed = JSON.parse(raw!);
    expect(parsed.expiresAt).toBe(expiry);
  });

  it('writes actor field when present', () => {
    writeStoredDashboardSession({
      session_token: 'tok',
      expires_at: futureIso(),
      actor: 'admin',
    } as any);
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const parsed = JSON.parse(raw!);
    expect(parsed.actor).toBe('admin');
  });

  it('written session can be read back by readStoredDashboardSession', () => {
    const expiry = futureIso();
    writeStoredDashboardSession({
      session_token: 'roundtrip-tok',
      expires_at: expiry,
      actor: 'roundtrip',
    } as any);
    const session = readStoredDashboardSession();
    expect(session).toEqual({ sessionToken: 'roundtrip-tok', expiresAt: expiry, actor: 'roundtrip' });
  });

  it('silently swallows localStorage.setItem errors', () => {
    vi.spyOn(window.localStorage, 'setItem').mockImplementation(() => {
      throw new Error('quota exceeded');
    });
    expect(() =>
      writeStoredDashboardSession({ session_token: 'tok', expires_at: futureIso() } as any),
    ).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// isDashboardAuthError
// ---------------------------------------------------------------------------

describe('isDashboardAuthError', () => {
  it('returns true for ApiError with status 401', () => {
    const err = new ApiError(401, 'Unauthorized');
    expect(isDashboardAuthError(err)).toBe(true);
  });

  it('returns false for ApiError with non-401 status', () => {
    const err = new ApiError(500, 'Internal Server Error');
    expect(isDashboardAuthError(err)).toBe(false);
  });

  it('returns true for Error with "dashboard session" in message', () => {
    expect(isDashboardAuthError(new Error('dashboard session expired'))).toBe(true);
  });

  it('returns true for Error with "dashboard login is required" in message', () => {
    expect(isDashboardAuthError(new Error('Dashboard login is required'))).toBe(true);
  });

  it('returns true for Error with "invalid dashboard token" in message', () => {
    expect(isDashboardAuthError(new Error('Invalid Dashboard Token provided'))).toBe(true);
  });

  it('returns true for string matching auth pattern', () => {
    expect(isDashboardAuthError('dashboard session missing')).toBe(true);
  });

  it('returns false for generic Error message', () => {
    expect(isDashboardAuthError(new Error('Network failure'))).toBe(false);
  });

  it('returns false for null', () => {
    expect(isDashboardAuthError(null)).toBe(false);
  });

  it('returns false for undefined', () => {
    expect(isDashboardAuthError(undefined)).toBe(false);
  });

  it('returns false for unrelated string', () => {
    expect(isDashboardAuthError('timeout error')).toBe(false);
  });

  it('is case-insensitive for message patterns', () => {
    expect(isDashboardAuthError('DASHBOARD SESSION EXPIRED')).toBe(true);
    expect(isDashboardAuthError('INVALID DASHBOARD TOKEN')).toBe(true);
  });
});