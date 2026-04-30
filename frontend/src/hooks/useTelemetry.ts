import { useState, useEffect, useRef, useCallback } from 'react';
import type { RiskTelemetry, ThoughtTelemetry, TelemetryMessage } from '../services/api';
import { getRuntimeApiBase } from '../services/runtimeUrl';

const WS_BASE = getRuntimeApiBase(import.meta.env.VITE_API_URL).replace('http', 'ws');

export const useTelemetry = (token: string | null, sessionToken?: string | null) => {
  const [isConnected, setIsConnected] = useState(false);
  const [risk, setRisk] = useState<RiskTelemetry | null>(null);
  const [thoughts, setThoughts] = useState<ThoughtTelemetry[]>([]);
  const [botState, setBotState] = useState<string>('IDLE');
  
  const ws = useRef<WebSocket | null>(null);
  const reconnectTimeout = useRef<number | null>(null);
  const retryCount = useRef(0);
  const connectRef = useRef<() => void>(() => {});

  const connect = useCallback(() => {
    if (!sessionToken) return;

    const url = new URL('/ws/telemetry', WS_BASE);
    const socket = new WebSocket(url.toString());

    socket.onopen = () => {
      console.log('Telemetry WebSocket Connected');
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
            setThoughts(prev => {
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

    socket.onclose = () => {
      console.log('Telemetry WebSocket Disconnected');
      setIsConnected(false);
      
      // Exponential backoff reconnect
      const delay = Math.min(1000 * Math.pow(2, retryCount.current), 30000);
      reconnectTimeout.current = window.setTimeout(() => {
        retryCount.current++;
        connectRef.current();
      }, delay);
    };

    socket.onerror = (err) => {
      console.error('Telemetry WebSocket Error:', err);
      socket.close();
    };

    ws.current = socket;
  }, [token, sessionToken]);

  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  useEffect(() => {
    connect();
    return () => {
      if (ws.current) ws.current.close();
      if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current);
    };
  }, [connect]);

  return { isConnected, risk, thoughts, botState, ws };
};
