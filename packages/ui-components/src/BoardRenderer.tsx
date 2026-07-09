'use client'

interface BoardRendererProps {
  cards: string[]
}

const SUIT_TO_COLOR: Record<string, string> = { s: '#2c3e50', c: '#2ecc71', h: '#e74c3c', d: '#3498db' }

export function BoardRenderer({ cards }: BoardRendererProps) {
  if (!cards.length) return null
  return (
    <div style={{ display: 'flex', gap: 6 }}>
      {cards.map(card => {
        const suit = card.charAt(card.length - 1).toLowerCase()
        return (
          <span
            key={card}
            style={{
              width: 36,
              height: 48,
              background: '#fff',
              color: SUIT_TO_COLOR[suit] || '#2c3e50',
              borderRadius: 6,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: 700,
              fontSize: 15,
              border: '1px solid #ddd',
              boxShadow: '0 1px 3px rgba(0,0,0,0.15)',
            }}
          >
            {card}
          </span>
        )
      })}
    </div>
  )
}
