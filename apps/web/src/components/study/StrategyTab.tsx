'use client'

import { useState } from 'react'
import { ACTION_COLORS } from '@/lib/tokens'

interface HandCell {
  hand: string
  action: string
  frequency: number
  equity?: number
}

interface StrategyTabProps {
  rangeData: HandCell[]
  onHandClick?: (hand: string) => void
}

type Metric = 'strategy' | 'equity' | 'ev' | 'all'

function classifyAction(action: string): 'fold' | 'call' | 'raise' | 'all_in' {
  if (action === 'fold') return 'fold'
  if (action === 'all_in' || action.includes('all_in')) return 'all_in'
  if (action.startsWith('raise') || action.startsWith('bet')) return 'raise'
  return 'call'
}

function getActionColor(action: string): string {
  if (action === 'fold') return '#2a2e32'
  if (action === 'all_in' || action.includes('all_in')) return '#c0392b'
  if (action.startsWith('raise') || action.startsWith('bet')) return ACTION_COLORS.raise
  if (action.startsWith('call') || action === 'check') return ACTION_COLORS.call
  return '#2a2e32'
}

// Simplified EV calculation
function computeEV(action: string, freq: number, pot: number = 1.5): number {
  if (action === 'fold' || freq === 0) return 0
  if (action.startsWith('raise') || action.startsWith('bet')) return pot * 0.6 * freq
  if (action === 'all_in') return pot * 0.65 * freq
  return pot * 0.5 * freq
}

const RANKS = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2'] as const

export function StrategyTab({ rangeData, onHandClick }: StrategyTabProps) {
  const [metric, setMetric] = useState<Metric>('strategy')

  const cellMap = new Map(rangeData.map(h => [h.hand, h]))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Metric toggle */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <span style={{ fontSize: 11, fontWeight: 600, color: '#8a8f98', textTransform: 'uppercase' }}>
          Overlay:{' '}
        </span>
        {(['strategy', 'equity', 'ev', 'all'] as const).map(m => (
          <button
            key={m}
            onClick={() => setMetric(m)}
            style={{
              padding: '4px 10px',
              borderRadius: 4,
              border: 'none',
              background: metric === m ? '#3498db' : 'rgba(255,255,255,0.04)',
              color: metric === m ? '#fff' : '#8a8f98',
              cursor: 'pointer',
              fontSize: 12,
              fontWeight: 600,
              textTransform: 'capitalize',
            }}
          >
            {m}
          </button>
        ))}
      </div>

      {/* Strategy matrix */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: `repeat(13, 40px)`,
          gridTemplateRows: `repeat(13, 40px)`,
          gap: 1,
          background: '#2a2e32',
          borderRadius: 8,
          overflow: 'hidden',
          width: 'fit-content',
        }}
      >
        {RANKS.flatMap((r1, i) =>
          RANKS.map((r2, j) => {
            const isPair = i === j
            const isSuited = i < j
            const handKey = isPair ? `${r1}${r2}` : isSuited ? `${r1}${r2}s` : `${r2}${r1}o`
            const cell = cellMap.get(handKey)
            const action = cell?.action || 'fold'
            const freq = cell?.frequency || 0
            const equity = cell?.equity || 0.5
            const ev = computeEV(action, freq)
            const actionType = classifyAction(action)

            const showStrategy = metric === 'strategy' || metric === 'all'
            const showEquity = metric === 'equity' || metric === 'all'
            const showEV = metric === 'ev' || metric === 'all'

            const bgColor = showStrategy ? getActionColor(action) : showEquity
              ? `hsl(${equity * 120}, 60%, 30%)`  // green=high, red=low
              : showEV
              ? `hsl(${ev > 0.5 ? 120 : 0}, ${Math.min(ev * 100, 60)}%, 30%)`
              : '#2a2e32'

            return (
              <button
                key={handKey}
                onClick={() => onHandClick?.(handKey)}
                style={{
                  width: 40,
                  height: 40,
                  border: '1px solid transparent',
                  borderRadius: 0,
                  cursor: 'pointer',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 9,
                  fontWeight: 600,
                  color: freq === 0 && metric === 'strategy' ? '#555' : '#fff',
                  background: bgColor,
                  transition: 'filter 0.15s',
                }}
                onMouseEnter={e => { e.currentTarget.style.filter = 'brightness(1.3)' }}
                onMouseLeave={e => { e.currentTarget.style.filter = 'brightness(1)' }}
                title={`${handKey}: ${action} ${(freq * 100).toFixed(0)}% | EQ ${(equity * 100).toFixed(0)}%`}
              >
                <span style={{ fontSize: 10, fontWeight: 700 }}>{handKey}</span>
                {showStrategy && freq > 0 && freq < 1 && (
                  <span style={{ fontSize: 8 }}>{(freq * 100).toFixed(0)}%</span>
                )}
                {showEquity && (
                  <span style={{ fontSize: 8, opacity: 0.8 }}>{(equity * 100).toFixed(0)}%</span>
                )}
                {showEV && ev > 0 && (
                  <span style={{ fontSize: 8, opacity: 0.7 }}>{ev.toFixed(2)}</span>
                )}
              </button>
            )
          })
        )}
      </div>

      {/* Legend */}
      <div style={{ display: 'flex', gap: 16, fontSize: 11, color: '#8a8f98', flexWrap: 'wrap' }}>
        {metric === 'strategy' || metric === 'all' ? (
          <>
            <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ width: 10, height: 10, background: '#e74c3c' }} /> Raise
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ width: 10, height: 10, background: '#2ecc71' }} /> Call
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ width: 10, height: 10, background: '#2a2e32' }} /> Fold
            </span>
          </>
        ) : metric === 'equity' ? (
          <span>Green = high equity, Red = low equity</span>
        ) : metric === 'ev' ? (
          <span>Bright = high expected value</span>
        ) : null}
      </div>
    </div>
  )
}
