'use client'

import { useState, useEffect, useCallback } from 'react'
import { ACTION_COLORS } from '@/lib/tokens'
import useAggregateStats from '@/hooks/useAggregateStats'
import { AggregateFlipStrip } from '@/components/study/AggregateFlipStrip'
import { BreakdownTab } from '@/components/study/BreakdownTab'
import { StrategyTab } from '@/components/study/StrategyTab'
import { PostflopPanel } from '@/components/study/PostflopPanel'

// --- Types & Interfaces ---
interface HandCell {
  hand: string
  action: string
  frequency: number
  equity?: number
}

interface BoardCard {
  rank: string
  suit: string
}

interface HandLock {
  actions: Record<string, number>
}

interface TreeAction {
  position: string
  action: string
  label: string
  size?: number
}

interface TreeNodeData {
  acting_position: string
  available_actions: Array<{ id: string; actionBase: string; label: string; size?: number; frequency?: number }>
  pot_size: number
  stack_remaining: number
  context: string
  description?: string
}

interface RangeResponse {
  hands?: HandCell[]
  range?: HandCell[]
  source?: string
  combos?: number
  position?: string
  stack_depth?: number
  tree_node?: TreeNodeData
  locked_hands_applied?: string[]
  counter_strategy?: Record<string, number>
}

interface PostflopAction {
  action: string
  frequency: number
  ev: number
}

interface PostflopResponse {
  actions: PostflopAction[]
  source: string
  status: string
  message?: string
}

// --- URL helpers ---
function parseLockedHandsFromURL(): Record<string, HandLock> {
  if (typeof window === 'undefined') return {}
  const hash = window.location.hash
  if (!hash.startsWith('#locks=')) return {}
  try {
    return JSON.parse(decodeURIComponent(hash.slice(7)))
  } catch {
    return {}
  }
}

function serializeLockedHandsToURL(locks: Record<string, HandLock>): string {
  if (Object.keys(locks).length === 0) return ''
  return `#locks=${encodeURIComponent(JSON.stringify(locks))}`
}

// --- Constants ---
const POSITIONS = ['UTG', 'HJ', 'CO', 'BTN', 'SB', 'BB'] as const
type Position = typeof POSITIONS[number]
const RANKS = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2'] as const
const GRAY = '#2a2e32'
const SUITS = [
  { id: 's', sym: '♠', color: '#d7d7d7' },
  { id: 'h', sym: '♥', color: '#e74c3c' },
  { id: 'd', sym: '♦', color: '#e74c3c' },
  { id: 'c', sym: '♣', color: '#d7d7d7' },
]

// --- Helpers ---
function getCellColor(action: string, frequency: number, GRAY: string): string {
  if (action === 'fold' || frequency === 0) return GRAY
  const base = action.startsWith('all_in') || action === 'all_in' ? '#c0392b'
    : action.startsWith('raise') || action.startsWith('bet') ? ACTION_COLORS.raise
    : action.startsWith('call') || action === 'check' ? ACTION_COLORS.call
    : GRAY
  return base
}

function getSuitSymbol(suitId: string): string {
  return SUITS.find(s => s.id === suitId)?.sym ?? '?'
}

function getSuitColor(suitId: string): string {
  return SUITS.find(s => s.id === suitId)?.color ?? '#d7d7d7'
}

function randomBoard(cardCount: number): BoardCard[] {
  const pool: BoardCard[] = []
  for (const r of RANKS) for (const s of SUITS) pool.push({ rank: r, suit: s.id })
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[pool[i], pool[j]] = [pool[j], pool[i]]
  }
  return pool.slice(0, cardCount)
}

// --- Main Component ---
export default function StudyPage() {
  // Core state
  const [activePosition, setActivePosition] = useState<Position>('UTG')
  const [stackDepth, setStackDepth] = useState(100)
  const [treePath, setTreePath] = useState<TreeAction[]>([])
  const [treeNode, setTreeNode] = useState<TreeNodeData | null>(null)
  const [actionFilter, setActionFilter] = useState<string | null>(null)
  const [rangeData, setRangeData] = useState<HandCell[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Board / postflop state
  const [boardCards, setBoardCards] = useState<BoardCard[]>([])
  const [postflopActions, setPostflopActions] = useState<PostflopAction[]>([])

  // UI state
  const [selectedHand, setSelectedHand] = useState<string | null>(null)
  const [lockedHands, setLockedHands] = useState<Record<string, HandLock>>(() => parseLockedHandsFromURL())
  const [activeTab, setActiveTab] = useState<'matrix' | 'breakdown' | 'strategy'>('matrix')
  const [boardPickerOpen, setBoardPickerOpen] = useState(false)

  // Aggregate stats
  const { stats: aggregateStats, loading: statsLoading, error: statsError } = useAggregateStats(stackDepth)

  const isPostflop = boardCards.length >= 3

  // --- Fetch preflop ranges ---
  const fetchRange = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const body: Record<string, unknown> = {
        position: activePosition,
        stack_depth: stackDepth,
        game_type: 'NLH',
        players: 6,
      }
      if (treePath.length > 0) {
        body.tree_path = treePath.map(t => ({ position: t.position, action: t.action }))
      }
      if (Object.keys(lockedHands).length > 0) {
        body.locked_hands = Object.fromEntries(
          Object.entries(lockedHands).map(([hand, lock]) => [hand, { actions: lock.actions }])
        )
      }

      const res = await fetch('/api/v1/solver/preflop-range', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data: RangeResponse = await res.json()
      setRangeData(data.hands || data.range || [])
      setTreeNode(data.tree_node || null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load range')
      setRangeData([])
      setTreeNode(null)
    } finally {
      setLoading(false)
    }
  }, [activePosition, stackDepth, treePath, lockedHands])

  // --- Fetch postflop strategy ---
  const fetchPostflopStrategy = useCallback(async (board: BoardCard[]) => {
    if (board.length < 3) {
      setPostflopActions([])
      return
    }
    setLoading(true)
    setError(null)
    try {
      const boardStr = board.map(c => c.rank + c.suit).join('')
      const res = await fetch('/api/v1/solver/postflop-strategy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          board: boardStr,
          position: activePosition,
          street: board.length === 3 ? 'flop' : board.length === 4 ? 'turn' : 'river',
          pot_size: 5.5,
          stack_depth: stackDepth - 2.5,
        }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data: PostflopResponse = await res.json()
      setPostflopActions(data.actions || [])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load postflop strategy')
      setPostflopActions([])
    } finally {
      setLoading(false)
    }
  }, [activePosition, stackDepth])

  // Fetch on parameter changes
  useEffect(() => {
    if (isPostflop) {
      fetchPostflopStrategy(boardCards)
    } else {
      fetchRange()
    }
  }, [activePosition, stackDepth, treePath, lockedHands, boardCards, isPostflop, fetchRange, fetchPostflopStrategy])

  // Reset tree when position or stack depth changes
  useEffect(() => {
    setTreePath([])
    setTreeNode(null)
    setActiveTab('matrix')
    const urlHash = serializeLockedHandsToURL(lockedHands)
    if (urlHash !== window.location.hash) {
      window.history.replaceState(null, '', window.location.pathname + urlHash)
    }
  }, [activePosition, stackDepth, lockedHands])

  // --- Handlers ---
  function handleActionClick(actionBase: string) {
    const actions = treeNode?.available_actions || []
    const matchingAct = actions.find(a => a.actionBase === actionBase)
    if (!matchingAct) { setActionFilter(null); return }
    const newEntry: TreeAction = {
      position: displayPosition,
      action: matchingAct.id,
      label: matchingAct.label,
      size: matchingAct.size,
    }
    setTreePath(prev => [...prev, newEntry])
    setActionFilter(null)
  }

  function handlePositionClick(pos: Position) {
    setActivePosition(pos)
    setActionFilter(null)
  }

  function handleBoardChange(cards: BoardCard[]) {
    setBoardCards(cards)
    setTreePath([])
    setTreeNode(null)
    if (cards.length === 0) {
      setPostflopActions([])
    }
  }

  const handleDealerBoard = useCallback((cardCount: number) => {
    handleBoardChange(randomBoard(cardCount))
  }, [])

  const handleClearBoard = useCallback(() => {
    handleBoardChange([])
  }, [])

  function handleToggleBoardCard(rank: string, suit: string) {
    const existing = boardCards.find(c => c.rank === rank && c.suit === suit)
    if (existing) {
      handleBoardChange(boardCards.filter(c => !(c.rank === rank && c.suit === suit)))
    } else if (boardCards.length < 5) {
      handleBoardChange([...boardCards, { rank, suit }])
    }
  }

  const displayPosition: Position = treeNode?.acting_position
    ? (treeNode.acting_position as Position)
    : activePosition

  const displayActions = treeNode?.available_actions || []
  const selectedHandData = selectedHand ? rangeData.find(h => h.hand === selectedHand) : null

  // --- Cell display logic ---
  function getCellOpacity(cell: HandCell | undefined): number {
    if (!actionFilter) return 1
    return cell?.action.startsWith(actionFilter) ? 1 : 0.08
  }

  return (
    <div
      data-testid="study-page"
      style={{ display: 'flex', height: 'calc(100vh - 48px)', overflow: 'hidden' }}
    >
      {/* ===== LEFT SIDEBAR ===== */}
      <aside
        data-testid="study-sidebar"
        style={{
          width: 240,
          background: '#1a1c1e',
          borderRight: '1px solid #2a2e32',
          padding: 16,
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
          flexShrink: 0,
          overflow: 'auto',
        }}
      >
        {/* Position selector */}
        <section data-testid="position-selector">
          <h3 style={sectionTitle}>Position</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {POSITIONS.map(pos => (
              <div key={pos}>
                <button
                  data-testid={`position-btn-${pos}`}
                  aria-pressed={pos === displayPosition}
                  onClick={() => handlePositionClick(pos)}
                  style={{
                    width: '100%', textAlign: 'left', padding: '10px 12px', borderRadius: 8, border: 'none',
                    background: pos === displayPosition ? '#00b89415' : 'transparent',
                    color: pos === displayPosition ? '#00b894' : '#d7d7d7',
                    fontWeight: pos === displayPosition ? 600 : 400,
                    cursor: 'pointer', fontSize: 14, transition: 'background 0.15s',
                  }}
                  onMouseEnter={e => { if (pos !== displayPosition) e.currentTarget.style.background = '#ffffff08' }}
                  onMouseLeave={e => { if (pos !== displayPosition) e.currentTarget.style.background = 'transparent' }}
                >
                  {pos}
                </button>
                {/* Action buttons for acting position */}
                {pos === displayPosition && displayActions.length > 0 && (
                  <div
                    data-testid="position-actions"
                    style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4, paddingLeft: 12 }}
                  >
                    {displayActions.map(act => (
                      <button
                        key={act.id}
                        data-testid={`action-btn-${act.actionBase}`}
                        aria-pressed={actionFilter === act.actionBase}
                        onClick={e => { e.stopPropagation(); handleActionClick(act.actionBase) }}
                        onMouseEnter={() => setActionFilter(act.actionBase)}
                        onMouseLeave={() => setActionFilter(null)}
                        style={{
                          padding: '4px 8px', borderRadius: 4,
                          border: actionFilter === act.actionBase
                            ? `1px solid ${getCellColor(act.actionBase, 1, GRAY)}`
                            : '1px solid transparent',
                          background: actionFilter === act.actionBase
                            ? `${getCellColor(act.actionBase, 1, GRAY)}20`
                            : 'rgba(255,255,255,0.04)',
                          color: actionFilter === act.actionBase
                            ? getCellColor(act.actionBase, 1, GRAY)
                            : '#8a8f98',
                          fontSize: 11, fontWeight: actionFilter === act.actionBase ? 700 : 400,
                          cursor: 'pointer', transition: 'all 0.1s',
                        }}
                      >
                        {act.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>

        {/* Stack depth selector */}
        <section data-testid="stack-depth-selector" style={{ marginTop: 16 }}>
          <h3 style={sectionTitle}>Stack Depth</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {[20, 40, 60, 80, 100, 150, 200].map(bb => (
              <button
                key={bb}
                data-testid={`stack-btn-${bb}`}
                aria-pressed={stackDepth === bb}
                onClick={() => setStackDepth(bb)}
                style={{
                  width: '100%', textAlign: 'left', padding: '6px 12px', borderRadius: 6, border: 'none',
                  background: stackDepth === bb ? '#00b89415' : 'transparent',
                  color: stackDepth === bb ? '#00b894' : '#8a8f98',
                  fontWeight: stackDepth === bb ? 600 : 400,
                  cursor: 'pointer', fontSize: 13, transition: 'background 0.15s',
                }}
              >
                {bb}bb
              </button>
            ))}
          </div>
        </section>

        {/* Board card selector — POSTFLOP */}
        <section data-testid="board-selector" style={{ marginTop: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <h3 style={{ ...sectionTitle, margin: 0 }}>Board Cards</h3>
            <span style={{ fontSize: 11, color: '#555' }}>
              {boardCards.length === 0 ? 'Preflop' :
               boardCards.length < 3 ? `${boardCards.length}/3 Flop` :
               boardCards.length === 3 ? 'Flop' :
               boardCards.length === 4 ? 'Turn' : 'River'}
            </span>
          </div>

          {/* Card display row */}
          <div style={{ display: 'flex', gap: 4, marginBottom: 8 }}>
            {boardCards.length === 0 ? (
              <div style={{
                width: 100, height: 48, borderRadius: 6, border: '2px dashed #2a2e32',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 11, color: '#555',
              }}>
                No board
              </div>
            ) : (
              boardCards.map((card, i) => (
                <button
                  key={`${card.rank}${card.suit}`}
                  data-testid={`board-card-${i}`}
                  onClick={() => handleBoardChange(boardCards.filter((_, j) => j !== i))}
                  style={{
                    width: 36, height: 48, borderRadius: 4, border: '2px solid #00b894',
                    background: '#0e0e0f', display: 'flex', flexDirection: 'column',
                    alignItems: 'center', justifyContent: 'center', cursor: 'pointer',
                    gap: 0, padding: 0, position: 'relative',
                  }}
                  title={`${card.rank}${getSuitSymbol(card.suit)} — click to remove`}
                >
                  <span style={{ fontSize: 14, fontWeight: 700, color: getSuitColor(card.suit), lineHeight: 1 }}>
                    {card.rank}
                  </span>
                  <span style={{ fontSize: 12, color: getSuitColor(card.suit), lineHeight: 1 }}>
                    {getSuitSymbol(card.suit)}
                  </span>
                </button>
              ))
            )}
          </div>

          {/* Board controls */}
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            <button
              data-testid="btn-deal-flop"
              onClick={() => handleDealerBoard(3)}
              style={{
                padding: '4px 10px', borderRadius: 4, border: '1px solid #2a2e32',
                background: 'transparent', color: boardCards.length >= 3 ? '#2a2e32' : '#8a8f98',
                cursor: boardCards.length >= 3 ? 'not-allowed' : 'pointer', fontSize: 11, fontWeight: 600,
              }}
            >
              Deal Flop
            </button>
            {boardCards.length === 3 && (
              <button
                data-testid="btn-deal-turn"
                onClick={() => handleDealerBoard(4)}
                style={{
                  padding: '4px 10px', borderRadius: 4, border: '1px solid #2a2e32',
                  background: 'transparent', color: '#8a8f98', cursor: 'pointer', fontSize: 11, fontWeight: 600,
                }}
              >
                Deal Turn
              </button>
            )}
            {boardCards.length === 4 && (
              <button
                data-testid="btn-deal-river"
                onClick={() => handleDealerBoard(5)}
                style={{
                  padding: '4px 10px', borderRadius: 4, border: '1px solid #2a2e32',
                  background: 'transparent', color: '#8a8f98', cursor: 'pointer', fontSize: 11, fontWeight: 600,
                }}
              >
                Deal River
              </button>
            )}
            <button
              data-testid="btn-toggle-board-picker"
              onClick={() => setBoardPickerOpen(!boardPickerOpen)}
              aria-expanded={boardPickerOpen}
              style={{
                padding: '4px 10px', borderRadius: 4,
                border: boardPickerOpen ? '1px solid #00b894' : '1px solid #2a2e32',
                background: boardPickerOpen ? '#00b89415' : 'transparent',
                color: boardPickerOpen ? '#00b894' : '#8a8f98',
                cursor: 'pointer', fontSize: 11, fontWeight: 600,
              }}
            >
              {boardPickerOpen ? 'Close' : 'Pick Cards'}
            </button>
            {boardCards.length > 0 && (
              <button
                data-testid="btn-clear-board"
                onClick={handleClearBoard}
                style={{
                  padding: '4px 8px', borderRadius: 4, border: 'none',
                  background: 'transparent', color: '#8a8f98', cursor: 'pointer', fontSize: 12,
                }}
                title="Clear board"
              >
                ✕
              </button>
            )}
          </div>

          {/* Expanded card picker grid */}
          {boardPickerOpen && (
            <div
              data-testid="board-card-picker"
              style={{
                marginTop: 8, padding: 8, background: '#0e0e0f', borderRadius: 6,
                border: '1px solid #2a2e32',
              }}
            >
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(4, 1fr)',
                gap: 3,
              }}>
                {RANKS.map(rank =>
                  SUITS.map(suit => {
                    const isSelected = boardCards.some(c => c.rank === rank && c.suit === suit.id)
                    const isDisabled = !isSelected && boardCards.length >= 5
                    return (
                      <button
                        key={`${rank}${suit.id}`}
                        data-testid={`board-card-option-${rank}${suit.id}`}
                        disabled={isDisabled}
                        onClick={() => handleToggleBoardCard(rank, suit.id)}
                        style={{
                          width: '100%', height: 40, borderRadius: 3,
                          border: isSelected
                            ? '2px solid #00b894'
                            : isDisabled
                            ? '1px solid #1a1c1e'
                            : '1px solid transparent',
                          background: isSelected ? '#00b89420' : isDisabled ? 'transparent' : '#1a1c1e',
                          cursor: isDisabled ? 'not-allowed' : 'pointer',
                          display: 'flex', flexDirection: 'column',
                          alignItems: 'center', justifyContent: 'center',
                          gap: 0, opacity: isDisabled ? 0.3 : 1,
                          transition: 'all 0.1s',
                        }}
                        onMouseEnter={e => { if (!isDisabled) e.currentTarget.style.filter = 'brightness(1.3)' }}
                        onMouseLeave={e => { e.currentTarget.style.filter = 'brightness(1)' }}
                      >
                        <span style={{ fontSize: 11, fontWeight: 700, color: suit.color, lineHeight: 1 }}>{rank}</span>
                        <span style={{ fontSize: 10, color: suit.color, lineHeight: 1 }}>{suit.sym}</span>
                      </button>
                    )
                  })
                )}
              </div>
              <div style={{ fontSize: 10, color: '#555', marginTop: 6, textAlign: 'center' }}>
                {boardCards.length < 3
                  ? `Select ${3 - boardCards.length} more card${3 - boardCards.length === 1 ? '' : 's'} for the flop`
                  : boardCards.length === 3
                  ? 'Flop set. Add Turn/River or click ✕ to clear'
                  : boardCards.length === 4
                  ? 'Turn set. Add River or deal'
                  : '5 cards selected (River)'}
              </div>
            </div>
          )}
        </section>

        {/* Game tree breadcrumb — "What happened" */}
        {treePath.length > 0 && (
          <section data-testid="game-tree-breadcrumb" style={{ marginTop: 16 }}>
            <h3 style={sectionTitle}>Action History</h3>
            <div style={{
              display: 'flex', flexWrap: 'wrap', gap: 4,
              padding: '8px 10px', background: '#0e0e0f', borderRadius: 6,
              border: '1px solid #2a2e32', fontSize: 11,
            }}>
              {treePath.map((step, i) => (
                <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                  <span style={{ color: '#8a8f98', fontWeight: 600 }}>{step.position}</span>
                  <span style={{ color: getCellColor(step.action, 1, GRAY), fontWeight: 700 }}>{step.label}</span>
                  {i < treePath.length - 1 && <span style={{ color: '#2a2e32' }}>→</span>}
                </span>
              ))}
              <button
                data-testid="btn-reset-tree"
                onClick={() => setTreePath([])}
                style={{
                  marginLeft: 'auto', background: 'none', border: 'none',
                  color: '#555', cursor: 'pointer', fontSize: 12,
                }}
                title="Reset game tree"
              >
                ✕
              </button>
            </div>
          </section>
        )}

        {/* Locked hands summary */}
        {Object.keys(lockedHands).length > 0 && (
          <section data-testid="locked-hands-summary" style={{ marginTop: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
              <h3 style={{ ...sectionTitle, margin: 0 }}>Locked Hands</h3>
              <button
                data-testid="btn-clear-all-locks"
                onClick={() => setLockedHands({})}
                style={{
                  background: 'none', border: 'none', color: '#555',
                  cursor: 'pointer', fontSize: 10, textDecoration: 'underline',
                }}
              >
                Clear all
              </button>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {Object.entries(lockedHands).map(([hand, lock]) => (
                <div
                  key={hand}
                  data-testid={`locked-hand-${hand}`}
                  style={{
                    padding: '6px 10px', background: '#0e0e0f', borderRadius: 6,
                    border: '1px solid #f1c40f20', fontSize: 11,
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  }}
                >
                  <span style={{ fontWeight: 700 }}>{hand} 🔒</span>
                  <span style={{ color: '#8a8f98', fontSize: 10 }}>
                    {Object.entries(lock.actions).map(([a, f]) => `${a} ${(f * 100).toFixed(0)}%`).join(' / ')}
                  </span>
                </div>
              ))}
            </div>
          </section>
        )}
      </aside>

      {/* ===== MAIN CONTENT ===== */}
      <main
        data-testid="study-main-content"
        style={{ flex: 1, padding: 24, overflow: 'auto', display: 'flex', flexDirection: 'column', alignItems: 'center' }}
      >
        {/* Tab navigation */}
        <nav
          data-testid="study-tab-bar"
          role="tablist"
          aria-label="Study view tabs"
          style={{ display: 'flex', gap: 0, marginBottom: 16, width: 'fit-content' }}
        >
          {(['matrix', 'breakdown', 'strategy'] as const).map(tab => (
            <button
              key={tab}
              role="tab"
              aria-selected={activeTab === tab}
              data-testid={`tab-${tab}`}
              onClick={() => setActiveTab(tab)}
              style={{
                padding: '8px 20px', border: 'none',
                background: activeTab === tab ? '#00b89415' : 'transparent',
                color: activeTab === tab ? '#00b894' : '#8a8f98',
                cursor: 'pointer', fontSize: 13, fontWeight: 600,
                borderBottom: activeTab === tab ? '2px solid #00b894' : '2px solid transparent',
                textTransform: 'capitalize', transition: 'background 0.15s',
              }}
            >
              {tab}
            </button>
          ))}
        </nav>

        {/* Postflop mode indicator */}
        {isPostflop && (
          <div
            data-testid="postflop-indicator"
            style={{
              display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12,
              padding: '6px 14px', background: '#3498db15', borderRadius: 6,
              border: '1px solid #3498db30', fontSize: 11, color: '#3498db',
            }}
          >
            <span>🎯</span>
            <span>Postflop: {boardCards.length === 3 ? 'Flop' : boardCards.length === 4 ? 'Turn' : 'River'} solved live</span>
            <button
              onClick={handleClearBoard}
              style={{
                marginLeft: 'auto', background: 'none', border: 'none',
                color: '#8a8f98', cursor: 'pointer', fontSize: 11,
              }}
            >
              ✕
            </button>
          </div>
        )}

        {/* Loading / Error */}
        {loading && (
          <div data-testid="study-loading" style={{ color: '#8a8f98', fontSize: 14, marginBottom: 16 }}>
            Loading...
          </div>
        )}
        {error && (
          <div data-testid="study-error" style={{ color: '#e74c3c', fontSize: 14, marginBottom: 16, padding: '8px 16px', background: '#e74c3c10', borderRadius: 8 }}>
            {error}
          </div>
        )}

        {/* ===== MATRIX TAB ===== */}
        {activeTab === 'matrix' && (
          <>
            {/* Preflop matrix */}
            {!isPostflop && (
              <>
                <div
                  data-testid="hand-matrix"
                  role="grid"
                  aria-label="13x13 hand matrix"
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(13, 48px)',
                    gridTemplateRows: 'repeat(13, 48px)',
                    gap: 1, background: '#2a2e32', borderRadius: 8, overflow: 'hidden',
                  }}
                >
                  {RANKS.flatMap((r1, i) =>
                    RANKS.map((r2, j) => {
                      const isPair = i === j
                      const isSuited = i < j
                      const handKey = isPair ? `${r1}${r2}` : isSuited ? `${r1}${r2}s` : `${r2}${r1}o`
                      const cell = rangeData.find(h => h.hand === handKey)
                      const action = cell?.action || 'fold'
                      const freq = cell?.frequency || 0
                      const color = getCellColor(action, freq, GRAY)
                      const opacity = getCellOpacity(cell)
                      const isSelected = selectedHand === handKey

                      return (
                        <button
                          key={handKey}
                          role="gridcell"
                          data-testid={`hand-cell-${handKey}`}
                          aria-label={`${handKey}: ${action} ${freq > 0 ? `${(freq * 100).toFixed(0)}%` : 'fold'}`}
                          onClick={() => setSelectedHand(prev => prev === handKey ? null : handKey)}
                          style={{
                            width: 48, height: 48,
                            border: isSelected ? '2px solid #ffffff' : '1px solid transparent',
                            borderRadius: 4, cursor: 'pointer', display: 'flex', flexDirection: 'column',
                            alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 600,
                            color: action === 'fold' || freq === 0 ? '#555' : '#fff', opacity,
                            background: action !== 'fold' && freq > 0 && freq < 1
                              ? `linear-gradient(to right, ${color} ${(freq * 100).toFixed(0)}%, ${GRAY} ${(freq * 100).toFixed(0)}%)`
                              : action !== 'fold' && freq > 0 ? color : GRAY,
                            transition: 'opacity 0.15s, filter 0.15s',
                          }}
                          onMouseEnter={e => { e.currentTarget.style.filter = 'brightness(1.3)' }}
                          onMouseLeave={e => { e.currentTarget.style.filter = 'brightness(1)' }}
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

                {/* Matrix legend */}
                <div data-testid="matrix-legend" style={{ display: 'flex', gap: 16, marginTop: 16, fontSize: 12, color: '#8a8f98' }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ width: 12, height: 12, borderRadius: 2, background: ACTION_COLORS.raise }} /> Raise
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ width: 12, height: 12, borderRadius: 2, background: ACTION_COLORS.call }} /> Call
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ width: 12, height: 12, borderRadius: 2, background: '#c0392b' }} /> All-in
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ width: 12, height: 12, borderRadius: 2, background: GRAY }} /> Fold
                  </span>
                </div>

                {/* Aggregate strip */}
                {statsLoading && <div style={{ color: '#8a8f98', fontSize: 14, marginTop: 20 }}>Loading stats...</div>}
                {statsError && <div style={{ color: '#e74c3c', fontSize: 13, marginTop: 12 }}>{statsError}</div>}
                {!statsLoading && !statsError && (
                  <AggregateFlipStrip stats={aggregateStats} activePosition={activePosition} onPositionClick={setActivePosition} />
                )}
              </>
            )}

            {/* Postflop strategy panel */}
            {isPostflop && (
              <PostflopPanel actions={postflopActions} />
            )}
          </>
        )}

        {/* ===== BREAKDOWN TAB ===== */}
        {activeTab === 'breakdown' && (
          <BreakdownTab rangeData={rangeData} onHandClick={setSelectedHand} />
        )}

        {/* ===== STRATEGY TAB ===== */}
        {activeTab === 'strategy' && (
          <StrategyTab rangeData={rangeData} onHandClick={setSelectedHand} />
        )}
      </main>

      {/* ===== RIGHT PANEL ===== */}
      <aside
        data-testid="study-detail-panel"
        style={{
          width: 320, background: '#1a1c1e', borderLeft: '1px solid #2a2e32',
          padding: 16, display: 'flex', flexDirection: 'column', gap: 12,
          flexShrink: 0, overflow: 'auto',
        }}
      >
        <h3 style={sectionTitle}>Hand Details</h3>

        {/* Pot & stack info */}
        {treeNode && (
          <div data-testid="pot-stack-info" style={{ background: '#0e0e0f', borderRadius: 8, padding: 12 }}>
            <div style={{ fontSize: 12, color: '#8a8f98', marginBottom: 4 }}>Pot</div>
            <div style={{ fontSize: 20, fontWeight: 700 }}>{treeNode.pot_size} bb</div>
            <div style={{ fontSize: 12, color: '#8a8f98', marginTop: 8, marginBottom: 4 }}>Remaining</div>
            <div style={{ fontSize: 16, fontWeight: 600 }}>{treeNode.stack_remaining} bb</div>
          </div>
        )}

        {/* Selected hand details */}
        {selectedHandData ? (
          <div data-testid="selected-hand-details" style={{ background: '#0e0e0f', borderRadius: 8, padding: 12 }}>
            <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 8 }}>{selectedHandData.hand}</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                <span style={{ color: '#8a8f98' }}>Action</span>
                <span style={{ color: getCellColor(selectedHandData.action, selectedHandData.frequency, GRAY), fontWeight: 600 }}>
                  {selectedHandData.action}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                <span style={{ color: '#8a8f98' }}>Frequency</span>
                <span>{(selectedHandData.frequency * 100).toFixed(1)}%</span>
              </div>
              {selectedHandData.equity !== undefined && (
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                  <span style={{ color: '#8a8f98' }}>Equity</span>
                  <span>{(selectedHandData.equity * 100).toFixed(1)}%</span>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div data-testid="no-hand-selected" style={{ color: '#555', fontSize: 13, textAlign: 'center', padding: 24 }}>
            Click a hand to see details
          </div>
        )}

        {/* Context info */}
        <div style={{ marginTop: 'auto', fontSize: 11, color: '#555' }}>
          {rangeData.length} hands • Source: preflop GTO
        </div>
      </aside>
    </div>
  )
}

// --- Shared styles ---
const sectionTitle: React.CSSProperties = {
  fontSize: 12,
  fontWeight: 600,
  color: '#8a8f98',
  textTransform: 'uppercase',
  marginBottom: 8,
}
