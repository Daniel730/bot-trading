import React, { useState } from 'react';
import { act, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useAutoDismiss } from './useAutoDismiss';

function Harness() {
  const [message, setMessage] = useState<string | null>('Saved');
  useAutoDismiss(message, setMessage, 1000);
  return message ? <div>{message}</div> : <div>cleared</div>;
}

describe('useAutoDismiss', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('clears transient messages after the configured delay', () => {
    vi.useFakeTimers();

    render(<Harness />);

    expect(screen.getByText('Saved')).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(screen.getByText('cleared')).toBeInTheDocument();
    expect(screen.queryByText('Saved')).not.toBeInTheDocument();
  });
});
