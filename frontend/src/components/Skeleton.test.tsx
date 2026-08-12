import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ContentReveal, PanelSkeleton, Skeleton } from './Skeleton'

describe('Skeleton system', () => {
  it('marks decorative skeleton blocks aria-hidden', () => {
    const { container } = render(<Skeleton width={40} height={10} />)
    const block = container.querySelector('.skeleton-block')
    expect(block?.getAttribute('aria-hidden')).toBe('true')
  })

  it('exposes polite status on PanelSkeleton', () => {
    render(<PanelSkeleton rows={3} label="Loading pairs" />)
    expect(screen.getByRole('status')).toBeTruthy()
    expect(screen.getByText('Loading pairs')).toBeTruthy()
  })

  it('reveals children when not loading', () => {
    render(
      <ContentReveal loading={false} skeleton={<PanelSkeleton label="wait" />}>
        <div>Ready content</div>
      </ContentReveal>,
    )
    expect(screen.getByText('Ready content')).toBeTruthy()
    expect(screen.queryByText('wait')).toBeNull()
  })
})
