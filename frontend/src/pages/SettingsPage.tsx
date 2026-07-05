import React, { useState } from 'react';
import type { ConfigResponse, TwoFactorInitiateResponse } from '../services/api';
import { SectionHeader } from '../components/UIHelpers';
import { formatDateTime } from '../utils/formatters';
import { getConfigMetadata } from '../utils/configMetadata';

interface SettingsPageProps {
  config: ConfigResponse | null;
  configForm: Record<string, string>;
  setConfigForm: (val: Record<string, string> | ((prev: Record<string, string>) => Record<string, string>)) => void;
  handleSaveConfig: () => void;
  isBusy: boolean;
  handleInitiate2FA: () => void;
  twoFactorSetup: TwoFactorInitiateResponse | null;
  twoFactorCode: string;
  setTwoFactorCode: (val: string) => void;
  handleVerify2FA: () => void;
}

type SettingsTab = 'general' | 'security' | 'audit';

const SettingsPage: React.FC<SettingsPageProps> = ({
  config,
  configForm,
  setConfigForm,
  handleSaveConfig,
  isBusy,
  handleInitiate2FA,
  twoFactorSetup,
  twoFactorCode,
  setTwoFactorCode,
  handleVerify2FA,
}) => {
  const [activeTab, setActiveTab] = useState<SettingsTab>('general');
  const [visibleFields, setVisibleFields] = useState<Set<string>>(new Set());

  const toggleVisibility = (key: string) => {
    setVisibleFields(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const getCategory = (key: string) => {
    if (
      key === 'BROKERAGE_PROVIDER' ||
      key.startsWith('ALPACA_')
    ) {
      return 'Brokerage';
    }
    if (key.includes('RISK') || key.includes('TRADE') || key.includes('MARGIN') || key.includes('DRAWDOWN')) {
      return 'Trading & Risk';
    }
    if (key.includes('API') || key.includes('URL') || key.includes('TOKEN') || key.includes('KEY')) {
      return 'API & Connectivity';
    }
    return 'General';
  };

  const categories = {
    Brokerage: config?.items.filter(item => getCategory(item.key) === 'Brokerage'),
    'Trading & Risk': config?.items.filter(item => getCategory(item.key) === 'Trading & Risk'),
    'API & Connectivity': config?.items.filter(item => getCategory(item.key) === 'API & Connectivity'),
    General: config?.items.filter(item => getCategory(item.key) === 'General'),
  };
  const provider = configForm.BROKERAGE_PROVIDER
    ?? String(config?.integrations?.brokerage_provider ?? config?.items.find((item) => item.key === 'BROKERAGE_PROVIDER')?.value ?? 'ALPACA');
  const hasAlpacaKey = Boolean(String(configForm.ALPACA_API_KEY ?? '').trim())
    || Boolean(config?.integrations?.alpaca_configured);
  const hasAlpacaSecret = Boolean(String(configForm.ALPACA_API_SECRET ?? '').trim())
    || Boolean(config?.integrations?.alpaca_configured);
  const alpacaBaseUrl = String(
    configForm.ALPACA_BASE_URL
    ?? config?.integrations?.alpaca_base_url
    ?? config?.items.find((item) => item.key === 'ALPACA_BASE_URL')?.value
    ?? '',
  );

  return (
    <>
      <SectionHeader title="Configuration" subtitle="Dashboard-editable runtime values with 2FA for sensitive changes." />

      <div className="editor-tabs" style={{ marginBottom: '20px', padding: 0 }}>
        <button className={`editor-tab ${activeTab === 'general' ? 'active' : ''}`} onClick={() => setActiveTab('general')}>Configuration</button>
        <button className={`editor-tab ${activeTab === 'security' ? 'active' : ''}`} onClick={() => setActiveTab('security')}>Security & 2FA</button>
        <button className={`editor-tab ${activeTab === 'audit' ? 'active' : ''}`} onClick={() => setActiveTab('audit')}>Audit Log</button>
      </div>

      {activeTab === 'general' && (
        <section className="panel">
          <SectionHeader title="Editable Variables" subtitle="Sensitive changes require a current OTP or backup code." />
          <div className="twofa-status" style={{ marginBottom: '16px' }}>
            <div><span>Active Equity Broker</span><strong>{provider}</strong></div>
            <div><span>Alpaca API Key</span><strong>{hasAlpacaKey ? 'Set' : 'Missing'}</strong></div>
            <div><span>Alpaca API Secret</span><strong>{hasAlpacaSecret ? 'Set' : 'Missing'}</strong></div>
            <div><span>Alpaca Base URL</span><strong>{alpacaBaseUrl || 'Not set'}</strong></div>
          </div>

          {Object.entries(categories).map(([category, items]) => (
            items && items.length > 0 && (
              <div key={category} style={{ marginBottom: '24px' }}>
                <h3 style={{ fontSize: '0.9rem', color: 'var(--muted)', textTransform: 'uppercase', marginBottom: '12px', borderBottom: '1px solid var(--line)', paddingBottom: '4px' }}>{category}</h3>
                <div className="settings-grid">
                  {items.map((item) => {
                    const metadata = getConfigMetadata(item.key);
                    return (
                      <label key={item.key} className="setting-field" title={metadata.description}>
                        <span>{metadata.label}{item.sensitive ? ' - 2FA' : ''}</span>
                        {item.options?.length ? (
                          <select
                            value={configForm[item.key] ?? item.options[0]}
                            onChange={(event) => setConfigForm((current) => ({ ...current, [item.key]: event.target.value }))}
                          >
                            {item.options.map((option) => (
                              <option key={option} value={option}>{option}</option>
                            ))}
                          </select>
                        ) : item.type === 'bool' ? (
                          <select
                            value={configForm[item.key] ?? 'false'}
                            onChange={(event) => setConfigForm((current) => ({ ...current, [item.key]: event.target.value }))}
                          >
                            <option value="true">Enabled</option>
                            <option value="false">Disabled</option>
                          </select>
                        ) : (
                          <div style={{ display: 'flex', gap: '8px', alignItems: 'center', width: '100%' }}>
                            <input
                              type={item.sensitive && !visibleFields.has(item.key) ? 'password' : item.type === 'str' ? 'text' : item.type === 'int' || item.type === 'float' ? 'number' : 'text'}
                              step={item.type === 'int' ? '1' : item.type === 'float' ? '0.0001' : undefined}
                              value={configForm[item.key] ?? ''}
                              onChange={(event) => setConfigForm((current) => ({ ...current, [item.key]: event.target.value }))}
                              style={{ flex: 1 }}
                            />
                            {item.sensitive && (
                              <button
                                type="button"
                                onClick={() => toggleVisibility(item.key)}
                                style={{ padding: '4px', background: 'transparent', border: 'none', cursor: 'pointer', fontSize: '1.2rem', color: 'var(--text)' }}
                                title={visibleFields.has(item.key) ? "Hide value" : "Show value"}
                              >
                                {visibleFields.has(item.key) ? '🙈' : '👁️'}
                              </button>
                            )}
                          </div>
                        )}
                      </label>
                    );
                  })}
                </div>
              </div>
            )
          ))}
          <div className="inline-actions" style={{ marginTop: '12px' }}>
            <button className="primary-btn" disabled={isBusy} onClick={handleSaveConfig}>Save Changes</button>
          </div>
        </section>
      )}

      {activeTab === 'security' && (
        <section className="panel">
          <SectionHeader title="Two-Factor Auth" subtitle="Authenticator-based gate for sensitive config writes." />
          <div className="twofa-status">
            <div><span>Enabled</span><strong>{config?.two_factor.enabled ? 'Yes' : 'No'}</strong></div>
            <div><span>Pending Setup</span><strong>{config?.two_factor.pending_setup ? 'Yes' : 'No'}</strong></div>
            <div><span>Backup Codes Left</span><strong>{config?.two_factor.backup_codes_remaining ?? 0}</strong></div>
          </div>
          <div className="inline-actions">
            <button className="ghost-btn" disabled={isBusy} onClick={handleInitiate2FA}>Generate Setup Secret</button>
          </div>
          {twoFactorSetup ? (
            <div className="twofa-setup" style={{ marginTop: '20px' }}>
              <p>Secret: <code>{twoFactorSetup.secret}</code></p>
              <p>otpauth URI:</p>
              <code className="block-code">{twoFactorSetup.otpauth_url}</code>
              <p>Backup codes:</p>
              <div className="code-grid">
                {twoFactorSetup.backup_codes.map((code) => <code key={code}>{code}</code>)}
              </div>
              <div className="inline-actions" style={{ marginTop: '12px' }}>
                <input
                  value={twoFactorCode}
                  onChange={(event) => setTwoFactorCode(event.target.value)}
                  placeholder="Enter authenticator code"
                />
                <button className="primary-btn" disabled={isBusy} onClick={handleVerify2FA}>Verify & Enable</button>
              </div>
            </div>
          ) : null}
        </section>
      )}

      {activeTab === 'audit' && (
        <section className="panel">
          <SectionHeader title="Audit Log" subtitle="Recent configuration changes and 2FA usage." />
          <div className="list">
            {config?.audit_log?.length ? config.audit_log.map((entry, index) => (
              <div className="list-row audit-row" key={`${entry.key}-${entry.timestamp}-${index}`}>
                <div>
                  <strong>{entry.key}</strong>
                  <span>{entry.actor} - {formatDateTime(entry.timestamp)}</span>
                </div>
                <div className="audit-values">
                  <span>{String(entry.old_value)}</span>
                  <span>-&gt;</span>
                  <span>{String(entry.new_value)}</span>
                  {entry.requires_2fa ? <em>2FA</em> : null}
                </div>
              </div>
            )) : <div className="empty">No config changes recorded yet.</div>}
          </div>
        </section>
      )}
    </>
  );
};

export default SettingsPage;
