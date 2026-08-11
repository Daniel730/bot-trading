import React from 'react'

type SkeletonProps = {
  width?: string | number
  height?: string | number
  className?: string
  style?: React.CSSProperties
  rounded?: boolean
}

/** Single shimmer block — decorative; hide from AT with aria-hidden. */
export function Skeleton({
  width = '100%',
  height = 12,
  className = '',
  style,
  rounded = true,
}: SkeletonProps) {
  return (
    <span
      aria-hidden="true"
      className={`skeleton-block${rounded ? ' skeleton-rounded' : ''} ${className}`.trim()}
      style={{ width, height, ...style }}
    />
  )
}

type PanelSkeletonProps = {
  rows?: number
  className?: string
  label?: string
}

/** Layout-parity placeholder for panel bodies while data loads. */
export function PanelSkeleton({ rows = 4, className = '', label = 'Loading' }: PanelSkeletonProps) {
  return (
    <div
      className={`panel-skeleton ${className}`.trim()}
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, index) => (
        <div className="panel-skeleton-row" key={index}>
          <Skeleton width={`${72 - index * 8}%`} height={14} />
          <Skeleton width={48} height={14} />
        </div>
      ))}
    </div>
  )
}

type ContentRevealProps = {
  loading: boolean
  skeleton?: React.ReactNode
  children: React.ReactNode
  className?: string
}

/**
 * Cross-fade skeleton → content (~180ms). Honors prefers-reduced-motion via CSS.
 */
export function ContentReveal({
  loading,
  skeleton,
  children,
  className = '',
}: ContentRevealProps) {
  return (
    <div className={`content-reveal ${loading ? 'is-loading' : 'is-ready'} ${className}`.trim()}>
      {loading ? (
        <div className="content-reveal-layer" key="skeleton">
          {skeleton ?? <PanelSkeleton />}
        </div>
      ) : (
        <div className="content-reveal-layer" key="content">
          {children}
        </div>
      )}
    </div>
  )
}
