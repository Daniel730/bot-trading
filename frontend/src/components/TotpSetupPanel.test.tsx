import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import TotpSetupPanel from './TotpSetupPanel';

describe('TotpSetupPanel secret handling', () => {
  it('does not load third-party QR endpoints that would exfiltrate the otpauth secret', () => {
    const otpauthUrl = 'otpauth://totp/Alpha:ops?secret=JBSWY3DPEHPK3PXP&issuer=Alpha';
    const { container } = render(
      <TotpSetupPanel
        secret="JBSWY3DPEHPK3PXP"
        otpauthUrl={otpauthUrl}
        backupCodes={['AAAA-BBBB', 'CCCC-DDDD']}
        code=""
        onCodeChange={() => {}}
        onVerify={() => {}}
        isBusy={false}
      />,
    );

    const images = container.querySelectorAll('img');
    expect(images.length).toBe(0);
    expect(container.innerHTML).not.toMatch(/qrserver|chart\.googleapis|api\.qrserver/i);
    expect(screen.getByText(/never leaves this browser/i)).toBeInTheDocument();
    expect(screen.getByLabelText('Copy otpauth URI')).toBeInTheDocument();
  });
});
