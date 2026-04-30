import React from 'react';
import { ChartPoint } from '../services/api';
import { sparklinePath } from '../utils/formatters';

export function LineMiniChart({ points, color }: { points: ChartPoint[]; color: string }) {
  const values = points.map((point) => point.value ?? 0);
  const path = sparklinePath(values, 300, 90);
  return (
    <svg viewBox="0 0 300 90" className="mini-chart">
      <path d={path} fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

export function DualBarChart({ points }: { points: ChartPoint[] }) {
  const max = Math.max(1, ...points.flatMap((point) => [point.wins ?? 0, point.losses ?? 0]));
  return (
    <div className="dual-bars">
      {points.slice(-12).map((point) => (
        <div key={point.timestamp} className="dual-bar-item">
          <div className="dual-bar-stack">
            <div className="dual-bar win" style={{ height: `${((point.wins ?? 0) / max) * 100}%` }} />
            <div className="dual-bar loss" style={{ height: `${((point.losses ?? 0) / max) * 100}%` }} />
          </div>
          <span>{point.timestamp.slice(5)}</span>
        </div>
      ))}
    </div>
  );
}

export function SectionHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: React.ReactNode }) {
  return (
    <div className="section-header">
      <div>
        <h2>{title}</h2>
        {subtitle ? <p>{subtitle}</p> : null}
      </div>
      {action}
    </div>
  );
}
