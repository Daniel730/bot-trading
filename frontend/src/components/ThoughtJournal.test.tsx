import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import ThoughtJournal from './ThoughtJournal';
import type { ThoughtTelemetry } from '../services/api';

describe('ThoughtJournal', () => {
  it('renders "NO_THOUGHTS_CAPTURED" when thoughts are empty', () => {
    render(<ThoughtJournal thoughts={[]} />);
    expect(screen.getByText('NO_THOUGHTS_CAPTURED')).toBeInTheDocument();
  });

  it('renders thoughts correctly', () => {
    const mockThoughts: ThoughtTelemetry[] = [
      { agent_name: 'BULL', thought: 'Price is rising', verdict: 'BULLISH', signal_id: '123' }
    ];
    render(<ThoughtJournal thoughts={mockThoughts} />);
    expect(screen.getByText('BULL')).toBeInTheDocument();
    expect(screen.getByText('Price is rising')).toBeInTheDocument();
  });

  it('renders multiple thoughts in reverse order', () => {
    const mockThoughts: ThoughtTelemetry[] = [
      { agent_name: 'FIRST', thought: 'First thought', verdict: 'NEUTRAL', signal_id: '1' },
      { agent_name: 'SECOND', thought: 'Second thought', verdict: 'BULLISH', signal_id: '2' }
    ];
    render(<ThoughtJournal thoughts={mockThoughts} />);
    const elements = screen.getAllByText(/thought/);
    expect(elements[0]).toHaveTextContent('Second thought');
    expect(elements[1]).toHaveTextContent('First thought');
  });

  it('handles 100 thoughts without crashing', () => {
    const manyThoughts: ThoughtTelemetry[] = Array.from({ length: 100 }, (_, i) => ({
      agent_name: `AGENT_${i}`,
      thought: `Thought ${i}`,
      verdict: 'NEUTRAL',
      signal_id: `${i}`
    }));
    const { container } = render(<ThoughtJournal thoughts={manyThoughts} />);
    expect(container.querySelectorAll('.thought-journal > div').length).toBe(100);
  });
});
