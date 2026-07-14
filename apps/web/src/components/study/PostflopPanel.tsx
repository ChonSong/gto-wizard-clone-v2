'use client'

interface PostflopAction {
  action: string
  frequency: number
  ev: number
}

interface PostflopPanelProps {
  actions: PostflopAction[]
}

function getActionColor(action: string): string {
  if (action === 'fold') return '#3498db'
  if (action.startsWith('all_in')) return '#c0392b'
  if (action.startsWith('raise') || action.startsWith('bet')) return '#e74c3c'
  if (action.startsWith('call') || action === 'check') return '#2ecc71'
  return '#8a8f98'
}

function getActionIcon(action: string): string {
  if (action === 'fold') return '✋'
  if (action.startsWith('all_in')) return '💥'
  if (action.startsWith('raise') || action.startsWith('bet')) return '⬆️'
  if (action.startsWith('call')) return '📞'
  if (action === 'check') return '✓'
  return '•'
}

export function PostflopPanel({ actions }: PostflopPanelProps) {
  if (actions.length === 0) {
    return (
      <div
        data-testid="postflop-empty"
        style={{
          padding: 32, textAlign: 'center', color: '#8a8f98', fontSize: 14,
        }}
      >
        No postflop strategy loaded. Select a board to see actions.
      </div>
    )
  }

  const maxFreq = Math.max(...actions.map(a => a.frequency))

  return (
    <div
      data-testid="postflop-panel"
      style={{
        display: 'flex', flexDirection: 'column', gap: 8,
        padding: 16, background: '#1a1c1e', borderRadius: 8,
        border: '1px solid #2a2e32', minWidth: 400,
      }}
    >
      <h4 style={{ margin: 0, fontSize: 13, fontWeight: 600, color: '#d7d7d7' }}>
        GTO Strategy
      </h4>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {actions.map((act, i) => (
          <div
            key={`${act.action}-${i}`}
            data-testid={`postflop-action-${act.action}`}
            style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '8px 12px', borderRadius: 6,
              background: '#0e0e0f',
              border: '1px solid #2a2e32',
            }}
          >
            <span style={{ fontSize: 14, width: 24, textAlign: 'center' }}>
              {getActionIcon(act.action)}
            </span>

            <span style={{
              fontSize: 12, fontWeight: 600, width: 80,
              color: getActionColor(act.action), textTransform: 'uppercase',
            }}>
              {act.action.replace(/_\d+\.?\d*bb$/, '')}
            </span>

            {/* Frequency bar */}
            <div style={{
              flex: 1, height: 16, background: '#2a2e32', borderRadius: 4, overflow: 'hidden',
              position: 'relative',
            }}>
              <div style={{
                position: 'absolute', left: 0, top: 0, bottom: 0,
                width: `${(act.frequency / maxFreq) * 100}%`,
                background: getActionColor(act.action), opacity: 0.3,
                borderRadius: 4,
              }} />
              <span style={{
                position: 'absolute', left: 4, top: '50%', transform: 'translateY(-50%)',
                fontSize: 10, fontWeight: 700, color: '#fff',
              }}>
                {(act.frequency * 100).toFixed(1)}%
              </span>
            </div>

            {/* EV display */}
            <span style={{
              fontSize: 11, width: 40, textAlign: 'right', color: '#8a8f98',
            }}>
              {act.ev > 0 ? '+' : ''}{act.ev.toFixed(2)}
            </span>
          </div>
        ))}
      </div>

      {/* Action mix summary */}
      <div style={{
        display: 'flex', gap: 12, marginTop: 8, padding: '8px 12px',
        background: '#0e0e0f', borderRadius: 6, border: '1px solid #2a2e32',
      }}>
        {actions.slice(0, 4).map((act, i) => (
          <div key={`summary-${i}`} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11 }}>
            <span style={{
              width: 8, height: 8, borderRadius: '50%',
              background: getActionColor(act.action),
            }} />
            <span style={{ color: '#8a8f98' }}>
              {act.action.replace(/_\d+\.?\d*bb$/, '')}
            </span>
            <span style={{ fontWeight: 600 }}>
              {(act.frequency * 100).toFixed(0)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
