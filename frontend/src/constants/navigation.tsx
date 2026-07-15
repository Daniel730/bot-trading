import React from 'react';
import {
  Activity,
  BarChart3,
  Bot,
  Briefcase,
  Cpu,
  Gauge,
  History,
  Layers,
  Settings as SettingsIcon,
  Wallet,
} from 'lucide-react';

export type Page =
  | 'overview'
  | 'wallet'
  | 'pairs'
  | 'signals'
  | 'positions'
  | 'analytics'
  | 'trades'
  | 'control'
  | 'settings'
  | 'health';

export interface NavItem {
  key: Page;
  label: string;
  icon: React.ReactNode;
  category: 'MONITORING' | 'TRADING' | 'SYSTEM';
}

export const NAV_CATEGORIES: NavItem['category'][] = ['MONITORING', 'TRADING', 'SYSTEM'];

export const NAV_ITEMS: NavItem[] = [
  { key: 'overview', label: 'Overview', icon: <Gauge size={16} />, category: 'MONITORING' },
  { key: 'analytics', label: 'Analytics', icon: <BarChart3 size={16} />, category: 'MONITORING' },
  { key: 'trades', label: 'Trade History', icon: <History size={16} />, category: 'MONITORING' },
  { key: 'wallet', label: 'Wallet', icon: <Wallet size={16} />, category: 'TRADING' },
  { key: 'pairs', label: 'Pairs', icon: <Layers size={16} />, category: 'TRADING' },
  { key: 'signals', label: 'Signals', icon: <Activity size={16} />, category: 'TRADING' },
  { key: 'positions', label: 'Positions', icon: <Briefcase size={16} />, category: 'TRADING' },
  { key: 'control', label: 'Bot Control', icon: <Bot size={16} />, category: 'SYSTEM' },
  { key: 'settings', label: 'Settings', icon: <SettingsIcon size={16} />, category: 'SYSTEM' },
  { key: 'health', label: 'System Health', icon: <Cpu size={16} />, category: 'SYSTEM' },
];

const PAGE_KEYS = new Set<string>(NAV_ITEMS.map((item) => item.key));

export function isPage(value: string): value is Page {
  return PAGE_KEYS.has(value);
}
