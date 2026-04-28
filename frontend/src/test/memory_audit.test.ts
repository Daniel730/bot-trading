import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { useTelemetry } from '../hooks/useTelemetry';

// Mock WebSocket
class MockWebSocket {
  onopen: any;
  onmessage: any;
  onclose: any;
  onerror: any;
  close = vi.fn();
  url: string;
  constructor(url: string) {
    this.url = url;
    setTimeout(() => this.onopen?.(), 0);
  }
}
(globalThis as any).WebSocket = MockWebSocket;

describe('Telemetry Memory Stability', () => {
  it('strictly enforces 100-entry limit under extreme burst', async () => {
    const { result } = renderHook(() => useTelemetry('fake-token', 'fake-session'));
    
    // Wait for connection
    await new Promise(r => setTimeout(r, 10));

    const wsInstance = (result.current as any).ws?.current;
    
    // Simulate 5,000 messages
    act(() => {
      for (let i = 0; i < 5000; i++) {
        wsInstance.onmessage({
          data: JSON.stringify({
            type: 'thought',
            data: { agent_name: 'TEST', thought: `Msg ${i}`, verdict: 'NEUTRAL' },
            timestamp: new Date().toISOString()
          })
        });
      }
    });

    expect(result.current.thoughts.length).toBe(100);
    expect(result.current.thoughts.at(-1)?.thought).toBe('Msg 4999');
  });
});
