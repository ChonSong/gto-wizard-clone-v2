'use client'

import { useState, useEffect, useCallback } from 'react'

// --- Types ---
interface QuizSpot {
  id: string
  category: string
  difficulty: 'easy' | 'medium' | 'hard'
  description: string
  position: string
  stack_depth: number
  board?: string[]
  hero_cards: string[]
  gto_action: string
  gto_frequency: number
  alternatives: { action: string; frequency: number }[]
}

interface QuizStats {
  correct: number
  total: number
  streak: number
  ev_loss_total: number
}

// --- Mock spots (until API is wired) ---
const MOCK_SPOTS: QuizSpot[] = [
  {
    id: '1',
    category: 'Preflop RFI',
    difficulty: 'easy',
    description: 'UTG 100bb. What do you do with AKo?',
    position: 'UTG',
    stack_depth: 100,
    hero_cards: ['As', 'Kd'],
    gto_action: 'raise',
    gto_frequency: 0.98,
    alternatives: [{ action: 'fold', frequency: 0.02 }],
  },
  {
    id: '2',
    category: 'Preflop vs 3-bet',
    difficulty: 'medium',
    description: 'You open CO, BB 3-bets. What do you do with JTs?',
    position: 'CO',
    stack_depth: 100,
    hero_cards: ['Js', 'Ts'],
    gto_action: 'call',
    gto_frequency: 0.65,
    alternatives: [
      { action: 'raise', frequency: 0.15 },
      { action: 'fold', frequency: 0.20 },
    ],
  },
  {
    id: '3',
    category: 'Flop C-bet',
    difficulty: 'hard',
    description: 'You raised BTN, BB called. Flop: K72 rainbow. BB checks. What do you do with 98s?',
    position: 'BTN',
    stack_depth: 100,
    board: ['Ks', '7d', '2c'],
    hero_cards: ['9s', '8s'],
    gto_action: 'bet',
    gto_frequency: 0.72,
    alternatives: [{ action: 'check', frequency: 0.28 }],
  },
]

const ACTIONS = ['fold', 'check', 'call', 'bet', 'raise', 'all_in'] as const
type Action = typeof ACTIONS[number]

export default function PracticePage() {
  const [spots, setSpots] = useState<QuizSpot[]>([])
  const [currentIndex, setCurrentIndex] = useState(0)
  const [selectedAction, setSelectedAction] = useState<Action | null>(null)
  const [showResult, setShowResult] = useState(false)
  const [stats, setStats] = useState<QuizStats>({ correct: 0, total: 0, streak: 0, ev_loss_total: 0 })
  const [feedback, setFeedback] = useState<string | null>(null)
  const [mode, setMode] = useState<'idle' | 'playing' | 'complete'>('idle')

  const currentSpot = spots[currentIndex]

  const startQuiz = useCallback(() => {
    setSpots(MOCK_SPOTS)
    setCurrentIndex(0)
    setStats({ correct: 0, total: 0, streak: 0, ev_loss_total: 0 })
    setMode('playing')
    setShowResult(false)
    setSelectedAction(null)
    setFeedback(null)
  }, [])

  const submitAction = (action: Action) => {
    if (showResult || !currentSpot) return
    setSelectedAction(action)
    setShowResult(true)

    const isCorrect = action === currentSpot.gto_action
    const newStats = { ...stats, total: stats.total + 1 }
    if (isCorrect) {
      newStats.correct++
      newStats.streak++
      setFeedback(`✅ Correct! GTO ${currentSpot.gto_action}s ${(currentSpot.gto_frequency * 100).toFixed(0)}% of the time.`)
    } else {
      newStats.streak = 0
      newStats.ev_loss_total += 0.5
      setFeedback(`❌ GTO ${currentSpot.gto_action}s ${(currentSpot.gto_frequency * 100).toFixed(0)}%. You chose ${action}.`)
    }
    setStats(newStats)
  }

  const nextSpot = () => {
    if (currentIndex + 1 >= spots.length) {
      setMode('complete')
    } else {
      setCurrentIndex(prev => prev + 1)
      setSelectedAction(null)
      setShowResult(false)
      setFeedback(null)
    }
  }

  // --- Render ---
  if (mode === 'idle') {
    return (
      <div style={{ maxWidth: 600, margin: '0 auto', padding: '48px 24px', textAlign: 'center' }}>
        <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 12 }}>Practice Mode</h1>
        <p style={{ color: '#8a8f98', marginBottom: 32 }}>
          Test your decisions against GTO solutions. Get instant feedback and track your progress.
        </p>
        <button
          onClick={startQuiz}
          style={{
            padding: '14px 32px',
            fontSize: 16,
            fontWeight: 600,
            background: '#00b894',
            color: '#fff',
            border: 'none',
            borderRadius: 8,
            cursor: 'pointer',
          }}
        >
          Start Training
        </button>
      </div>
    )
  }

  if (mode === 'complete') {
    const accuracy = stats.total > 0 ? ((stats.correct / stats.total) * 100).toFixed(1) : '0'
    return (
      <div style={{ maxWidth: 500, margin: '0 auto', padding: '48px 24px', textAlign: 'center' }}>
        <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 12 }}>Session Complete!</h1>
        <div style={{ background: '#1a1c1e', borderRadius: 12, padding: 24, marginBottom: 24 }}>
          <div style={{ fontSize: 48, fontWeight: 700, color: '#00b894' }}>{accuracy}%</div>
          <div style={{ color: '#8a8f98', fontSize: 14, marginTop: 4 }}>Accuracy</div>
          <div style={{ display: 'flex', justifyContent: 'center', gap: 32, marginTop: 20 }}>
            <div>
              <div style={{ fontSize: 24, fontWeight: 600 }}>{stats.correct}/{stats.total}</div>
              <div style={{ fontSize: 12, color: '#8a8f98' }}>Correct</div>
            </div>
            <div>
              <div style={{ fontSize: 24, fontWeight: 600 }}>{stats.streak}</div>
              <div style={{ fontSize: 12, color: '#8a8f98' }}>Best Streak</div>
            </div>
          </div>
        </div>
        <button onClick={startQuiz} style={{ padding: '14px 32px', fontSize: 16, fontWeight: 600, background: '#00b894', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer' }}>
          Train Again
        </button>
      </div>
    )
  }

  return (
    <div style={{ maxWidth: 640, margin: '0 auto', padding: '32px 24px' }}>
      {/* Progress */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div style={{ fontSize: 13, color: '#8a8f98' }}>
          {currentIndex + 1} / {spots.length}
        </div>
        <div style={{ display: 'flex', gap: 16, fontSize: 13 }}>
          <span style={{ color: '#2ecc71' }}>✓ {stats.correct}</span>
          <span style={{ color: '#e74c3c' }}>Streak: {stats.streak}</span>
        </div>
      </div>

      {/* Spot card */}
      {currentSpot && (
        <div style={{ background: '#1a1c1e', borderRadius: 12, padding: 24, border: '1px solid #2a2e32' }}>
          <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            <span style={{
              padding: '2px 8px',
              borderRadius: 4,
              fontSize: 11,
              fontWeight: 600,
              background: currentSpot.difficulty === 'easy' ? '#2ecc7115' : currentSpot.difficulty === 'medium' ? '#e67e2215' : '#e74c3c15',
              color: currentSpot.difficulty === 'easy' ? '#2ecc71' : currentSpot.difficulty === 'medium' ? '#e67e22' : '#e74c3c',
            }}>
              {currentSpot.difficulty.toUpperCase()}
            </span>
            <span style={{ padding: '2px 8px', borderRadius: 4, fontSize: 11, background: '#ffffff08', color: '#8a8f98' }}>
              {currentSpot.category}
            </span>
          </div>

          <p style={{ fontSize: 16, lineHeight: 1.5, marginBottom: 20 }}>{currentSpot.description}</p>

          {/* Hero cards display */}
          <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
            {currentSpot.hero_cards.map(card => (
              <span key={card} style={{
                width: 40, height: 56,
                background: '#fff', color: card.includes('s') || card.includes('d') ? '#e74c3c' : '#2c3e50',
                borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontWeight: 700, fontSize: 16, border: '1px solid #ddd',
              }}>
                {card}
              </span>
            ))}
          </div>

          {currentSpot.board && (
            <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
              <span style={{ fontSize: 12, color: '#8a8f98', marginRight: 4 }}>Board:</span>
              {currentSpot.board.map(card => (
                <span key={card} style={{
                  width: 32, height: 44,
                  background: '#fff', color: card.includes('s') || card.includes('d') ? '#e74c3c' : '#2c3e50',
                  borderRadius: 4, display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontWeight: 700, fontSize: 14, border: '1px solid #ddd',
                }}>
                  {card}
                </span>
              ))}
            </div>
          )}

          {/* Action buttons */}
          {!showResult ? (
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {ACTIONS.map(action => (
                <button
                  key={action}
                  onClick={() => submitAction(action)}
                  style={{
                    padding: '10px 20px',
                    borderRadius: 8,
                    border: '1px solid #2a2e32',
                    background: '#0e0e0f',
                    color: '#d7d7d7',
                    fontSize: 15,
                    fontWeight: 500,
                    cursor: 'pointer',
                    transition: 'background 0.15s',
                    textTransform: 'capitalize',
                  }}
                  onMouseEnter={e => { e.currentTarget.style.background = '#2a2e32' }}
                  onMouseLeave={e => { e.currentTarget.style.background = '#0e0e0f' }}
                >
                  {action.replace('_', ' ')}
                </button>
              ))}
            </div>
          ) : (
            /* Result view */
            <div>
              <div
                style={{
                  padding: '12px 16px',
                  borderRadius: 8,
                  background: feedback?.startsWith('✅') ? '#2ecc7115' : '#e74c3c15',
                  border: `1px solid ${feedback?.startsWith('✅') ? '#2ecc7130' : '#e74c3c30'}`,
                  marginBottom: 16,
                  fontSize: 14,
                  lineHeight: 1.5,
                  color: feedback?.startsWith('✅') ? '#2ecc71' : '#e74c3c',
                }}
              >
                {feedback}
              </div>
              <button
                onClick={nextSpot}
                style={{
                  width: '100%',
                  padding: '14px',
                  fontSize: 16,
                  fontWeight: 600,
                  background: '#00b894',
                  color: '#fff',
                  border: 'none',
                  borderRadius: 8,
                  cursor: 'pointer',
                }}
              >
                {currentIndex + 1 >= spots.length ? 'See Results' : 'Next Spot →'}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
