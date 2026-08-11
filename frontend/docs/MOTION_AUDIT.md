# Motion audit notes (#134)

Short SaaS-dashboard audit (Emil primary, Jakub secondary):

| Surface | Finding | Action |
|---|---|---|
| Telemetry ticks / thoughts stream | High frequency | Do **not** animate list ticks |
| Page switches | Occasional | `PanelMount` ~200ms fade+raise |
| 2FA confirm modal | Occasional | `ModalShell` overlay fade |
| IntelligenceHub cards | Occasional mount | Dropped lateral slide + glow; short y/opacity |
| Startup progress bars | Functional | Keep width transitions; CSS respects reduced-motion |
| PairsPanel Expand rows | Existing AnimatePresence | Keep; already occasional |

`prefers-reduced-motion` covered via `useReducedMotion` in wrappers + CSS skeleton/content rules from #132.
