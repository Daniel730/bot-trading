import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { HealthResponse, LogsResponse } from '../services/api';
import SystemHealthPage from './SystemHealthPage';

const health: HealthResponse = {
  status: 'healthy',
  current: {
    timestamp: '2026-05-20T00:00:00Z',
    cpu_pct: 12.3,
    rss_mb: 123.4,
    vms_mb: 456.7,
    threads: 8,
    net_sent_mb: 1.2,
    net_recv_mb: 3.4,
    system_memory_pct: 45.6,
    uptime_seconds: 60,
    hostname: 'bot-host',
  },
  history: [],
  runtime: {
    mode: 'ALPACA_PAPER',
    execution_mode: 'ALPACA_PAPER',
    paper_trading: false,
    broker_paper_trading: true,
    alpaca_endpoint_class: 'paper',
    dev_mode: false,
    live_capital_danger: true,
    region: 'US',
    bot_start_time: '2026-05-20T00:00:00Z',
  },
};

const logs: LogsResponse = {
  file: null,
  lines: [],
  events: [],
};

describe('SystemHealthPage runtime mode visibility', () => {
  it('shows sanitized runtime mode fields without exposing the Alpaca URL', () => {
    render(<SystemHealthPage health={health} logs={logs} />);

    expect(screen.getByText('Execution Mode')).toBeInTheDocument();
    expect(screen.getByText('ALPACA_PAPER')).toBeInTheDocument();
    expect(screen.getByText('Broker Paper')).toBeInTheDocument();
    expect(screen.getByText('Yes')).toBeInTheDocument();
    expect(screen.getByText('Alpaca Endpoint')).toBeInTheDocument();
    expect(screen.getByText('PAPER')).toBeInTheDocument();
    expect(screen.queryByText(/paper-api\.alpaca\.markets/i)).not.toBeInTheDocument();
  });
});
