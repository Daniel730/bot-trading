import React from 'react';
import { Search } from 'lucide-react';
import type { TradeHistoryResponse } from '../services/api';
import { 
  formatCurrency, 
  formatDateTime, 
  getTrendClass, 
  SectionHeader 
} from '../components/UIHelpers';

interface TradeHistoryPageProps {
  tradeHistory: TradeHistoryResponse | null;
  tradeSearch: string;
  setTradeSearch: (val: string) => void;
  tradeStatus: string;
  setTradeStatus: (val: string) => void;
  tradeVenue: string;
  setTradeVenue: (val: string) => void;
  tradePage: number;
  setTradePage: (val: number | ((prev: number) => number)) => void;
  refreshTradeHistory: () => void;
}

const TradeHistoryPage: React.FC<TradeHistoryPageProps> = ({
  tradeHistory,
  tradeSearch,
  setTradeSearch,
  tradeStatus,
  setTradeStatus,
  tradeVenue,
  setTradeVenue,
  tradePage,
  setTradePage,
  refreshTradeHistory
}) => {
  return (
    <>
      <SectionHeader title="Trade History" subtitle="Search and filter executed trade groups." />
      <div className="toolbar">
        <label className="search-box">
          <Search size={14} />
          <input
            value={tradeSearch}
            onChange={(event) => setTradeSearch(event.target.value)}
            placeholder="Search ticker or signal id"
          />
        </label>
        <select value={tradeStatus} onChange={(event) => { setTradePage(1); setTradeStatus(event.target.value); }}>
          <option value="">All statuses</option>
          <option value="OPEN">Open</option>
          <option value="CLOSED">Closed</option>
          <option value="COMPLETED">Completed</option>
        </select>
        <select value={tradeVenue} onChange={(event) => { setTradePage(1); setTradeVenue(event.target.value); }}>
          <option value="">All venues</option>
          <option value="T212">T212</option>
          <option value="WEB3">WEB3</option>
        </select>
        <button className="ghost-btn" onClick={() => { setTradePage(1); refreshTradeHistory(); }}>Apply</button>
      </div>
      <section className="panel">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Pair</th>
                <th>Status</th>
                <th>Venue</th>
                <th>Opened</th>
                <th>Notional</th>
                <th>P&L</th>
              </tr>
            </thead>
            <tbody>
              {tradeHistory?.items?.length ? tradeHistory.items.map((trade) => (
                <tr key={trade.signal_id}>
                  <td>
                    <strong>{trade.pair}</strong>
                    <div className="muted">#{trade.signal_id.slice(0, 8)}</div>
                  </td>
                  <td>{trade.status}</td>
                  <td>{trade.venue}</td>
                  <td>{formatDateTime(trade.opened_at)}</td>
                  <td>{formatCurrency(trade.notional)}</td>
                  <td className={getTrendClass(trade.pnl)}>{formatCurrency(trade.pnl)}</td>
                </tr>
              )) : (
                <tr>
                  <td colSpan={6} className="empty-row">No trades matched the current filters.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="table-footer">
          <span>{tradeHistory?.total ?? 0} results</span>
          <div className="pager">
            <button className="ghost-btn" disabled={tradePage === 1} onClick={() => setTradePage((current) => Math.max(1, current - 1))}>Previous</button>
            <span>Page {tradePage}</span>
            <button
              className="ghost-btn"
              disabled={!!tradeHistory && tradeHistory.page * tradeHistory.page_size >= tradeHistory.total}
              onClick={() => setTradePage((current) => (current as number) + 1)}
            >
              Next
            </button>
          </div>
        </div>
      </section>
    </>
  );
};

export default TradeHistoryPage;
