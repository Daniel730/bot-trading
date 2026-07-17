import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import IntelligenceHub from './IntelligenceHub';

describe('IntelligenceHub', () => {
  it('displays the actual market regime label (spaces, not underscores)', () => {
    render(<IntelligenceHub regime="TRENDING_UP" confidence={0.82} accuracy={0.71} />);
    expect(screen.getByText('TRENDING UP')).toBeInTheDocument();
    expect(screen.getByText('CLASSIFICATION_CONFIDENCE: 82.0%')).toBeInTheDocument();
  });

  it('shows "—" for confidence/accuracy when telemetry has not arrived', () => {
    render(<IntelligenceHub regime="STABLE" confidence={null} accuracy={null} />);
    expect(screen.getByText('CLASSIFICATION_CONFIDENCE: —')).toBeInTheDocument();
    // Accuracy meter label and state both fall back to em dash rather than 0.0%.
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(2);
    // Never renders a misleading 0.0%.
    expect(screen.queryByText('0.0%')).not.toBeInTheDocument();
  });

  it('renders the accuracy percentage when provided', () => {
    render(<IntelligenceHub regime="VOLATILE" confidence={0.5} accuracy={0.35} />);
    expect(screen.getByText('35.0%')).toBeInTheDocument();
    expect(screen.getByText('LOW ACCURACY WARNING')).toBeInTheDocument();
  });
});
