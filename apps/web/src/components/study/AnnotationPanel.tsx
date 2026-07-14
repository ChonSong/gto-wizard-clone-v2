'use client'

import { useState, useEffect, useCallback } from 'react'

interface Annotation {
  id: string
  hand: string
  content: string
  author: string
  is_ai_suggested: number
  accepted: number
  created_at: string
}

interface AnnotationPanelProps {
  open: boolean
  onClose: () => void
  spotHash: string
  hand: string
  board: string
  position: string
  stackDepth: number
  treePath: string[]
  action: string
  frequency: number
}

export default function AnnotationPanel({
  open,
  onClose,
  spotHash,
  hand,
  board,
  position,
  stackDepth,
  treePath,
  action,
  frequency,
}: AnnotationPanelProps) {
  const [annotations, setAnnotations] = useState<Annotation[]>([])
  const [newComment, setNewComment] = useState('')
  const [loading, setLoading] = useState(false)
  const [suggesting, setSuggesting] = useState(false)

  const loadAnnotations = useCallback(async () => {
    if (!spotHash || !hand) return
    try {
      const res = await fetch(`/api/v1/annotations/spot/${spotHash}?hand=${hand}`)
      if (res.ok) {
        const data = await res.json()
        setAnnotations(data)
      }
    } catch (e) {
      console.error('Failed to load annotations:', e)
    }
  }, [spotHash, hand])

  useEffect(() => {
    if (open) loadAnnotations()
  }, [open, loadAnnotations])

  const handleAddComment = async () => {
    if (!newComment.trim()) return
    setLoading(true)
    try {
      const res = await fetch('/api/v1/annotations/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          spot_hash: spotHash,
          hand,
          board,
          position,
          stack_depth: stackDepth,
          tree_path: treePath,
          content: newComment,
        }),
      })
      if (res.ok) {
        setNewComment('')
        loadAnnotations()
      }
    } catch (e) {
      console.error('Failed to add annotation:', e)
    } finally {
      setLoading(false)
    }
  }

  const handleSuggest = async () => {
    setSuggesting(true)
    try {
      const res = await fetch('/api/v1/suggest/annotation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          hand,
          board,
          position,
          stack_depth: stackDepth,
          action,
          frequency,
          tree_path: treePath,
        }),
      })
      if (res.ok) {
        const data = await res.json()
        setNewComment(data.suggestion)
      }
    } catch (e) {
      console.error('Failed to get suggestion:', e)
    } finally {
      setSuggesting(false)
    }
  }

  if (!open) return null

  return (
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: '#1a1c1e', borderRadius: 12, padding: 24, width: 480,
          border: '1px solid #2a2e32', maxHeight: '80vh', overflow: 'auto',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <div>
            <h3 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>Annotations</h3>
            <div style={{ fontSize: 12, color: '#8a8f98', marginTop: 4 }}>
              {hand} on {board || 'preflop'}
            </div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#8a8f98', cursor: 'pointer', fontSize: 18 }}>✕</button>
        </div>

        {/* Existing annotations */}
        {annotations.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            {annotations.map((ann) => (
              <div
                key={ann.id}
                style={{
                  background: '#0e0e0f', borderRadius: 6, padding: 12, marginBottom: 8,
                  border: '1px solid #2a2e32',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                  <span style={{ fontSize: 11, color: '#8a8f98' }}>
                    {ann.author} {ann.is_ai_suggested ? '🤖 AI' : ''}
                  </span>
                  <span style={{ fontSize: 10, color: '#555' }}>
                    {new Date(ann.created_at).toLocaleDateString()}
                  </span>
                </div>
                <div style={{ fontSize: 13, lineHeight: 1.5 }}>{ann.content}</div>
              </div>
            ))}
          </div>
        )}

        {/* Suggest button */}
        <button
          onClick={handleSuggest}
          disabled={suggesting}
          style={{
            width: '100%', padding: '8px 12px', borderRadius: 6,
            border: '1px solid #3498db40', background: '#3498db15',
            color: '#3498db', cursor: 'pointer', fontSize: 12, fontWeight: 600,
            marginBottom: 12,
          }}
        >
          {suggesting ? '🔄 Regenerate' : '🤖 Suggest Annotation'}
        </button>

        {/* New comment input */}
        <textarea
          value={newComment}
          onChange={(e) => setNewComment(e.target.value)}
          placeholder="Add your annotation..."
          style={{
            width: '100%', minHeight: 80, padding: 10, borderRadius: 6,
            border: '1px solid #2a2e32', background: '#0e0e0f',
            color: '#d7d7d7', fontSize: 13, resize: 'vertical',
            marginBottom: 12,
          }}
        />

        {/* Action buttons */}
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            onClick={handleAddComment}
            disabled={loading || !newComment.trim()}
            style={{
              flex: 1, padding: '10px 16px', borderRadius: 6,
              border: 'none', background: '#00b894', color: '#fff',
              cursor: 'pointer', fontSize: 13, fontWeight: 600,
              opacity: loading || !newComment.trim() ? 0.5 : 1,
            }}
          >
            {loading ? 'Saving...' : 'Save Annotation'}
          </button>
          <button
            onClick={onClose}
            style={{
              padding: '10px 16px', borderRadius: 6,
              border: '1px solid #2a2e32', background: 'transparent',
              color: '#8a8f98', cursor: 'pointer', fontSize: 13,
            }}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
