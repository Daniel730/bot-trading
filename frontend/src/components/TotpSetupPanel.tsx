import React, { useMemo, useState } from 'react';
import { Check, Copy, Download, Eye, EyeOff } from 'lucide-react';

interface TotpSetupPanelProps {
  secret: string;
  otpauthUrl: string;
  backupCodes: string[];
  code: string;
  onCodeChange: (value: string) => void;
  onVerify: () => void;
  isBusy: boolean;
}

const TotpSetupPanel: React.FC<TotpSetupPanelProps> = ({
  secret,
  otpauthUrl,
  backupCodes,
  code,
  onCodeChange,
  onVerify,
  isBusy,
}) => {
  const [showSecret, setShowSecret] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const [ackBackup, setAckBackup] = useState(false);

  const qrSrc = useMemo(
    () => `https://api.qrserver.com/v1/create-qr-code/?size=220x220&data=${encodeURIComponent(otpauthUrl)}`,
    [otpauthUrl],
  );

  const copyText = async (label: string, value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(label);
      window.setTimeout(() => setCopied(null), 1500);
    } catch {
      setCopied(null);
    }
  };

  const downloadBackupCodes = () => {
    const blob = new Blob([`${backupCodes.join('\n')}\n`], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'alpha-arbitrage-2fa-backup-codes.txt';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="twofa-setup" style={{ marginTop: '20px' }}>
      <div className="twofa-qr-row">
        <div className="twofa-qr-card">
          <img src={qrSrc} alt="Authenticator QR code" width={220} height={220} />
          <p className="muted">Scan with Google Authenticator, 1Password, or Authy.</p>
        </div>
        <div className="twofa-manual">
          <label className="setting-field">
            <span>Manual secret</span>
            <div className="inline-actions">
              <code>{showSecret ? secret : '••••••••••••••••'}</code>
              <button type="button" className="ghost-btn" onClick={() => setShowSecret((v) => !v)} aria-label="Toggle secret">
                {showSecret ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
              <button type="button" className="ghost-btn" onClick={() => copyText('secret', secret)} aria-label="Copy secret">
                {copied === 'secret' ? <Check size={14} /> : <Copy size={14} />}
              </button>
            </div>
          </label>
        </div>
      </div>

      <div style={{ marginTop: '16px' }}>
        <strong>Backup codes</strong>
        <p className="muted">Store these offline. Each code works once.</p>
        <div className="code-grid">
          {backupCodes.map((item) => (
            <code key={item}>{item}</code>
          ))}
        </div>
        <div className="inline-actions" style={{ marginTop: '12px' }}>
          <button type="button" className="ghost-btn" onClick={() => copyText('backup', backupCodes.join('\n'))}>
            {copied === 'backup' ? <Check size={14} /> : <Copy size={14} />}
            Copy all
          </button>
          <button type="button" className="ghost-btn" onClick={downloadBackupCodes}>
            <Download size={14} />
            Download
          </button>
        </div>
        <label className="setting-field" style={{ marginTop: '12px' }}>
          <span>
            <input type="checkbox" checked={ackBackup} onChange={(e) => setAckBackup(e.target.checked)} />
            {' '}I saved my backup codes
          </span>
        </label>
      </div>

      <div className="inline-actions" style={{ marginTop: '12px' }}>
        <input
          value={code}
          onChange={(event) => onCodeChange(event.target.value)}
          placeholder="Authenticator code"
          autoComplete="one-time-code"
        />
        <button className="primary-btn" disabled={isBusy || !ackBackup || code.trim().length < 6} onClick={onVerify}>
          Verify & Enable
        </button>
      </div>
    </div>
  );
};

export default TotpSetupPanel;
