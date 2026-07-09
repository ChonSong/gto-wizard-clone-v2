export default function EquityPage() {
  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '32px 24px' }}>
      <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 8 }}>Equity Calculator</h1>
      <p style={{ color: '#8a8f98', marginBottom: 24 }}>
        Calculate hand vs range equity using Monte Carlo simulation. Select hero hand and villain ranges.
      </p>
      <div style={{ background: '#1a1c1e', borderRadius: 12, padding: 24, border: '1px solid #2a2e32' }}>
        <div style={{ color: '#8a8f98', textAlign: 'center', padding: 48 }}>
          Equity calculator — coming soon. API endpoint: POST /api/v1/equity
        </div>
      </div>
    </div>
  )
}
