'use client'

import { useState } from 'react'

interface ExportModalProps {
  open: boolean
  onClose: () => void
  position: string
  stackDepth: number
  board: string
  treePath: string[]
  actions: Array<{ hand: string; action: string; frequency: number; equity?: number }>
}

export default function ExportModal({
  open,
  onClose,
  position,
  stackDepth,
  board,
  treePath,
  actions,
}: ExportModalProps) {
  const [format, setFormat] = useState<'json' | 'pio' | 'gto-plus'>('json')
  const [copied, setCopied] = useState(false)

  if (!open) return null

  const handleExport = async () => {
    const res = await fetch(`/api/v1/export/${format}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        position,
        stack_depth: stackDepth,
        board,
        tree_path: treePath,
        actions,
      }),
    })
    const data = await res.json()

    // Download file
    const blob = new Blob([data.content], { type: data.mime })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = data.filename
    a.click()
    URL.revokeObjectURL(url)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleCopy = async () => {
    const res = await fetch(`/api/v1/export/${format}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        position,
        stack_depth: stackDepth,
        board,
        tree_path: treePath,
        actions,
      }),
    })
    const data = await res.json()
    await navigator.clipboard.writeText(data.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

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
          background: '#1a1c1e', borderRadius: 12, padding: 24, width: 500,
          border: '1px solid #2a2e32', maxHeight: '80vh', overflow: 'auto',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>Export Spot</h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#8a8f98', cursor: 'pointer', fontSize: 18 }}>✕</button>
        </div>

        {/* Format selector */}
        <div style={{ marginBottom: 16 }}>
          <label style={{ fontSize: 12, color: '#8a8f98', display: 'block', marginBottom: 6 }}>Format</label>
          <div style={{ display: 'flex', gap: 8 }}>
            {[
              { id: 'json', label: 'GTO Wizard JSON', desc: 'Round-trip' },
              { id: 'pio', label: 'PioSOLVER CSV', desc: 'Import to Pio' },
              { id: 'gto-plus', label: 'GTO+ TXT', desc: 'Power-Equilab' },
            ].map((f) => (
              <button
                key={f.id}
                onClick={() => setFormat(f.id as any)}
                style={{
                  flex: 1, padding: '8px 12px', borderRadius: 6,
                  border: format === f.id ? '1px solid #00b894' : '1px solid #2a2e32',
                  background: format === f.id ? '#00b89415' : 'transparent',
                  color: format === f.id ? '#00b894' : '#8a8f98',
                  cursor: 'pointer', fontSize: 12, fontWeight: 600,
                }}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        {/* Spot info */}
        <div style={{
          background: '#0e0e0f', borderRadius: 6, padding: 12, marginBottom: 16,
          fontSize: 12, color: '#8a8f98',
        }}>
          <div><strong>Position:</strong> {position} | <strong>Stack:</strong> {stackDepth}bb</div>
          <div><strong>Board:</strong> {board || 'Preflop'}</div>
          {treePath.length > 0 && <div><strong>Action:</strong> {treePath.join(' → ')}</div>}
          <div><strong>Hands:</strong> {actions.length}</div>
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            onClick={handleExport}
            style={{
              flex: 1, padding: '10px 16px', borderRadius: 6,
              border: 'none', background: '#00b894', color: '#fff',
              cursor: 'pointer', fontSize: 13, fontWeight: 600,
            }}
          >
            {copied ? '✓ Downloaded!' : 'Download File'}
          </button>
          <button
            onClick={handleCopy}
            style={{
              padding: '10px 16px', borderRadius: 6,
              border: '1px solid #2a2e32', background: 'transparent',
              color: '#8a8f98', cursor: 'pointer', fontSize: 13,
            }}
          >
            Copy
          </button>
        </div>
      </div>
    </div>
  )
}
