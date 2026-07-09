'use client'

import type { HandCell } from '@gto/types'

interface RangeGridProps {
  range: HandCell[]
  onHandClick?: (hand: string) => void
  selectedHand?: string | null
  actionFilter?: string | null
}

const RANKS = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2']
const GRAY = '#2a2e32'

export function RangeGrid({ range, onHandClick, selectedHand, actionFilter }: RangeGridProps) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: `repeat(13, 48px)`,
        gridTemplateRows: `repeat(13, 48px)`,
        gap: 1,
        background: '#2a2e32',
        borderRadius: 8,
        overflow: 'hidden',
      }}
    >
      {RANKS.flatMap((r1, i) =>
        RANKS.map((r2, j) => {
          const isPair = i === j
          const isSuited = i < j
          const handKey = isPair ? `${r1}${r2}` : isSuited ? `${r1}${r2}s` : `${r2}${r1}o`
          const cell = range.find(h => h.hand === handKey)
          const action = cell?.action || 'fold'
          const freq = cell?.frequency || 0
          const isSelected = selectedHand === handKey

          const color =
            action === 'fold' || freq === 0 ? GRAY
            : action.includes('all_in') ? '#c0392b'
            : action.includes('raise') || action.includes('bet') ? '#e74c3c'
            : action.includes('call') || action.includes('check') ? '#2ecc71'
            : GRAY

          const opacity = actionFilter && cell?.action !== actionFilter ? 0.08 : 1

          return (
            <button
              key={handKey}
              onClick={() => onHandClick?.(handKey)}
              style={{
                width: 48,
                height: 48,
                border: isSelected ? '2px solid #fff' : '1px solid transparent',
                borderRadius: 4,
                cursor: 'pointer',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 12,
                fontWeight: 600,
                color: action === 'fold' || freq === 0 ? '#555' : '#fff',
                opacity,
                background:
                  action !== 'fold' && freq > 0 && freq < 1
                    ? `linear-gradient(to right, ${color} ${(freq * 100).toFixed(0)}%, ${GRAY} ${(freq * 100).toFixed(0)}%)`
                    : color,
                transition: 'opacity 0.15s, filter 0.15s',
              }}
            >
              <span style={{ fontSize: 13 }}>{handKey}</span>
              {freq > 0 && freq < 1 && (
                <span style={{ fontSize: 10, background: 'rgba(0,0,0,0.45)', padding: '0 3px', borderRadius: 3 }}>
                  {(freq * 100).toFixed(0)}%
                </span>
              )}
            </button>
          )
        })
      )}
    </div>
  )
}
