export default function AnalyzePage() {
  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '32px 24px' }}>
      <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 8 }}>Hand History Analyzer</h1>
      <p style={{ color: '#8a8f98', marginBottom: 24 }}>
        Upload your PokerStars hand histories. Get leak analysis and GTO comparison.
      </p>
      <div style={{ background: '#1a1c1e', borderRadius: 12, padding: 24, border: '1px solid #2a2e32' }}>
        <div style={{ color: '#8a8f98', textAlign: 'center', padding: 48 }}>
          HH Analyzer — coming soon. API endpoints: POST /api/v1/hh/upload, GET /api/v1/hh/analyze
        </div>
      </div>
    </div>
  )
}
