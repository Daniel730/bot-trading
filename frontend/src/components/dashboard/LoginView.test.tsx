/**
 * Tests for src/components/dashboard/LoginView.tsx
 *
 * Covers:
 *  - Static rendering: title, subtitle, field labels, button text
 *  - Conditional banners: loginNotice and loginError
 *  - Input binding: onChange callbacks for token and OTP fields
 *  - Button state: disabled when isBusy or loginChallengeId is present
 *  - Button text: "Login" vs "Waiting Approval" depending on loginChallengeId
 *  - Form submission: onSubmit is called when form is submitted
 */

import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import LoginView from './LoginView';

// ---------------------------------------------------------------------------
// Helper: minimal default props
// ---------------------------------------------------------------------------

function defaultProps(overrides: Record<string, unknown> = {}) {
  return {
    loginToken: '',
    setLoginToken: vi.fn(),
    loginOtp: '',
    setLoginOtp: vi.fn(),
    loginNotice: null,
    loginError: null,
    isBusy: false,
    loginChallengeId: null,
    onSubmit: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Static rendering
// ---------------------------------------------------------------------------

describe('LoginView static content', () => {
  it('renders the application title', () => {
    render(<LoginView {...defaultProps()} />);
    expect(screen.getByText('Alpha Arbitrage')).toBeInTheDocument();
  });

  it('renders the operations console subtitle', () => {
    render(<LoginView {...defaultProps()} />);
    expect(screen.getByText('Operations Console')).toBeInTheDocument();
  });

  it('renders a Security Token label', () => {
    render(<LoginView {...defaultProps()} />);
    expect(screen.getByText('Security Token')).toBeInTheDocument();
  });

  it('renders an Authenticator / Backup Code label', () => {
    render(<LoginView {...defaultProps()} />);
    expect(screen.getByText('Authenticator / Backup Code')).toBeInTheDocument();
  });

  it('renders a password input for the token field', () => {
    render(<LoginView {...defaultProps()} />);
    const passwordInput = screen.getByDisplayValue('');
    // The password field has type="password"
    const inputs = document.querySelectorAll('input[type="password"]');
    expect(inputs.length).toBe(1);
  });

  it('renders the login button with text "Login" by default', () => {
    render(<LoginView {...defaultProps()} />);
    expect(screen.getByRole('button', { name: /login/i })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Conditional banners
// ---------------------------------------------------------------------------

describe('LoginView banners', () => {
  it('renders loginNotice when provided', () => {
    render(<LoginView {...defaultProps({ loginNotice: 'Password reset successfully' })} />);
    expect(screen.getByText('Password reset successfully')).toBeInTheDocument();
  });

  it('does not render notice banner when loginNotice is null', () => {
    render(<LoginView {...defaultProps({ loginNotice: null })} />);
    const successBanners = document.querySelectorAll('.banner.success');
    expect(successBanners.length).toBe(0);
  });

  it('renders loginError when provided', () => {
    render(<LoginView {...defaultProps({ loginError: 'Invalid credentials' })} />);
    expect(screen.getByText('Invalid credentials')).toBeInTheDocument();
  });

  it('does not render error banner when loginError is null', () => {
    render(<LoginView {...defaultProps({ loginError: null })} />);
    const errorBanners = document.querySelectorAll('.banner.error');
    expect(errorBanners.length).toBe(0);
  });

  it('can show both notice and error simultaneously', () => {
    render(<LoginView {...defaultProps({ loginNotice: 'Session expired', loginError: 'Please log in again' })} />);
    expect(screen.getByText('Session expired')).toBeInTheDocument();
    expect(screen.getByText('Please log in again')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Input binding
// ---------------------------------------------------------------------------

describe('LoginView input interactions', () => {
  it('calls setLoginToken when security token input changes', () => {
    const setLoginToken = vi.fn();
    render(<LoginView {...defaultProps({ setLoginToken })} />);
    const passwordInput = document.querySelector('input[type="password"]') as HTMLInputElement;
    fireEvent.change(passwordInput, { target: { value: 'my-secret' } });
    expect(setLoginToken).toHaveBeenCalledWith('my-secret');
  });

  it('calls setLoginOtp when OTP input changes', () => {
    const setLoginOtp = vi.fn();
    render(<LoginView {...defaultProps({ setLoginOtp })} />);
    // OTP field is not password type and has autocomplete="one-time-code"
    const otpInput = document.querySelector('input[autocomplete="one-time-code"]') as HTMLInputElement;
    fireEvent.change(otpInput, { target: { value: '123456' } });
    expect(setLoginOtp).toHaveBeenCalledWith('123456');
  });

  it('displays the current loginToken value in the password field', () => {
    render(<LoginView {...defaultProps({ loginToken: 'prefilled-token' })} />);
    const passwordInput = document.querySelector('input[type="password"]') as HTMLInputElement;
    expect(passwordInput.value).toBe('prefilled-token');
  });

  it('displays the current loginOtp value in the OTP field', () => {
    render(<LoginView {...defaultProps({ loginOtp: '654321' })} />);
    const otpInput = document.querySelector('input[autocomplete="one-time-code"]') as HTMLInputElement;
    expect(otpInput.value).toBe('654321');
  });
});

// ---------------------------------------------------------------------------
// Button state
// ---------------------------------------------------------------------------

describe('LoginView button state', () => {
  it('button is enabled by default', () => {
    render(<LoginView {...defaultProps()} />);
    const btn = screen.getByRole('button', { name: /login/i });
    expect(btn).not.toBeDisabled();
  });

  it('button is disabled when isBusy is true', () => {
    render(<LoginView {...defaultProps({ isBusy: true })} />);
    const btn = screen.getByRole('button');
    expect(btn).toBeDisabled();
  });

  it('button is disabled when loginChallengeId is set', () => {
    render(<LoginView {...defaultProps({ loginChallengeId: 'challenge-abc' })} />);
    const btn = screen.getByRole('button');
    expect(btn).toBeDisabled();
  });

  it('button shows "Waiting Approval" text when loginChallengeId is set', () => {
    render(<LoginView {...defaultProps({ loginChallengeId: 'challenge-abc' })} />);
    expect(screen.getByText('Waiting Approval')).toBeInTheDocument();
  });

  it('button is disabled when both isBusy and loginChallengeId are set', () => {
    render(<LoginView {...defaultProps({ isBusy: true, loginChallengeId: 'ch-1' })} />);
    const btn = screen.getByRole('button');
    expect(btn).toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// Form submission
// ---------------------------------------------------------------------------

describe('LoginView form submission', () => {
  it('calls onSubmit when form is submitted', () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<LoginView {...defaultProps({ onSubmit })} />);
    const form = document.querySelector('form') as HTMLFormElement;
    fireEvent.submit(form);
    expect(onSubmit).toHaveBeenCalledOnce();
  });
});