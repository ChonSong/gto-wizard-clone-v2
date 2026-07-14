'use client'

import { useState, useEffect, useCallback } from 'react'
import { ACTION_COLORS } from '@/lib/tokens'
import useAggregateStats from '@/hooks/useAggregateStats'
import { AggregateFlipStrip } from '@/components/study/AggregateFlipStrip'
import { BreakdownTab } from '@/components/study/BreakdownTab'
import { StrategyTab } from '@/components/study/StrategyTab'

// --- Types ---
interface HandCell {
  hand: string
  action: string
  frequency: number
  equity?: number
}

interface TreeAction {
  position: string
  action: string
  label: string
  size?: number
}

interface TreeNodeData {
  acting_position: string
  available_actions: { id: string; actionBase: string; label: string; size?: number; frequency?: number }[]
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

// --- Constants ---
const POSITIONS = ['UTG', 'HJ', 'CO', 'BTN', 'SB', 'BB'] as const
type Position = typeof POSITIONS[number]
const RANKS = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2'] as const
const GRAY = '#2a2e32'

// --- Main Component ---
export default function StudyPage() {
  const [activePosition, setActivePosition] = useState<Position>('UTG')
  const [stackDepth, setStackDepth] = useState(100)
  const [treePath, setTreePath] = useState<TreeAction[]>([])
  const [treeNode, setTreeNode] = useState<TreeNodeData | null>(null)
  const [actionFilter, setActionFilter] = useState<string | null>(null)
  const [rangeData, setRangeData] = useState<HandCell[]>([])
  const [loading, setLoading] = useState(false)
  const [selectedHand, setSelectedHand] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'matrix' | 'breakdown' | 'strategy'>('matrix')

  const { stats: aggregateStats, loading: statsLoading, error: statsError } = useAggregateStats(stackDepth)

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

      const res = await fetch('/api/v1/solver/preflop-range', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data: RangeResponse = await res.json()
      const hands = data.hands || data.range || []
      setRangeData(hands)
      setTreeNode(data.tree_node || null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load range')
      setRangeData([])
      setTreeNode(null)
    } finally {
      setLoading(false)
    }
  }, [activePosition, stackDepth, treePath])

  useEffect(() => { fetchRange() }, [fetchRange])
  useEffect(() => {
    setTreePath([])
    setTreeNode(null)
    setActiveTab('matrix')
  }, [activePosition, stackDepth])

  function getCellColor(action: string, frequency: number): string {
    if (action === 'fold' || frequency === 0) return GRAY
    const base = action.startsWith('all_in') || action === 'all_in' ? '#c0392b'
      : action.startsWith('raise') || action.startsWith('bet') ? ACTION_COLORS.raise
      : action.startsWith('call') || action === 'check' ? ACTION_COLORS.call
      : GRAY
    return base
  }

  function getCellOpacity(cell: HandCell | undefined): number {
    if (!actionFilter) return 1
    return cell?.action.startsWith(actionFilter) ? 1 : 0.08
  }

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

  function handleHandClick(hand: string) {
    setSelectedHand(prev => prev === hand ? null : hand)
  }

  const displayPosition: Position = treeNode?.acting_position
    ? (treeNode.acting_position as Position)
    : activePosition

  const displayActions = treeNode?.available_actions || []

  const selectedHandData = selectedHand
    ? rangeData.find(h => h.hand === selectedHand)
    : null

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 48px)', overflow: 'hidden' }}>
      {/* LEFT SIDEBAR */}
      <aside style={{ width: 220, background: '#1a1c1e', borderRight: '1px solid #2a2e32', padding: 16, display: 'flex', flexDirection: 'column', gap: 8, flexShrink: 0 }}>
        <h3 style={{ fontSize: 12, fontWeight: 600, color: '#8a8f98', textTransform: 'uppercase', marginBottom: 4 }}>
          Position
        </h3>
        {POSITIONS.map(pos => (
          <div key={pos}>
            <button
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
            {pos === displayPosition && displayActions.length > 0 && (
              <div style={{ display: 'flex', gap: 4, marginTop: 4, paddingLeft: 12 }}>
                {displayActions.map(act => (
                  <button
                    key={act.id}
                    onClick={e => { e.stopPropagation(); handleActionClick(act.actionBase) }}
                    onMouseEnter={() => setActionFilter(act.actionBase)}
                    onMouseLeave={() => setActionFilter(null)}
                    style={{
                      padding: '4px 8px', borderRadius: 4,
                      border: actionFilter === act.actionBase ? `1px solid ${getCellColor(act.actionBase, 1)}` : '1px solid transparent',
                      background: actionFilter === act.actionBase ? `${getCellColor(act.actionBase, 1)}20` : 'rgba(255,255,255,0.04)',
                      color: actionFilter === act.actionBase ? getCellColor(act.actionBase, 1) : '#8a8f98',
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

        <div style={{ marginTop: 16 }}>
          <h3 style={{ fontSize: 12, fontWeight: 600, color: '#8a8f98', textTransform: 'uppercase', marginBottom: 8 }}>
            Stack Depth
          </h3>
          {[20, 40, 60, 80, 100, 150, 200].map(bb => (
            <button
              key={bb}
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
      </aside>

      {/* CENTER — Tabbed view: Matrix / Breakdown / Strategy */}
      <div style={{ flex: 1, padding: 24, overflow: 'auto', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        {/* Tab bar */}
        <div style={{ display: 'flex', gap: 0, marginBottom: 16, width: 'fit-content' }}>
          <button onClick={() => setActiveTab('matrix')} style={{
            padding: '8px 20px', border: 'none', background: activeTab === 'matrix' ? '#00b89415' : 'transparent',
            color: activeTab === 'matrix' ? '#00b894' : '#8a8f98', cursor: 'pointer', fontSize: 13, fontWeight: 600,
            borderBottom: activeTab === 'matrix' ? '2px solid #00b894' : '2px solid transparent',
          }}>Matrix</button>
          <button onClick={() => setActiveTab('breakdown')} style={{
            padding: '8px 20px', border: 'none', background: activeTab === 'breakdown' ? '#00b89415' : 'transparent',
            color: activeTab === 'breakdown' ? '#00b894' : '#8a8f98', cursor: 'pointer', fontSize: 13, fontWeight: 600,
            borderBottom: activeTab === 'breakdown' ? '2px solid #00b894' : '2px solid transparent',
          }}>Breakdown</button>
          <button onClick={() => setActiveTab('strategy')} style={{
            padding: '8px 20px', border: 'none', background: activeTab === 'strategy' ? '#00b89415' : 'transparent',
            color: activeTab === 'strategy' ? '#00b894' : '#8a8f98', cursor: 'pointer', fontSize: 13, fontWeight: 600,
            borderBottom: activeTab === 'strategy' ? '2px solid #00b894' : '2px solid transparent',
          }}>Strategy</button>
        </div>

        {/* MATRIX TAB */}
        {activeTab === 'matrix' && (
          <>
            {/* Breadcrumb */}
            {treePath.length > 0 && (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 20, padding: '8px 16px', background: '#1a1c1e', borderRadius: 8, border: '1px solid #2a2e32', fontSize: 13, width: 'fit-content' }}>
                {treePath.map((step, i) => (
                  <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    <span style={{ color: '#8a8f98' }}>{step.position}</span>
                    <span style={{ color: getCellColor(step.action, 1), fontWeight: 600 }}>{step.label}</span>
                    {i < treePath.length - 1 && <span style={{ color: '#2a2e32' }}>→</span>}
                  </span>
                ))}
                <button onClick={() => setTreePath([])} style={{ marginLeft: 8, background: 'none', border: 'none', color: '#8a8f98', cursor: 'pointer', fontSize: 14 }}>✕</button>
              </div>
            )}

            {loading && <div style={{ color: '#8a8f98', fontSize: 14, marginBottom: 16 }}>Loading range...</div>}
            {error && <div style={{ color: '#e74c3c', fontSize: 14, marginBottom: 16 }}>{error}</div>}

            {/* Matrix grid */}
            <div style={{ display: 'grid', gridTemplateColumns: `repeat(13, 48px)`, gridTemplateRows: `repeat(13, 48px)`, gap: 1, background: '#2a2e32', borderRadius: 8, overflow: 'hidden' }}>
              {RANKS.flatMap((r1, i) => RANKS.map((r2, j) => {
                const isPair = i === j; const isSuited = i < j
                const handKey = isPair ? `${r1}${r2}` : isSuited ? `${r1}${r2}s` : `${r2}${r1}o`
                const cell = rangeData.find(h => h.hand === handKey)
                const action = cell?.action || 'fold'; const freq = cell?.frequency || 0
                const color = getCellColor(action, freq)
                const opacity = getCellOpacity(cell)
                const isSelected = selectedHand === handKey
                return (
                  <button key={handKey} onClick={() => handleHandClick(handKey)}
                    style={{
                      width: 48, height: 48, border: isSelected ? '2px solid #ffffff' : '1px solid transparent',
                      borderRadius: 4, cursor: 'pointer', display: 'flex', flexDirection: 'column',
                      alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 600,
                      color: action === 'fold' || freq === 0 ? '#555' : '#fff', opacity,
                      background: action !== 'fold' && freq > 0 && freq < 1
                        ? `linear-gradient(to right, ${color} ${(freq * 100).toFixed(0)}%, ${GRAY} ${(freq * 100).toFixed(0)}%)`
                        : action !== 'fold' && freq > 0 ? color : GRAY,
                      transition: 'opacity 0.15s, filter 0.15s',
                    }}
                    onMouseEnter={e => { e.currentTarget.style.filter = 'brightness(1.3)' }}
                    onMouseLeave={e => { e.currentTarget.style.filter = 'brightness(1)' }}>
                    <span style={{ fontSize: 13 }}>{handKey}</span>
                    {freq > 0 && freq < 1 && <span style={{ fontSize: 10, background: 'rgba(0,0,0,0.45)', padding: '0 3px', borderRadius: 3 }}>{(freq * 100).toFixed(0)}%</span>}
                  </button>
                )
              }))}
            </div>

            {/* Legend */}
            <div style={{ display: 'flex', gap: 16, marginTop: 16, fontSize: 12, color: '#8a8f98' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}><span style={{ width: 12, height: 12, borderRadius: 2, background: ACTION_COLORS.raise }} /> Raise</span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}><span style={{ width: 12, height: 12, borderRadius: 2, background: ACTION_COLORS.call }} /> Call</span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}><span style={{ width: 12, height: 12, borderRadius: 2, background: '#c0392b' }} /> All-in</span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}><span style={{ width: 12, height: 12, borderRadius: 2, background: GRAY }} /> Fold</span>
            </div>

            {statsLoading && <div style={{ color: '#8a8f98', fontSize: 14, marginTop: 20 }}>Loading stats...</div>}
            {statsError && <div style={{ color: '#e74c3c', fontSize: 13, marginTop: 12 }}>{statsError}</div>}
            {!statsLoading && !statsError && <AggregateFlipStrip stats={aggregateStats} activePosition={activePosition} onPositionClick={setActivePosition} />}
          </>
        )}

        {/* BREAKDOWN TAB */}
        {activeTab === 'breakdown' && (
          <BreakdownTab rangeData={rangeData} onHandClick={setSelectedHand} />
        )}

        {/* STRATEGY TAB */}
        {activeTab === 'strategy' && (
          <StrategyTab rangeData={rangeData} onHandClick={setSelectedHand} />
        )}
      </div>

      {/* RIGHT PANEL */}
      <aside style={{ width: 320, background: '#1a1c1e', borderLeft: '1px solid #2a2e32', padding: 16, display: 'flex', flexDirection: 'column', gap: 12, flexShrink: 0, overflow: 'auto' }}>
        <h3 style={{ fontSize: 12, fontWeight: 600, color: '#8a8f98', textTransform: 'uppercase' }}>Overview</h3>

        {treeNode && (
          <div style={{ background: '#0e0e0f', borderRadius: 8, padding: 12 }}>
            <div style={{ fontSize: 12, color: '#8a8f98', marginBottom: 4 }}>Pot</div>
            <div style={{ fontSize: 20, fontWeight: 700 }}>{treeNode.pot_size} bb</div>
            <div style={{ fontSize: 12, color: '#8a8f98', marginTop: 8, marginBottom: 4 }}>Remaining</div>
            <div style={{ fontSize: 16, fontWeight: 600 }}>{treeNode.stack_remaining} bb</div>
          </div>
        )}

        {selectedHandData ? (
          <div style={{ background: '#0e0e0f', borderRadius: 8, padding: 12 }}>
            <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 8 }}>{selectedHandData.hand}</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                <span style={{ color: '#8a8f98' }}>Action</span>
                <span style={{ color: getCellColor(selectedHandData.action, selectedHandData.frequency), fontWeight: 600 }}>{selectedHandData.action}</span>
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
          <div style={{ color: '#555', fontSize: 13, textAlign: 'center', padding: 24 }}>
            Click a hand to see details
          </div>
        )}

        <div style={{ marginTop: 'auto', fontSize: 11, color: '#555' }}>
          {rangeData.length} hands • Source: preflop GTO
        </div>
      </aside>
    </div>
  )
}
