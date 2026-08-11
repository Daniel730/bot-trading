/**
 * Shared motion tokens for the ops console (#134).
 * SaaS dashboard weighting: Emil primary (restraint/speed), Jakub secondary (polish).
 * High-frequency telemetry ticks must not use these animations.
 */
import type { Transition, Variants } from 'framer-motion'

export const PANEL_EASE: [number, number, number, number] = [0.22, 1, 0.36, 1]
export const PANEL_DURATION_MS = 200

export const panelTransition: Transition = {
  duration: PANEL_DURATION_MS / 1000,
  ease: PANEL_EASE,
}

export const panelMountVariants: Variants = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -6 },
}

export const modalVariants: Variants = {
  initial: { opacity: 0, y: 10, scale: 0.98 },
  animate: { opacity: 1, y: 0, scale: 1 },
  exit: { opacity: 0, y: 6, scale: 0.99 },
}

export const listItemVariants: Variants = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -4 },
}

/** Prefer this over hardcoding — returns true when OS asks for reduced motion. */
export function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return false
  }
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

export function motionSafeTransition(transition: Transition = panelTransition): Transition {
  return prefersReducedMotion() ? { duration: 0 } : transition
}
