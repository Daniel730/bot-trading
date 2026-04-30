import React from 'react';
import { HealthResponse, LogsResponse } from '../services/api';
import { 
  SectionHeader, 
  formatDateTime, 
  LineMiniChart 
} from '../components/UIHelpers';

interface SystemHealthPageProps {
  health: HealthResponse | null;
  logs: LogsResponse | null;
}

const SystemHealthPage: React.FC<SystemHealthPageProps> = ({
  health,
  logs
}) => {
  return (
    <>
      <SectionHeader title="System Health" subtitle="CPU, memory, network, and event visibility." />
      <div className="card-grid metrics">
        <div className="metric-card">
          <span>CPU</span>
          <strong>{health?.current?.cpu_pct?.toFixed(1) ?? '—'}%</strong>
        </div>
        <div className="metric-card">
          <span>System Memory</span>
          <strong>{health?.current?.system_memory_pct?.toFixed(1) ?? '—'}%</strong>
        </div>
        <div className="metric-card">
          <span>Process RSS</span>
          <strong>{health?.current?.rss_mb?.toFixed(1) ?? '—'} MB</strong>
        </div>
        <div className="metric-card">
          <span>Threads</span>
          <strong>{health?.current?.threads ?? '—'}</strong>
        </div>
      </div>
      <div className="card-grid two-up">
        <section className="panel">
          <SectionHeader title="CPU History" subtitle="Recent process and host samples." />
          {health?.history?.length ? (
            <LineMiniChart
              points={health.history.map((point) => ({ timestamp: point.timestamp, value: point.cpu_pct ?? 0 }))}
              color="var(--crimson)"
            />
          ) : <div className="empty">No health samples yet.</div>}
        </section>
        <section className="panel">
          <SectionHeader title="Memory History" subtitle="Recent host memory utilization." />
          {health?.history?.length ? (
            <LineMiniChart
              points={health.history.map((point) => ({ timestamp: point.timestamp, value: point.system_memory_pct ?? 0 }))}
              color="var(--teal)"
            />
          ) : <div className="empty">No health samples yet.</div>}
        </section>
      </div>
      <section className="panel">
        <SectionHeader title="Recent Events" subtitle={logs?.file ? `Log source: ${logs.file}` : 'SQLite event feed'} />
        <div className="feed">
          {logs?.events?.length ? logs.events.slice(0, 10).map((event, index) => (
            <div className="feed-item" key={`${event.timestamp}-${index}`}>
              <strong>{event.source}</strong>
              <span>{event.level} · {formatDateTime(event.timestamp)}</span>
              <p>{event.message}</p>
            </div>
          )) : <div className="empty">No recent events captured.</div>}
        </div>
      </section>
    </>
  );
};

export default SystemHealthPage;
