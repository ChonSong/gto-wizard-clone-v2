'use client'

type Position = 'UTG' | 'HJ' | 'CO' | 'BTN' | 'SB' | 'BB'

interface PositionSelectorProps {
  positions: Position[]
  active: Position
  onChange: (pos: Position) => void
}

export function PositionSelector({ positions, active, onChange }: PositionSelectorProps) {
  return (
    <div style={{ display: 'flex', gap: 4 }}>
      {positions.map(pos => (
        <button
          key={pos}
          onClick={() => onChange(pos)}
          style={{
            padding: '8px 14px',
            borderRadius: 6,
            border: pos === active ? '1px solid #00b894' : '1px solid transparent',
            background: pos === active ? '#00b89415' : 'rgba(255,255,255,0.04)',
            color: pos === active ? '#00b894' : '#8a8f98',
            fontWeight: pos === active ? 600 : 400,
            cursor: 'pointer',
            fontSize: 13,
            transition: 'all 0.15s',
          }}
        >
          {pos}
        </button>
      ))}
    </div>
  )
}
