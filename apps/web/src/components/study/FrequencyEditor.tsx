'use client'

import { useState, useCallback, useEffect, useRef } from 'react'
import { ACTION_COLORS } from '@/lib/tokens'

// --- Types ---
interface HandCell {
  hand: string
  action: string
  frequency: number
  equity?: number
}

interface HandLock {
  actions: Record<string, number>  // {"fold": 0.3, "call": 0.7}
}

interface FrequencyEditorProps {
  hand: string
  currentAction: string
  currentFreq: number
  availableActions: { id: string; actionBase: string; label: string; size?: number }[]
  existingLock?: HandLock
  onLock: (hand: string, lock: HandLock | null) => void
  onClose: () => void
}

export function FrequencyEditor({
  hand,
  currentAction,
  currentFreq,
  availableActions,
  existingLock,
  onLock,
  onClose,
}: FrequencyEditorProps) {
  const [actions, setActions] = useState<Record<string, number>>(() => {
    if (existingLock?.actions) return { ...existingLock.actions }
    // Default: current action at current frequency
    const base = currentAction.replace(/_\d+bb$/, '').replace(/_\d+\.\d+bb$/, '')
    return { [base]: currentFreq }
  })

  const popoverRef = useRef<HTMLDivElement>(null)

  // Close on Escape
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [onClose])

  // Close on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        onClose()
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [onClose])

  const updateAction = useCallback((actionBase: string, value: number) => {
    setActions(prev => {
      const next = { ...prev }
      if (value <= 0.001) {
        delete next[actionBase]
      } else {
        next[actionBase] = Math.round(value * 100) / 100
      }
      return next
    })
  }, [])

  const total = Object.values(actions).reduce((sum, f) => sum + f, 0)
  const isValid = total <= 1.001 && total > 0

  const handleApply = () => {
    if (!isValid) return
    // Normalize to exactly 1.0
    const normalized: Record<string, number> = {}
    for (const [act, freq] of Object.entries(actions)) {
      normalized[act] = Math.round((freq / total) * 100) / 100
    }
    onLock(hand, { actions: normalized })
  }

  const handleClear = () => {
    onLock(hand, null)
  }

  const actionColor = (base: string) => {
    if (base === 'fold') return '#3498db'
    if (base === 'call' || base === 'check') return '#2ecc71'
    if (base === 'raise' || base === 'bet') return '#e74c3c'
    if (base === 'all_in') return '#c0392b'
    return '#8a8f98'
  }

  return (
    <div
      ref={popoverRef}
      style={{
        position: 'absolute',
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        background: '#1a1c1e',
        border: '1px solid #2a2e32',
        borderRadius: 12,
        padding: 16,
        zIndex: 1000,
        minWidth: 260,
        boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <h4 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>{hand} — Lock Frequencies</h4>
        <button
          onClick={onClose}
          style={{
            background: 'none',
            border: 'none',
            color: '#8a8f98',
            cursor: 'pointer',
            fontSize: 16,
            padding: 0,
          }}
        >
          ✕
        </button>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 12 }}>
        {availableActions.map(act => {
          const val = actions[act.actionBase] || 0
          return (
            <div key={act.id} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 11, fontWeight: 600, width: 60, color: actionColor(act.actionBase) }}>
                {act.label}
              </span>
              <input
                type="range"
                min={0}
                max={100}
                value={Math.round(val * 100)}
                onChange={e => updateAction(act.actionBase, parseInt(e.target.value) / 100)}
                style={{ flex: 1, accentColor: actionColor(act.actionBase) }}
              />
              <span style={{ fontSize: 11, width: 36, textAlign: 'right', color: '#8a8f98' }}>
                {Math.round(val * 100)}%
              </span>
            </div>
          )
        })}
      </div>

      <div style={{
        fontSize: 11,
        color: isValid ? '#8a8f98' : '#e74c3c',
        marginBottom: 12,
        textAlign: 'center',
      }}>
        Total: {Math.round(total * 100)}%{isValid ? '' : ' (must be ≤ 100%)'}
      </div>

      <div style={{ display: 'flex', gap: 8 }}>
        {existingLock && (
          <button
            onClick={handleClear}
            style={{
              flex: 1,
              padding: '6px 12px',
              borderRadius: 6,
              border: '1px solid #e74c3c',
              background: 'transparent',
              color: '#e74c3c',
              cursor: 'pointer',
              fontSize: 12,
              fontWeight: 600,
            }}
          >
            Unlock
          </button>
        )}
        <button
          onClick={handleApply}
          disabled={!isValid}
          style={{
            flex: 1,
            padding: '6px 12px',
            borderRadius: 6,
            border: 'none',
            background: isValid ? '#00b894' : '#2a2e32',
            color: isValid ? '#fff' : '#555',
            cursor: isValid ? 'pointer' : 'not-allowed',
            fontSize: 12,
            fontWeight: 600,
          }}
        >
          🔒 Lock
        </button>
      </div>
    </div>
  )
}
