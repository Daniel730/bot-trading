import React, { useEffect, useState } from 'react';
import { Check, X } from 'lucide-react';
import { approvePendingTrade, fetchPendingApprovals, rejectPendingTrade, type PendingApproval } from '../services/api';
import { SectionHeader } from './UIHelpers';

interface PendingApprovalsPanelProps {
  token: string | null;
  sessionToken: string | null;
  onAuthFailure?: (err: unknown) => boolean;
  onMessage?: (message: string) => void;
  onError?: (message: string) => void;
}

const PendingApprovalsPanel: React.FC<PendingApprovalsPanelProps> = ({
  token,
  sessionToken,
  onAuthFailure,
  onMessage,
  onError,
}) => {
  const [items, setItems] = useState<PendingApproval[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);

  const refresh = async () => {
    try {
      const response = await fetchPendingApprovals(token, sessionToken);
      setItems(response.pending ?? []);
    } catch (err: any) {
      if (onAuthFailure?.(err)) return;
      onError?.(err?.message || 'Failed to load pending approvals.');
    }
  };

  useEffect(() => {
    refresh();
    const interval = window.setInterval(refresh, 5000);
    return () => window.clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, sessionToken]);

  const resolve = async (correlationId: string, approved: boolean) => {
    setBusyId(correlationId);
    try {
      if (approved) {
        await approvePendingTrade(token, sessionToken, correlationId);
        onMessage?.(`Approved ${correlationId}`);
      } else {
        await rejectPendingTrade(token, sessionToken, correlationId);
        onMessage?.(`Rejected ${correlationId}`);
      }
      await refresh();
    } catch (err: any) {
      if (onAuthFailure?.(err)) return;
      onError?.(err?.message || `Failed to ${approved ? 'approve' : 'reject'} ${correlationId}`);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section className="panel">
      <SectionHeader title="Pending Approvals" subtitle="Trade approvals waiting for Telegram or dashboard action." />
      <div className="list">
        {items.length ? items.map((item) => (
          <div className="list-row" key={item.correlation_id}>
            <div>
              <strong>{item.correlation_id}</strong>
              <span>{item.summary || 'Trade approval'}</span>
            </div>
            <div className="inline-actions">
              <button
                type="button"
                className="primary-btn"
                disabled={busyId === item.correlation_id}
                onClick={() => resolve(item.correlation_id, true)}
              >
                <Check size={14} />
                Approve
              </button>
              <button
                type="button"
                className="ghost-btn"
                disabled={busyId === item.correlation_id}
                onClick={() => resolve(item.correlation_id, false)}
              >
                <X size={14} />
                Reject
              </button>
            </div>
          </div>
        )) : <div className="empty">No pending approvals.</div>}
      </div>
    </section>
  );
};

export default PendingApprovalsPanel;
