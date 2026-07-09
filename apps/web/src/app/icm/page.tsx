export default function ICMPage() {
  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '32px 24px' }}>
      <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 8 }}>ICM Calculator</h1>
      <p style={{ color: '#8a8f98', marginBottom: 24 }}>
        Tournament Independent Chip Model. Convert chip stacks to real money equity.
      </p>
      <div style={{ background: '#1a1c1e', borderRadius: 12, padding: 24, border: '1px solid #2a2e32' }}>
        <div style={{ color: '#8a8f98', textAlign: 'center', padding: 48 }}>
          ICM calculator — coming soon. API endpoint: POST /api/v1/icm
        </div>
      </div>
    </div>
  )
}
