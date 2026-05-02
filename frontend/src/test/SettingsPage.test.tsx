/**
 * Tests for the PR changes to frontend/src/pages/SettingsPage.tsx:
 *
 * - Removed visibleFields state (Set<string>)
 * - Removed toggleVisibility function
 * - Sensitive fields now always use type="password" (no toggle to type="text")
 * - The eye/monkey-emoji toggle buttons (👁️/🙈) are gone
 * - Non-sensitive string fields still render as type="text"
 * - Numeric fields still render as type="number"
 */

import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import SettingsPage from '../pages/SettingsPage';
import type { ConfigResponse } from '../services/api';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeConfig(items: ConfigResponse['items']): ConfigResponse {
  return {
    items,
    two_factor: { enabled: false, setup_required: false },
    audit_log: [],
    integrations: {
      brokerage_provider: 'T212',
      alpaca_configured: false,
      alpaca_base_url: '',
      t212_configured: false,
    },
  };
}

function renderPage(
  overrides: Partial<React.ComponentProps<typeof SettingsPage>> = {}
) {
  const defaults = {
    config: null,
    configForm: {},
    setConfigForm: vi.fn(),
    handleSaveConfig: vi.fn(),
    isBusy: false,
    handleInitiate2FA: vi.fn(),
    twoFactorSetup: null,
    twoFactorCode: '',
    setTwoFactorCode: vi.fn(),
    handleVerify2FA: vi.fn(),
  };
  return render(<SettingsPage {...defaults} {...overrides} />);
}

// ---------------------------------------------------------------------------
// Sensitive fields always use type="password" (no toggle)
// ---------------------------------------------------------------------------

describe('SettingsPage – sensitive fields always type="password"', () => {
  it('renders a sensitive string field as type="password"', () => {
    const config = makeConfig([
      {
        key: 'ALPACA_API_KEY',
        value: '********',
        type: 'str',
        sensitive: true,
      },
    ]);
    renderPage({
      config,
      configForm: { ALPACA_API_KEY: 'my-secret-key' },
    });

    const input = screen.getByDisplayValue('my-secret-key') as HTMLInputElement;
    expect(input.type).toBe('password');
  });

  it('sensitive field does NOT render as type="text"', () => {
    const config = makeConfig([
      {
        key: 'ALPACA_API_SECRET',
        value: '********',
        type: 'str',
        sensitive: true,
      },
    ]);
    renderPage({
      config,
      configForm: { ALPACA_API_SECRET: 'secret-value' },
    });

    const input = screen.getByDisplayValue('secret-value') as HTMLInputElement;
    expect(input.type).not.toBe('text');
  });
});

// ---------------------------------------------------------------------------
// Removed visibility toggle buttons (👁️ / 🙈 emojis removed)
// ---------------------------------------------------------------------------

describe('SettingsPage – no visibility toggle buttons', () => {
  it('does NOT render the eye (👁️) toggle button for sensitive fields', () => {
    const config = makeConfig([
      {
        key: 'ALPACA_API_KEY',
        value: '********',
        type: 'str',
        sensitive: true,
      },
    ]);
    renderPage({ config, configForm: {} });

    expect(screen.queryByTitle('Show value')).not.toBeInTheDocument();
    expect(screen.queryByTitle('Hide value')).not.toBeInTheDocument();
  });

  it('does NOT render the 🙈 emoji button', () => {
    const config = makeConfig([
      {
        key: 'DASHBOARD_TOKEN',
        value: '********',
        type: 'str',
        sensitive: true,
      },
    ]);
    renderPage({ config, configForm: {} });

    // Neither emoji should appear on any button
    expect(screen.queryByText('🙈')).not.toBeInTheDocument();
    expect(screen.queryByText('👁️')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Non-sensitive fields
// ---------------------------------------------------------------------------

describe('SettingsPage – non-sensitive field types', () => {
  it('non-sensitive string field renders as type="text"', () => {
    const config = makeConfig([
      {
        key: 'MARKET_TIMEZONE',
        value: 'America/New_York',
        type: 'str',
        sensitive: false,
      },
    ]);
    renderPage({
      config,
      configForm: { MARKET_TIMEZONE: 'America/New_York' },
    });

    const input = screen.getByDisplayValue('America/New_York') as HTMLInputElement;
    expect(input.type).toBe('text');
  });

  it('non-sensitive int field renders as type="number"', () => {
    const config = makeConfig([
      {
        key: 'START_HOUR',
        value: 9,
        type: 'int',
        sensitive: false,
      },
    ]);
    renderPage({
      config,
      configForm: { START_HOUR: '9' },
    });

    const input = screen.getByDisplayValue('9') as HTMLInputElement;
    expect(input.type).toBe('number');
    expect(input.step).toBe('1');
  });

  it('non-sensitive float field renders as type="number" with step=0.0001', () => {
    const config = makeConfig([
      {
        key: 'KELLY_FRACTION',
        value: 0.25,
        type: 'float',
        sensitive: false,
      },
    ]);
    renderPage({
      config,
      configForm: { KELLY_FRACTION: '0.25' },
    });

    const input = screen.getByDisplayValue('0.25') as HTMLInputElement;
    expect(input.type).toBe('number');
    expect(input.step).toBe('0.0001');
  });

  it('bool field renders as a select element', () => {
    const config = makeConfig([
      {
        key: 'PAPER_TRADING',
        value: true,
        type: 'bool',
        sensitive: false,
      },
    ]);
    renderPage({
      config,
      configForm: { PAPER_TRADING: 'true' },
    });

    const select = screen.getByRole('combobox') as HTMLSelectElement;
    expect(select.tagName.toLowerCase()).toBe('select');
  });

  it('options field renders as a select element', () => {
    const config = makeConfig([
      {
        key: 'BROKERAGE_PROVIDER',
        value: 'T212',
        type: 'str',
        sensitive: false,
        options: ['T212', 'ALPACA'],
      },
    ]);
    renderPage({
      config,
      configForm: { BROKERAGE_PROVIDER: 'T212' },
    });

    const select = screen.getByRole('combobox') as HTMLSelectElement;
    expect(select.tagName.toLowerCase()).toBe('select');
  });
});

// ---------------------------------------------------------------------------
// Sensitive field shows masked value (type="password" hides it visually)
// ---------------------------------------------------------------------------

describe('SettingsPage – masked sensitive value from configForm', () => {
  it('sensitive input shows configForm value (masked by password type)', () => {
    const config = makeConfig([
      {
        key: 'TELEGRAM_BOT_TOKEN',
        value: '********',
        type: 'str',
        sensitive: true,
      },
    ]);
    renderPage({
      config,
      configForm: { TELEGRAM_BOT_TOKEN: 'real-token-value' },
    });

    const input = screen.getByDisplayValue('real-token-value') as HTMLInputElement;
    // Input renders the actual value but type="password" masks it visually
    expect(input.type).toBe('password');
  });
});

// ---------------------------------------------------------------------------
// Regression: no wrapper div with display:flex around sensitive inputs
// ---------------------------------------------------------------------------

describe('SettingsPage – simplified sensitive field markup', () => {
  it('sensitive field renders a plain <input> not wrapped in a flex container', () => {
    const config = makeConfig([
      {
        key: 'ALPACA_API_KEY',
        value: '********',
        type: 'str',
        sensitive: true,
      },
    ]);
    const { container } = renderPage({ config, configForm: {} });

    const inputs = container.querySelectorAll('input[type="password"]');
    // The PR removed the <div style="display:flex..."> wrapper, so we expect
    // the input to exist without sibling buttons in the same flex container
    inputs.forEach((input) => {
      const siblings = input.parentElement?.children ?? [];
      const buttonSiblings = Array.from(siblings).filter(
        (el) => el.tagName.toLowerCase() === 'button'
      );
      expect(buttonSiblings).toHaveLength(0);
    });
  });
});