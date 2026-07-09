export default function StrategiesPage() {
  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '32px 24px' }}>
      <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 8 }}>Strategy Lookup</h1>
      <p style={{ color: '#8a8f98', marginBottom: 24 }}>
        Browse GTO strategies by position, stack depth, and board texture.
      </p>
      <div style={{ background: '#1a1c1e', borderRadius: 12, padding: 24, border: '1px solid #2a2e32' }}>
        <div style={{ color: '#8a8f98', textAlign: 'center', padding: 48 }}>
          Strategy lookup — coming soon. API endpoint: GET /api/v1/strategy
        </div>
      </div>
    </div>
  )
}
