'use client'

import { useState, useEffect, useCallback } from 'react'
import type { HandCell, RangeResponse, Position } from '@gto/types'

// Positions in order from earliest to latest preflop actor
const POSITIONS: Position[] = ['UTG', 'HJ', 'CO', 'BTN', 'SB', 'BB']

export interface PositionStats {
  raisePct: number
  callPct: number
  foldPct: number
  combos: number
}

// Classify a GTO action into one of three aggregate buckets.
// raise/bet/all_in -> raise (matrix colors these red/dark-red)
// call/check -> call (green)
// fold -> fold (gray in matrix)
function classifyAction(action: string): 'raise' | 'call' | 'fold' {
  const a = action.toLowerCase()
  if (a.startsWith('fold')) return 'fold'
  if (a.startsWith('call') || a.startsWith('check')) return 'call'
  return 'raise' // raise, bet, all_in
}

function computeStats(hands: HandCell[]): PositionStats {
  let raiseW = 0
  let callW = 0
  let foldW = 0
  let totalW = 0
  let combos = 0

  for (const h of hands) {
    const f = Math.max(0, Math.min(1, h.frequency))
    if (f <= 0) continue
    combos++
    totalW += f
    const bucket = classifyAction(h.action)
    if (bucket === 'raise') raiseW += f
    else if (bucket === 'call') callW += f
    else foldW += f
  }

  const safe = totalW > 0 ? totalW : 1
  return {
    raisePct: Math.round((raiseW / safe) * 1000) / 10,
    callPct: Math.round((callW / safe) * 1000) / 10,
    foldPct: Math.round((foldW / safe) * 1000) / 10,
    combos,
  }
}

async function fetchPreflopRange(
  position: Position,
  stackDepth: number,
  signal?: AbortSignal,
): Promise<HandCell[]> {
  const res = await fetch('/api/v1/solver/preflop-range', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      position,
      stack_depth: stackDepth,
      game_type: 'NLH',
      players: 6,
    }),
    signal,
  })
  if (!res.ok) throw new Error(`Failed to fetch range for ${position}`)
  const data = (await res.json()) as RangeResponse & { hands?: HandCell[] }
  return data.hands || data.range || []
}

export default function useAggregateStats(stackDepth: number) {
  const [stats, setStats] = useState<Record<Position, PositionStats>>({
    UTG: { raisePct: 0, callPct: 0, foldPct: 0, combos: 0 },
    HJ: { raisePct: 0, callPct: 0, foldPct: 0, combos: 0 },
    CO: { raisePct: 0, callPct: 0, foldPct: 0, combos: 0 },
    BTN: { raisePct: 0, callPct: 0, foldPct: 0, combos: 0 },
    SB: { raisePct: 0, callPct: 0, foldPct: 0, combos: 0 },
    BB: { raisePct: 0, callPct: 0, foldPct: 0, combos: 0 },
  })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchAll = useCallback(
    async (depth: number) => {
      const controller = new AbortController()
      let cancelled = false

      setLoading(true)
      setError(null)

      const results = await Promise.allSettled(
        POSITIONS.map((pos) =>
          fetchPreflopRange(pos, depth, controller.signal),
        ),
      )

      if (cancelled) return

      const next: Record<Position, PositionStats> = {
        UTG: { raisePct: 0, callPct: 0, foldPct: 0, combos: 0 },
        HJ: { raisePct: 0, callPct: 0, foldPct: 0, combos: 0 },
        CO: { raisePct: 0, callPct: 0, foldPct: 0, combos: 0 },
        BTN: { raisePct: 0, callPct: 0, foldPct: 0, combos: 0 },
        SB: { raisePct: 0, callPct: 0, foldPct: 0, combos: 0 },
        BB: { raisePct: 0, callPct: 0, foldPct: 0, combos: 0 },
      }

      let anyError = false
      results.forEach((r, i) => {
        if (r.status === 'fulfilled') {
          next[POSITIONS[i]] = computeStats(r.value)
        } else {
          anyError = true
        }
      })

      setStats(next)
      setLoading(false)
      if (anyError) setError('Some positions failed to load')
      return () => {
        cancelled = true
        controller.abort()
      }
    },
    [],
  )

  useEffect(() => {
    const cleanup = fetchAll(stackDepth)
    return () => {
      cleanup?.then((fn) => fn?.())
    }
  }, [stackDepth, fetchAll])

  return { stats, loading, error }
}
