import React from 'react';
import { Play, Square, RefreshCw } from 'lucide-react';
import type { LogsResponse, TerminalMessage } from '../services/api';
import { SectionHeader } from '../components/UIHelpers';
import { formatDateTime } from '../utils/formatters';

interface BotControlPageProps {
  currentBotState: string;
  currentStage: string;
  currentMode: string;
  isConnected: boolean;
  isBusy: boolean;
  handleBotAction: (action: 'start' | 'stop' | 'restart') => void;
  terminalMessages: TerminalMessage[];
  logs: LogsResponse | null;
}

const BotControlPage: React.FC<BotControlPageProps> = ({
  currentBotState,
  currentStage,
  currentMode,
  isConnected,
  isBusy,
  handleBotAction,
  terminalMessages,
  logs
}) => {
  return (
    <>
      <SectionHeader title="Bot Control" subtitle="Operational state, restart queueing, and recent terminal activity." />
      <div className="card-grid metrics">
        <div className="metric-card">
          <span>Bot Status</span>
          <strong>{currentBotState}</strong>
        </div>
        <div className="metric-card">
          <span>Runtime Stage</span>
          <strong>{currentStage}</strong>
        </div>
        <div className="metric-card">
          <span>Mode</span>
          <strong>{currentMode}</strong>
        </div>
        <div className="metric-card">
          <span>Connection</span>
          <strong>{isConnected ? 'Live' : 'Reconnecting'}</strong>
        </div>
      </div>
      <div className="control-strip">
        <button className="primary-btn" disabled={isBusy} onClick={() => handleBotAction('start')}>
          <Play size={14} />
          Start
        </button>
        <button className="ghost-btn" disabled={isBusy} onClick={() => handleBotAction('stop')}>
          <Square size={14} />
          Stop
        </button>
        <button className="ghost-btn" disabled={isBusy} onClick={() => handleBotAction('restart')}>
          <RefreshCw size={14} />
          Restart
        </button>
      </div>
      <div className="card-grid two-up">
        <section className="panel">
          <SectionHeader title="Terminal Feed" subtitle="Most recent dashboard terminal messages." />
          <div className="terminal-feed">
            {terminalMessages.length ? terminalMessages.map((message, index) => (
              <TerminalLine key={`${message.timestamp}-${index}`} message={message} />
            )) : <div className="empty">No terminal activity yet.</div>}
          </div>
        </section>
        <section className="panel">
          <SectionHeader title="Recent Logs" subtitle="Latest file-backed log lines." />
          <div className="log-feed">
            {logs?.lines?.length ? logs.lines.slice(-12).map((line, index) => (
              <code key={`${line}-${index}`}>{line}</code>
            )) : <div className="empty">No recent log lines.</div>}
          </div>
        </section>
      </div>
    </>
  );
};

function TerminalLine({ message }: { message: TerminalMessage }) {
  return (
    <div className="terminal-line">
      <div>
        <strong>[{message.type}]</strong>
        <span>{formatDateTime(message.timestamp)}</span>
      </div>
      <p>{message.text}</p>
    </div>
  );
}

export default BotControlPage;
