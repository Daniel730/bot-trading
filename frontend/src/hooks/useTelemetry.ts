import { useState, useEffect, useRef, useCallback } from 'react';
import { ApiError, type RiskTelemetry, type ThoughtTelemetry, type TelemetryMessage } from '../services/api';
import { getRuntimeApiBase } from '../services/runtimeUrl';

export type TelemetryRisk = RiskTelemetry;
export type TelemetryThought = ThoughtTelemetry;

const WS_BASE = getRuntimeApiBase(import.meta.env.VITE_API_URL).replace('http', 'ws');
/** Backend closes unauthorized sockets with this code (see dashboard_service websocket_endpoint). */
const WS_AUTH_REJECT_CODE = 4003;

export const useTelemetry = (token: string | null, sessionToken?: string | null) => {
  const [isConnected, setIsConnected] = useState(false);
  const [risk, setRisk] = useState<RiskTelemetry | null>(null);
  const [thoughts, setThoughts] = useState<ThoughtTelemetry[]>([]);
  const [botState, setBotState] = useState<string>('IDLE');
  const [authError, setAuthError] = useState<ApiError | null>(null);

  const ws = useRef<WebSocket | null>(null);
  const reconnectTimeout = useRef<number | null>(null);
  const retryCount = useRef(0);
  const connectRef = useRef<() => void>(() => {});
  const intentionalClose = useRef(false);

  const connect = useCallback(() => {
    if (!sessionToken) return;

    // Never put session/security tokens in the WebSocket URL (proxy/access-log leak surface).
    const url = new URL('/ws/telemetry', WS_BASE);
    const socket = new WebSocket(url.toString());
    intentionalClose.current = false;

    socket.onopen = () => {
      if (typeof socket.send === 'function') {
        socket.send(JSON.stringify({ type: 'auth', token: token || undefined, session: sessionToken }));
      }
      setIsConnected(true);
      retryCount.current = 0;
    };

    socket.onmessage = (event) => {
      try {
        const message: TelemetryMessage = JSON.parse(event.data);

        switch (message.type) {
          case 'risk':
            setRisk(message.data as RiskTelemetry);
            break;
          case 'thought':
            setThoughts((prev) => {
              const newThoughts = [...prev, message.data as ThoughtTelemetry];
              return newThoughts.slice(-100); // Ring-buffer: keep last 100
            });
            break;
          case 'bot_state':
            setBotState(message.data.state || 'IDLE');
            break;
        }
      } catch (err) {
        console.error('Failed to parse telemetry message:', err);
      }
    };

    socket.onclose = (event) => {
      setIsConnected(false);

      if (intentionalClose.current) return;

      // Auth rejected — stop reconnect storms and surface a fail-closed session clear.
      if (event.code === WS_AUTH_REJECT_CODE) {
        setAuthError(new ApiError(401, 'Dashboard session expired. Please log in again.'));
        return;
      }

      const delay = Math.min(1000 * Math.pow(2, retryCount.current), 30000);
      reconnectTimeout.current = window.setTimeout(() => {
        retryCount.current++;
        connectRef.current();
      }, delay);
    };

    socket.onerror = () => {
      socket.close();
    };

    ws.current = socket;
  }, [token, sessionToken]);

  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  useEffect(() => {
    if (!sessionToken) {
      intentionalClose.current = true;
      if (ws.current) ws.current.close();
      if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current);
      return;
    }

    connect();
    return () => {
      intentionalClose.current = true;
      if (ws.current) ws.current.close();
      if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current);
    };
  }, [connect, sessionToken]);

  // Clear auth errors by derivation when the session is gone (avoids setState-in-effect).
  return {
    isConnected: sessionToken ? isConnected : false,
    risk,
    thoughts,
    botState,
    authError: sessionToken ? authError : null,
    ws,
  };
};
