import React from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import {
  listItemVariants,
  motionSafeTransition,
  panelMountVariants,
  panelTransition,
} from '../motion/principles'

type PanelMountProps = {
  id: string
  children: React.ReactNode
  className?: string
}

/** Occasional page/panel mount — ~200ms fade+raise; skipped under reduced motion. */
export function PanelMount({ id, children, className }: PanelMountProps) {
  const reduce = useReducedMotion()
  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={id}
        className={className}
        variants={panelMountVariants}
        initial={reduce ? false : 'initial'}
        animate="animate"
        exit={reduce ? undefined : 'exit'}
        transition={reduce ? { duration: 0 } : panelTransition}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  )
}

type ModalShellProps = {
  open: boolean
  onBackdrop?: () => void
  children: React.ReactNode
  className?: string
}

/** Overlay fade only — child markup (e.g. confirm-window) stays caller-owned. */
export function ModalShell({ open, onBackdrop, children, className = 'overlay' }: ModalShellProps) {
  const reduce = useReducedMotion()
  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          className={className}
          initial={reduce ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={reduce ? undefined : { opacity: 0 }}
          transition={motionSafeTransition({ duration: 0.16 })}
          onClick={(event) => {
            if (event.target === event.currentTarget) onBackdrop?.()
          }}
        >
          {children}
        </motion.div>
      ) : null}
    </AnimatePresence>
  )
}

type ListItemMotionProps = {
  itemKey: string
  children: React.ReactNode
  className?: string
}

/** For rare list add/remove only — never telemetry tick streams. */
export function ListItemMotion({ itemKey, children, className }: ListItemMotionProps) {
  const reduce = useReducedMotion()
  return (
    <motion.div
      layout={!reduce}
      className={className}
      key={itemKey}
      variants={listItemVariants}
      initial={reduce ? false : 'initial'}
      animate="animate"
      exit={reduce ? undefined : 'exit'}
      transition={reduce ? { duration: 0 } : panelTransition}
    >
      {children}
    </motion.div>
  )
}
