export default function PLO4Page() {
  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '32px 24px' }}>
      <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 8 }}>PLO4 & Variants</h1>
      <p style={{ color: '#8a8f98', marginBottom: 24 }}>
        Pot-Limit Omaha tools: PLO4, PLO5, Double Board, Bomb Pot, Omaha Hi/Lo.
      </p>
      <div style={{ background: '#1a1c1e', borderRadius: 12, padding: 24, border: '1px solid #2a2e32' }}>
        <div style={{ color: '#8a8f98', textAlign: 'center', padding: 48 }}>
          PLO tools — coming soon. API endpoints: POST /api/v1/plo4, /api/v1/double-board, /api/v1/bomb-pot
        </div>
      </div>
    </div>
  )
}
