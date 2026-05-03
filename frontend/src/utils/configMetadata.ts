export interface ConfigMetadata {
  label: string;
  description: string;
  category?: string;
}

export const CONFIG_METADATA: Record<string, ConfigMetadata> = {
  // --- General ---
  'REGION': { label: 'Trading Region', description: 'Target market region (US or EU). Affects trading hours and asset availability.' },
  'BROKERAGE_PROVIDER': { label: 'Broker', description: 'Active broker for live and paper-order validation.' },
  'PAPER_TRADING': { label: 'Shadow Trading', description: 'When enabled, trades are simulated locally without hitting any exchange API.' },
  'DEV_MODE': { label: 'Development Mode', description: 'Enable 24/7 scanning on test pairs. Do not use for real trading.' },
  'LIVE_CAPITAL_DANGER': { label: 'Live Capital Guard', description: 'Safety switch that must be ON to allow real money trades.' },
  'ALLOW_LIVE_APPROVAL_WITHOUT_TELEGRAM': { label: 'Allow Live Approval Without Telegram', description: 'Permit live approvals even if Telegram approval delivery is unavailable.' },

  // --- Risk & Allocation ---
  'ALPACA_BUDGET_USD': { label: 'Alpaca Budget (USD)', description: 'Optional total capital cap for Alpaca trading. Set 0 to use broker cash.' },
  'MAX_ALLOCATION_PERCENTAGE': { label: 'Max Pair Allocation %', description: 'Maximum % of total budget allowed for a single trading pair.' },
  'MAX_RISK_PER_TRADE': { label: 'Max Risk Per Trade', description: 'Percentage of account equity to risk on a single trade group.' },
  'MAX_DRAWDOWN': { label: 'Account Drawdown Limit', description: 'Maximum allowed account-wide drawdown before the bot stops trading.' },
  'FINANCIAL_KILL_SWITCH_PCT': { label: 'Hard Kill Switch %', description: 'Percentage loss on a single trade that triggers an immediate exit.' },

  // --- Strategy & Execution ---
  'APPROVAL_THRESHOLD': { label: 'AI Approval Score', description: 'Minimum confidence score required from the agent ensemble to fire a signal.' },
  'MONITOR_ENTRY_ZSCORE': { label: 'Entry Z-Score', description: 'Statistical threshold for pair divergence. Higher means more conservative entries.' },
  'TAKE_PROFIT_ZSCORE': { label: 'Take Profit Z-Score', description: 'The z-score target where the bot will close a profitable position.' },
  'STOP_LOSS_ZSCORE': { label: 'Stop Loss Z-Score', description: 'The z-score target where the bot will exit a losing position.' },
  'SCAN_INTERVAL_SECONDS': { label: 'Scan Frequency', description: 'Seconds between each market scan loop.' },

  // --- Connectivity ---
  'POLYGON_API_KEY': { label: 'Polygon API Key', description: 'Used for real-time equity market data.' },
  'OPENAI_API_KEY': { label: 'OpenAI API Key', description: 'Used for fundamental analysis and sentiment reasoning.' },
  'GEMINI_API_KEY': { label: 'Gemini API Key', description: 'Used for macro-economic analysis and reflection.' },
  'TELEGRAM_BOT_TOKEN': { label: 'Telegram Token', description: 'Bot token for remote approvals and notifications.' },
  'TELEGRAM_CHAT_ID': { label: 'Telegram Chat ID', description: 'Target chat for admin alerts.' },
  'ALPACA_API_KEY': { label: 'Alpaca API Key', description: 'Alpaca API key.' },
  'ALPACA_API_SECRET': { label: 'Alpaca API Secret', description: 'Alpaca API secret.' },
  'ALPACA_BASE_URL': { label: 'Alpaca Base URL', description: 'Alpaca paper or live REST endpoint.' },
  'SEC_USER_AGENT': { label: 'SEC User Agent', description: 'User-Agent value used for SEC/EDGAR and similar data-source calls.' },

  // --- Advanced ---
  'KALMAN_DELTA': { label: 'Kalman Process Noise', description: 'Higher values make the filter more responsive but noisier.' },
  'KALMAN_R': { label: 'Kalman Measurement Noise', description: 'Reflects confidence in incoming price data accuracy.' },
  'COINTEGRATION_PVALUE_THRESHOLD': { label: 'Coint P-Value Cap', description: 'Maximum p-value to admit a pair (0.05 is standard).' },
};

export function getConfigMetadata(key: string): ConfigMetadata {
  return CONFIG_METADATA[key] || {
    label: key.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, c => c.toUpperCase()),
    description: 'No detailed description available for this technical parameter.'
  };
}
