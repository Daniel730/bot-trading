import { useEffect, useMemo, useState } from 'react';
import type { ConfigResponse, HealthResponse, SummaryResponse, TradeHistoryResponse } from '../services/api';

interface StartupProgressInput {
  isAuthenticated: boolean;
  isConnected: boolean;
  currentStage: string;
  details?: string;
  dataReady: boolean;
  summary: SummaryResponse | null;
  health: HealthResponse | null;
  tradeHistory: TradeHistoryResponse | null;
  config: ConfigResponse | null;
}

export function useStartupProgress(input: StartupProgressInput) {
  const {
    isAuthenticated,
    isConnected,
    currentStage,
    details,
    dataReady,
    summary,
    health,
    tradeHistory,
    config,
  } = input;

  const startupStageText = `${currentStage} ${details ?? ''}`.toLowerCase();

  const preWarmingProgress = useMemo(() => {
    const stage = (currentStage || '').toLowerCase();
    const stageDetails = details || '';
    if (!/pre[_ -]?warming|initializ/.test(stage) && !/pair list/i.test(stageDetails)) return null;
    const match = stageDetails.match(/(\d+)\s*\/\s*(\d+)/);
    if (!match) return null;
    const current = Number(match[1]);
    const total = Number(match[2]);
    if (!Number.isFinite(current) || !Number.isFinite(total) || total <= 0) return null;
    return {
      current,
      total,
      pct: Math.max(0, Math.min(100, Math.round((current / total) * 100))),
    };
  }, [currentStage, details]);

  const startupReady = useMemo(() => {
    if (!isAuthenticated) return false;
    if (!summary || !dataReady) return false;
    if (!isConnected) return false;
    const stillStarting = /(boot|init|start|warm|load|attach|connect)/i.test(startupStageText);
    return !stillStarting;
  }, [dataReady, isAuthenticated, isConnected, startupStageText, summary]);

  const startupTargetProgress = useMemo(() => {
    if (!isAuthenticated) return 0;
    if (startupReady) return 100;
    let progress = 10;
    if (dataReady) progress = 28;
    if (summary) progress = 54;
    if (health || tradeHistory || config) progress = 72;
    if (isConnected) progress = 84;
    if (/warm|load|attach|connect/.test(startupStageText)) progress = Math.max(progress, 90);
    return Math.min(progress, 95);
  }, [config, dataReady, health, isAuthenticated, isConnected, startupReady, startupStageText, summary, tradeHistory]);

  const [startupProgress, setStartupProgress] = useState(8);

  useEffect(() => {
    if (!isAuthenticated) {
      setStartupProgress(8);
      return;
    }
    setStartupProgress((current) => {
      if (startupReady) return 100;
      if (current > startupTargetProgress) return startupTargetProgress;
      return current;
    });
  }, [isAuthenticated, startupReady, startupTargetProgress]);

  useEffect(() => {
    if (!isAuthenticated || startupReady) return;
    const id = window.setInterval(() => {
      setStartupProgress((current) => {
        if (current >= startupTargetProgress) return current;
        const remaining = startupTargetProgress - current;
        const step = Math.max(1, Math.ceil(remaining / 6));
        return Math.min(startupTargetProgress, current + step);
      });
    }, 350);
    return () => window.clearInterval(id);
  }, [isAuthenticated, startupReady, startupTargetProgress]);

  return {
    startupProgress,
    startupReady,
    preWarmingProgress,
  };
}
