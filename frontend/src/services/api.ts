import { useEffect, useState } from 'react';

export interface PortfolioMetrics {
  daily_budget: number;
  total_invested: number;
  daily_profit: number;
  daily_usage_pct: number;
}

export interface Signal {
  ticker_a: string;
  ticker_b: string;
  z_score: number;
  status: string;
}

export interface TerminalMessage {
  type: 'BOT' | 'USER' | 'SYSTEM';
  text: string;
  timestamp: string;
  metadata?: any;
}

export interface DashboardData {
  stage: string;
  details?: string;
  metrics?: PortfolioMetrics;
  active_signals?: Signal[];
  terminal_messages?: TerminalMessage[];
  timestamp: string;
}

const API_BASE = (window.location.port === '5173' || window.location.port === '3000')
  ? `${window.location.protocol}//${window.location.hostname}:8080` 
  : window.location.origin;

export const useDashboardStream = (token: string | null) => {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const url = new URL('/stream', API_BASE);
    if (token) url.searchParams.set('token', token);

    const eventSource = new EventSource(url.toString());

    eventSource.onmessage = (event) => {
      try {
        const parsedData = JSON.parse(event.data);
        setData(parsedData);
      } catch (err) {
        console.error('Failed to parse SSE data:', err);
      }
    };

    eventSource.onerror = (err) => {
      console.error('SSE Error:', err);
      setError('Connection to backend lost. Retrying...');
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }, [token]);

  return { data, error };
};

export const sendTerminalCommand = async (command: string, token: string | null, metadata?: any) => {
  const url = new URL('/api/terminal/command', API_BASE);
  if (token) url.searchParams.set('token', token);

  const response = await fetch(url.toString(), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command, metadata }),
  });

  if (!response.ok) {
    const errorData = await response.json();
    throw new Error(errorData.detail || 'Failed to send command');
  }

  return response.json();
};
