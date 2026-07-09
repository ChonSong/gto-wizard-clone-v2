/** Design tokens — GTO Wizard dark theme */
export const tokens = {
  colors: {
    bg: '#0e0e0f',
    panel: '#1a1c1e',
    border: '#2a2e32',
    text: '#d7d7d7',
    muted: '#8a8f98',
    teal: '#00b894',
    green: '#2ecc71',
    red: '#e74c3c',
    orange: '#e67e22',
    blue: '#3498db',
    yellow: '#f1c40f',
    white: '#ffffff',
  },
  font: {
    family: 'Inter, system-ui, sans-serif',
  },
  nav: {
    height: 48,
    sidebarWidth: 220,
  },
} as const

export const ACTION_COLORS: Record<string, string> = {
  raise: tokens.colors.red,
  bet: tokens.colors.red,
  all_in: '#c0392b',
  call: tokens.colors.green,
  check: tokens.colors.green,
  fold: tokens.colors.blue,
}
