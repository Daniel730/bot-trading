import { describe, expect, it } from 'vitest'
import { PANEL_DURATION_MS, panelMountVariants, prefersReducedMotion } from '../motion/principles'

describe('motion principles tokens', () => {
  it('keeps panel enter under Emil productivity budget', () => {
    expect(PANEL_DURATION_MS).toBeLessThanOrEqual(300)
    expect(panelMountVariants.initial).toMatchObject({ opacity: 0 })
  })

  it('prefersReducedMotion is safe in jsdom', () => {
    expect(typeof prefersReducedMotion()).toBe('boolean')
  })
})
