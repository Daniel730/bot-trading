import { describe, expect, it } from 'vitest';
import { getRuntimeApiBase } from './runtimeUrl';

const runtimeLocation = (url: string) => {
  const parsed = new URL(url);
  return {
    hostname: parsed.hostname,
    origin: parsed.origin,
    port: parsed.port,
    protocol: parsed.protocol,
  };
};

describe('getRuntimeApiBase', () => {
  it('uses configured API URLs first', () => {
    expect(
      getRuntimeApiBase('http://localhost:8080', runtimeLocation('http://localhost:3000/')),
    ).toBe('http://localhost:8080');
  });

  it('points localhost development at the backend port', () => {
    expect(getRuntimeApiBase(undefined, runtimeLocation('http://localhost:3000/'))).toBe('http://localhost:8080');
  });

  it('keeps remote nginx deployments on the same origin', () => {
    expect(getRuntimeApiBase(undefined, runtimeLocation('http://203.0.113.50:3000/'))).toBe(
      'http://203.0.113.50:3000',
    );
  });
});
