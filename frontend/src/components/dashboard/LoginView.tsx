import { Shield } from 'lucide-react';
import React, { useState } from 'react';

interface LoginViewProps {
  loginToken: string;
  setLoginToken: (value: string) => void;
  loginOtp: string;
  setLoginOtp: (value: string) => void;
  loginNotice: string | null;
  loginError: string | null;
  isBusy: boolean;
  loginChallengeId: string | null;
  onSubmit: (event: React.FormEvent) => Promise<void>;
  onCancelApproval?: () => void;
}

export default function LoginView(props: LoginViewProps) {
  const {
    loginToken,
    setLoginToken,
    loginOtp,
    setLoginOtp,
    loginNotice,
    loginError,
    isBusy,
    loginChallengeId,
    onSubmit,
    onCancelApproval,
  } = props;
  const [showOtpField, setShowOtpField] = useState(Boolean(loginOtp));

  return (
    <div className="login-screen">
      <form className="login-panel" onSubmit={onSubmit}>
        <div className="login-mark">
          <Shield size={24} />
        </div>
        <div>
          <h1>Alpha Arbitrage</h1>
          <p>Operations Console</p>
        </div>
        {loginNotice ? <div className="banner success">{loginNotice}</div> : null}
        {loginError ? <div className="banner error">{loginError}</div> : null}
        <label className="setting-field">
          <span>Security Token</span>
          <input
            type="password"
            value={loginToken}
            onChange={(event) => setLoginToken(event.target.value)}
            autoComplete="current-password"
            required
            disabled={Boolean(loginChallengeId)}
          />
        </label>
        {showOtpField ? (
          <label className="setting-field">
            <span>Authenticator / Backup Code</span>
            <input
              value={loginOtp}
              onChange={(event) => setLoginOtp(event.target.value)}
              autoComplete="one-time-code"
              disabled={Boolean(loginChallengeId)}
              placeholder="Required when Telegram approval is unavailable"
            />
          </label>
        ) : (
          <p className="muted">
            After submitting the token, approve via Telegram when prompted.
            {' '}
            <button
              type="button"
              className="link-btn"
              onClick={() => setShowOtpField(true)}
            >
              Use OTP instead
            </button>
          </p>
        )}
        <div className="inline-actions">
          <button className="primary-btn" disabled={isBusy || Boolean(loginChallengeId)} type="submit">
            <Shield size={14} />
            {loginChallengeId ? 'Waiting Approval' : 'Login'}
          </button>
          {loginChallengeId && onCancelApproval ? (
            <button type="button" className="ghost-btn" disabled={isBusy} onClick={onCancelApproval}>
              Cancel
            </button>
          ) : null}
        </div>
      </form>
    </div>
  );
}
