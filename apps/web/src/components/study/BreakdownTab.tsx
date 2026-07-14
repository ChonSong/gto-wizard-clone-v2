'use client'

import { useState, useMemo } from 'react'
import { ACTION_COLORS } from '@/lib/tokens'

interface HandCell {
  hand: string
  action: string
  frequency: number
  equity?: number
}

interface BreakdownTabProps {
  rangeData: HandCell[]
  onHandClick?: (hand: string) => void
}

type Category = 'all' | 'premium' | 'strong' | 'marginal' | 'bluff'

const CATEGORY_RANGES: Record<Category, { min: number; max: number }> = {
  all: { min: 0, max: 1 },
  premium: { min: 0.7, max: 1 },
  strong: { min: 0.6, max: 0.699 },
  marginal: { min: 0.5, max: 0.599 },
  bluff: { min: 0, max: 0.499 },
}

function classifyHand(hand: string): 'pair' | 'suited' | 'offsuit' {
  if (hand.length === 2) return 'pair'
  if (hand.endsWith('s')) return 'suited'
  return 'offsuit'
}

function getActionColor(action: string): string {
  if (action === 'fold') return '#2a2e32'
  if (action === 'all_in' || action.includes('all_in')) return '#c0392b'
  if (action.startsWith('raise') || action.startsWith('bet')) return ACTION_COLORS.raise
  if (action.startsWith('call') || action === 'check') return ACTION_COLORS.call
  return '#2a2e32'
}

export function BreakdownTab({ rangeData, onHandClick }: BreakdownTabProps) {
  const [category, setCategory] = useState<Category>('all')
  const [handClass, setHandClass] = useState<'all' | 'pair' | 'suited' | 'offsuit'>('all')
  const [showCount, setShowCount] = useState(20)

  const sortedHands = useMemo(() => {
    const range = CATEGORY_RANGES[category]
    return [...rangeData]
      .filter(h => (h.equity || 0.5) >= range.min && (h.equity || 0.5) <= range.max)
      .filter(h => handClass === 'all' || classifyHand(h.hand) === handClass)
      .sort((a, b) => (b.equity || 0.5) - (a.equity || 0.5))
  }, [rangeData, category, handClass])

  const displayedHands = sortedHands.slice(0, showCount)

  const totalCombos = sortedHands.length
  const avgEquity = sortedHands.length > 0
    ? sortedHands.reduce((sum, h) => sum + (h.equity || 0.5), 0) / sortedHands.length
    : 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, padding: '16px 0' }}>
      {/* Category / hand class filters */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <span style={{ fontSize: 11, fontWeight: 600, color: '#8a8f98', textTransform: 'uppercase' }}>
          Category:{' '}
        </span>
        {(Object.keys(CATEGORY_RANGES) as Category[]).map(cat => (
          <button
            key={cat}
            onClick={() => setCategory(cat)}
            style={{
              padding: '4px 10px',
              borderRadius: 4,
              border: 'none',
              background: category === cat ? '#00b894' : 'rgba(255,255,255,0.04)',
              color: category === cat ? '#fff' : '#8a8f98',
              cursor: 'pointer',
              fontSize: 12,
              fontWeight: 600,
              textTransform: 'capitalize',
            }}
          >
            {cat}
          </button>
        ))}
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <span style={{ fontSize: 11, fontWeight: 600, color: '#8a8f98', textTransform: 'uppercase' }}>
          Type:{' '}
        </span>
        {(['all', 'pair', 'suited', 'offsuit'] as const).map(cls => (
          <button
            key={cls}
            onClick={() => setHandClass(cls)}
            style={{
              padding: '4px 10px',
              borderRadius: 4,
              border: 'none',
              background: handClass === cls ? '#3498db' : 'rgba(255,255,255,0.04)',
              color: handClass === cls ? '#fff' : '#8a8f98',
              cursor: 'pointer',
              fontSize: 12,
              fontWeight: 600,
              textTransform: 'capitalize',
            }}
          >
            {cls === 'offsuit' ? 'Offsuit' : cls === 'all' ? 'All' : cls}s
          </button>
        ))}
      </div>

      {/* All Combos Summary strip */}
      <div style={{
        background: '#1a1c1e',
        borderRadius: 8,
        padding: 12,
      }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: '#8a8f98', textTransform: 'uppercase', marginBottom: 8 }}>
          All Combos Summary
        </div>
        <div style={{ display: 'flex', gap: 16, fontSize: 12, color: '#d7d7d7', marginBottom: 8 }}>
          <span>{totalCombos} combos</span>
          <span>Avg Equity: <strong>{(avgEquity * 100).toFixed(1)}%</strong></span>
        </div>
        {/* Equity distribution bar */}
        <div style={{
          height: 16,
          borderRadius: 4,
          background: 'linear-gradient(to right, #3498db, #2ecc71, #f1c40f, #e74c3c)',
          position: 'relative',
        }}>
          {displayedHands.map((h, i) => {
            const eq = h.equity || 0.5
            const left = `${eq * 100}%`
            return (
              <div
                key={h.hand}
                style={{
                  position: 'absolute',
                  left,
                  top: 0,
                  bottom: 0,
                  width: 2,
                  background: '#000',
                  opacity: 0.3,
                }}
                title={`${h.hand}: ${(eq * 100).toFixed(0)}%`}
              />
            )
          })}
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: '#555', marginTop: 4 }}>
          <span>0%</span><span>50%</span><span>100%</span>
        </div>
      </div>

      {/* Hand list (sorted by equity) */}
      <div style={{
        maxHeight: 400,
        overflow: 'auto',
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(80px, 1fr))',
        gap: 4,
      }}>
        {displayedHands.map(h => (
          <button
            key={h.hand}
            onClick={() => onHandClick?.(h.hand)}
            style={{
              background: '#1a1c1e',
              border: '1px solid #2a2e32',
              borderRadius: 4,
              padding: '6px 4px',
              cursor: 'pointer',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              fontSize: 11,
              color: '#d7d7d7',
              transition: 'background 0.15s',
            }}
            title={`${h.hand}: ${h.action} ${(h.frequency * 100).toFixed(0)}% • EQ ${(h.equity || 0.5) * 100}%`}
          >
            <span style={{ fontWeight: 600, fontSize: 12 }}>{h.hand}</span>
            <span style={{
              fontSize: 9,
              color: getActionColor(h.action),
              textTransform: 'uppercase',
            }}>
              {h.action.replace(/_\d+bb$/, '').replace(/_\d+\.\d+bb$/, '')}
            </span>
            <span style={{ fontSize: 9, color: '#8a8f98' }}>
              {((h.equity || 0.5) * 100).toFixed(0)}%
            </span>
          </button>
        ))}
      </div>

      {sortedHands.length > showCount && (
        <button
          onClick={() => setShowCount(prev => prev + 50)}
          style={{
            padding: '8px 16px',
            borderRadius: 6,
            border: '1px solid #2a2e32',
            background: 'transparent',
            color: '#8a8f98',
            cursor: 'pointer',
            fontSize: 12,
            alignSelf: 'center',
          }}
        >
          Show more ({sortedHands.length - showCount} remaining)
        </button>
      )}
    </div>
  )
}
