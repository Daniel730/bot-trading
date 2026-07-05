import { describe, expect, it } from 'vitest';
import { getConfigMetadata } from './configMetadata';

describe('config metadata', () => {
  it('explains shadow paper mode versus Alpaca paper broker mode', () => {
    const paperTrading = getConfigMetadata('PAPER_TRADING').description;
    const alpacaBaseUrl = getConfigMetadata('ALPACA_BASE_URL').description;

    expect(paperTrading).toContain('local shadow mode');
    expect(paperTrading).toContain('PAPER_TRADING=false');
    expect(paperTrading).toContain('https://paper-api.alpaca.markets');
    expect(alpacaBaseUrl).toContain('Alpaca paper broker');
    expect(alpacaBaseUrl).toContain('https://paper-api.alpaca.markets');
  });
});
