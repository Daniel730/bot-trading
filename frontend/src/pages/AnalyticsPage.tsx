import React from 'react';
import type { SummaryResponse, ChartResponse } from '../services/api';
import { 
  formatCurrency, 
  LineMiniChart, 
  DualBarChart, 
  SectionHeader 
} from '../components/UIHelpers';

interface AnalyticsPageProps {
  summary: SummaryResponse | null;
  profitChart: ChartResponse | null;
  winLossChart: ChartResponse | null;
}

const AnalyticsPage: React.FC<AnalyticsPageProps> = ({
  summary,
  profitChart,
  winLossChart
}) => {
  return (
    <>
      <SectionHeader title="Performance Analytics" subtitle="Trade performance and realized outcome trends." />
      <div className="card-grid two-up">
        <section className="panel">
          <SectionHeader title="Cumulative Profit" subtitle="Line view of total realized P&L." />
          {profitChart?.points?.length ? (
            <LineMiniChart points={profitChart.points} color="var(--gold)" />
          ) : (
            <div className="empty">No data yet.</div>
          )}
        </section>
        <section className="panel">
          <SectionHeader title="Win / Loss by Day" subtitle="Daily distribution of positive and negative closes." />
          {winLossChart?.points?.length ? (
            <DualBarChart points={winLossChart.points} />
          ) : (
            <div className="empty">No data yet.</div>
          )}
        </section>
      </div>
      <div className="card-grid metrics">
        <div className="metric-card">
          <span>Total Closed Trades</span>
          <strong>{summary?.closed_trades ?? 0}</strong>
        </div>
        <div className="metric-card">
          <span>Capital Deployed</span>
          <strong>{formatCurrency(summary?.capital_deployed)}</strong>
        </div>
        <div className="metric-card">
          <span>Open Signals</span>
          <strong>{summary?.open_signals ?? 0}</strong>
        </div>
        <div className="metric-card">
          <span>Open Positions</span>
          <strong>{summary?.open_positions ?? 0}</strong>
        </div>
      </div>
    </>
  );
};

export default AnalyticsPage;
