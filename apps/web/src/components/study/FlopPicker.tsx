'use client'

import { useState, useMemo } from 'react'
import { tokens } from '@/lib/tokens'

// --- Types ---
export type Card = { rank: string; suit: string }

interface FlopPickerProps {
  flopCards: Card[]
  onFlopChange: (cards: Card[]) => void
}

// --- Constants ---
const RANKS = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2'] as const
const SUITS: { id: string; sym: string; color: string }[] = [
  { id: 's', sym: '♠', color: '#d7d7d7' },
  { id: 'h', sym: '♥', color: '#e74c3c' },
  { id: 'd', sym: '♦', color: '#e74c3c' },
  { id: 'c', sym: '♣', color: '#d7d7d7' },
]

// --- Helpers ---
function randomFlop(): Card[] {
  const pool: Card[] = []
  for (const rank of RANKS) {
    for (const suit of SUITS) {
      pool.push({ rank, suit: suit.id })
    }
  }
  // Fisher-Yates shuffle, pick 3
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [pool[i], pool[j]] = [pool[j], pool[i]]
  }
  return pool.slice(0, 3)
}

function cardKey(c: Card) { return `${c.rank}${c.suit}` }

// --- Component ---
export default function FlopPicker({ flopCards, onFlopChange }: FlopPickerProps) {
  const [open, setOpen] = useState(false)
  const selectedKeys = useMemo(() => new Set(flopCards.map(cardKey)), [flopCards])

  function toggleCard(rank: string, suit: string) {
    const key = rank + suit
    if (selectedKeys.has(key)) {
      // Remove it
      onFlopChange(flopCards.filter(c => cardKey(c) !== key))
    } else if (flopCards.length < 3) {
      // Add it
      onFlopChange([...flopCards, { rank, suit }])
    }
  }

  function handleRandom() {
    onFlopChange(randomFlop())
    setOpen(false)
  }

  function handleClear() {
    onFlopChange([])
  }

  return (
    <div
      style={{
        width: '100%',
        maxWidth: 800,
        marginBottom: 20,
        background: tokens.colors.panel,
        borderRadius: 8,
        border: `1px solid ${tokens.colors.border}`,
        overflow: 'hidden',
      }}
    >
      {/* Header bar — selected cards + actions */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: '10px 16px',
          background: '#0e0e0f',
        }}
      >
        {/* Label */}
        <span style={{ fontSize: 12, fontWeight: 600, color: tokens.colors.muted, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
          Flop
        </span>

        {/* Card slots */}
        {[0, 1, 2].map(i => {
          const card = flopCards[i]
          return (
            <div
              key={i}
              style={{
                width: 40,
                height: 54,
                borderRadius: 4,
                border: card
                  ? `2px solid ${tokens.colors.teal}`
                  : `2px dashed ${tokens.colors.border}`,
                background: card ? tokens.colors.bg : 'transparent',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                transition: 'all 0.15s',
                cursor: card ? 'pointer' : 'default',
              }}
              onClick={() => {
                if (card) {
                  onFlopChange(flopCards.filter((_, j) => j !== i))
                }
              }}
              title={card ? `Remove ${card.rank}${card.suit}` : undefined}
            >
              {card ? (
                <>
                  <span style={{
                    fontSize: 16,
                    fontWeight: 700,
                    color: SUITS.find(s => s.id === card.suit)?.color || '#fff',
                    lineHeight: 1,
                  }}>
                    {card.rank}
                  </span>
                  <span style={{
                    fontSize: 14,
                    color: SUITS.find(s => s.id === card.suit)?.color || '#fff',
                    lineHeight: 1,
                    marginTop: 1,
                  }}>
                    {SUITS.find(s => s.id === card.suit)?.sym || '?'}
                  </span>
                </>
              ) : (
                <span style={{ fontSize: 18, color: tokens.colors.border, lineHeight: 1 }}>
                  ?
                </span>
              )}
            </div>
          )
        })}
        {flopCards.length === 0 && (
          <span style={{ fontSize: 12, color: tokens.colors.muted, fontStyle: 'italic' }}>
            No flop selected
          </span>
        )}

        {/* Spacer */}
        <div style={{ flex: 1 }} />

        {/* Random button */}
        <button
          onClick={handleRandom}
          style={{
            padding: '6px 12px',
            borderRadius: 6,
            border: `1px solid ${tokens.colors.border}`,
            background: tokens.colors.panel,
            color: tokens.colors.text,
            fontSize: 12,
            fontWeight: 600,
            cursor: 'pointer',
            transition: 'all 0.15s',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            whiteSpace: 'nowrap',
          }}
          onMouseEnter={e => { e.currentTarget.style.background = tokens.colors.border }}
          onMouseLeave={e => { e.currentTarget.style.background = tokens.colors.panel }}
        >
          🎲 Random
        </button>

        {/* Clear / picker toggle */}
        {flopCards.length > 0 && (
          <button
            onClick={handleClear}
            title="Clear flop"
            style={{
              padding: '4px 8px',
              borderRadius: 4,
              border: 'none',
              background: 'transparent',
              color: tokens.colors.muted,
              fontSize: 14,
              cursor: 'pointer',
              lineHeight: 1,
            }}
          >
            ✕
          </button>
        )}

        {/* Expand picker */}  
        <button
          onClick={() => setOpen(o => !o)}
          style={{
            padding: '6px 12px',
            borderRadius: 6,
            border: `1px solid ${open ? tokens.colors.teal : tokens.colors.border}`,
            background: open ? `${tokens.colors.teal}12` : tokens.colors.panel,
            color: open ? tokens.colors.teal : tokens.colors.muted,
            fontSize: 12,
            fontWeight: 600,
            cursor: 'pointer',
            transition: 'all 0.15s',
            whiteSpace: 'nowrap',
          }}
        >
          {open ? 'Done' : 'Pick Cards'}
        </button>
      </div>

      {/* Card grid — shown when open */}
      {open && (
        <div style={{ padding: 16 }}>
          <div
            style={{
              display: 'inline-grid',
              gridTemplateColumns: `repeat(4, auto)`,
              gridTemplateRows: `repeat(13, auto)`,
              gap: 4,
              background: tokens.colors.border,
              borderRadius: 6,
              padding: 4,
            }}
          >
            {RANKS.map(rank =>
              SUITS.map(suit => {
                const key = rank + suit.id
                const isSel = selectedKeys.has(key)
                const suitInfo = SUITS.find(s => s.id === suit.id)!
                return (
                  <button
                    key={key}
                    onClick={() => toggleCard(rank, suit.id)}
                    disabled={!isSel && flopCards.length >= 3}
                    style={{
                      width: 44,
                      height: 52,
                      borderRadius: 4,
                      border: isSel
                        ? `2px solid ${tokens.colors.teal}`
                        : '1px solid transparent',
                      background: isSel ? `${tokens.colors.teal}12` : tokens.colors.bg,
                      cursor: (!isSel && flopCards.length >= 3) ? 'not-allowed' : 'pointer',
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 0,
                      transition: 'all 0.1s',
                      opacity: (!isSel && flopCards.length >= 3) ? 0.3 : 1,
                      filter: 'brightness(1)',
                    }}
                    onMouseEnter={e => {
                      if (!isSel && flopCards.length >= 3) return
                      e.currentTarget.style.filter = 'brightness(1.3)'
                    }}
                    onMouseLeave={e => {
                      e.currentTarget.style.filter = 'brightness(1)'
                    }}
                    title={`${rank}${suit.sym}`}
                  >
                    <span style={{
                      fontSize: 14,
                      fontWeight: 700,
                      color: suitInfo.color,
                      lineHeight: 1.1,
                    }}>
                      {rank}
                    </span>
                    <span style={{
                      fontSize: 12,
                      color: suitInfo.color,
                      lineHeight: 1.1,
                    }}>
                      {suitInfo.sym}
                    </span>
                  </button>
                )
              })
            )}
          </div>
          <div style={{ fontSize: 11, color: tokens.colors.muted, marginTop: 8, textAlign: 'center' }}>
            {flopCards.length < 3
              ? `Select ${3 - flopCards.length} more card${3 - flopCards.length === 1 ? '' : 's'} for the flop`
              : '3 cards selected. Click a card to remove it.'}
          </div>
        </div>
      )}
    </div>
  )
}
