'use client'

import type { PositionStats } from '@/hooks/useAggregateStats'
import type { Position } from '@gto/types'
import { ACTION_COLORS, tokens } from '@/lib/tokens'

const POSITIONS: Position[] = ['UTG', 'HJ', 'CO', 'BTN', 'SB', 'BB']

interface AggregateFlipStripProps {
  stats: Record<Position, PositionStats>
  activePosition: Position
  onPositionClick: (position: Position) => void
}

function StatBar({ value, label, color, action }: { value: number; label: string; color: string; action: string }) {
  return (
    <div data-action={action} style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 10 }}>
      <span style={{ color: tokens.colors.muted, width: 32, textAlign: 'right', flexShrink: 0 }}>{label}</span>
      <div
        style={{
          flex: 1,
          height: 6,
          background: tokens.colors.border,
          borderRadius: 3,
          overflow: 'hidden',
          minWidth: 40,
        }}
      >
        <div
          style={{
            width: `${Math.min(value, 100)}%`,
            height: '100%',
            background: color,
            borderRadius: 3,
            transition: 'width 0.3s ease',
          }}
        />
      </div>
      <span style={{ color: tokens.colors.text, width: 28, textAlign: 'left', flexShrink: 0 }}>
        {value.toFixed(0)}%
      </span>
    </div>
  )
}

function PositionCount({ value }: { value: number }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 10 }}>
      <span style={{ color: tokens.colors.muted, width: 32, textAlign: 'right', flexShrink: 0 }} />
      <div style={{ flex: 1, minWidth: 40 }} />
      <span style={{ color: tokens.colors.text, width: 28, textAlign: 'left', flexShrink: 0 }}>
        {value} combos
      </span>
    </div>
  )
}

export function AggregateFlipStrip({ stats, activePosition, onPositionClick }: AggregateFlipStripProps) {
  if (!stats) return null

  const totalCombos = POSITIONS.reduce((sum, p) => sum + (stats[p]?.combos || 0), 0)
  if (totalCombos === 0) return null

  return (
    <div
      data-testid="aggregate-flip-strip"
      style={{
        width: '100%',
        maxWidth: 800,
        marginTop: 20,
      }}
    >
      <h3
        style={{
          fontSize: 12,
          fontWeight: 600,
          color: tokens.colors.muted,
          textTransform: 'uppercase',
          marginBottom: 10,
        }}
      >
        Aggregate Stats by Position
      </h3>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: `repeat(${POSITIONS.length}, 1fr)`,
          gap: 8,
        }}
      >
        {POSITIONS.map((pos) => {
          const s = stats[pos]
          if (!s) return null
          const isActive = pos === activePosition

          return (
            <button
              key={pos}
              data-testid="position-chip"
              data-active={isActive ? 'true' : 'false'}
              onClick={() => onPositionClick(pos)}
              style={{
                background: isActive ? `${tokens.colors.teal}12` : tokens.colors.panel,
                border: isActive ? `1px solid ${tokens.colors.teal}` : `1px solid ${tokens.colors.border}`,
                borderRadius: 8,
                padding: '10px 8px',
                cursor: 'pointer',
                display: 'flex',
                flexDirection: 'column',
                gap: 5,
                transition: 'background 0.15s, border-color 0.15s',
                textAlign: 'left',
              }}
            >
              <div
                style={{
                  fontSize: 13,
                  fontWeight: 700,
                  color: isActive ? tokens.colors.teal : tokens.colors.text,
                  textAlign: 'center',
                  marginBottom: 2,
                }}
              >
                {pos}
              </div>
              <StatBar value={s.raisePct} label="RSE" color={ACTION_COLORS.raise} action="raise" />
              <StatBar value={s.callPct} label="CLL" color={ACTION_COLORS.call} action="call" />
              <StatBar value={s.foldPct} label="FLD" color={ACTION_COLORS.fold} action="fold" />
              <PositionCount value={s.combos} />
            </button>
          )
        })}
      </div>
    </div>
  )
}
