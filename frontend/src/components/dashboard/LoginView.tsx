import { Shield } from 'lucide-react';
import React from 'react';

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
  } = props;

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
          />
        </label>
        <label className="setting-field">
          <span>Authenticator / Backup Code</span>
          <input
            value={loginOtp}
            onChange={(event) => setLoginOtp(event.target.value)}
            autoComplete="one-time-code"
          />
        </label>
        <button className="primary-btn" disabled={isBusy || Boolean(loginChallengeId)} type="submit">
          <Shield size={14} />
          {loginChallengeId ? 'Waiting Approval' : 'Login'}
        </button>
      </form>
    </div>
  );
}
