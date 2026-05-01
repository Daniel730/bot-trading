import React, { useEffect, useState } from 'react';
import type { Signal } from '../services/api';
import { SectionHeader } from '../components/UIHelpers';
import Pagination from '../components/Pagination';
import { Radio } from 'lucide-react';

interface SignalsPageProps {
  signals: Signal[];
}

const SignalsPage: React.FC<SignalsPageProps> = ({ signals }) => {
  const [page, setPage] = useState(1);
  const pageSize = 12;

  const totalItems = signals.length;
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);
  const paginatedSignals = signals.slice((page - 1) * pageSize, page * pageSize);

  return (
    <>
      <SectionHeader 
        title="Active Signals" 
        subtitle="Real-time statistical opportunities from the live scan loop." 
      />
      
      <div className="panel">
        {totalItems === 0 ? (
          <div className="empty-state">
            <Radio size={28} style={{ opacity: 0.3 }} />
            <span>No active signals found. Market may be quiet or cointegration pending.</span>
          </div>
        ) : (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Pair</th>
                    <th>Z-Score</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {paginatedSignals.map((sig, i) => (
                    <tr key={`${sig.ticker_a}-${sig.ticker_b}-${i}`}>
                      <td>
                        <strong>{sig.ticker_a} / {sig.ticker_b}</strong>
                      </td>
                      <td>
                        {typeof sig.z_score === 'number' ? (
                          <span className={Math.abs(sig.z_score) > 2 ? (sig.z_score > 0 ? 'negative' : 'positive') : ''}>
                            {sig.z_score.toFixed(2)}
                          </span>
                        ) : (
                          <span className="muted">—</span>
                        )}
                      </td>
                      <td>
                        <span className="badge badge-blue">{sig.status}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="table-footer">
              <Pagination 
                currentPage={page} 
                totalItems={totalItems} 
                pageSize={pageSize} 
                onPageChange={setPage} 
              />
            </div>
          </>
        )}
      </div>
    </>
  );
};

export default SignalsPage;
