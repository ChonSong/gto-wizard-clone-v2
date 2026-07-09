export default function CoursesPage() {
  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '32px 24px' }}>
      <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 8 }}>Training Courses</h1>
      <p style={{ color: '#8a8f98', marginBottom: 24 }}>
        Structured learning modules. Master GTO concepts step by step.
      </p>
      <div style={{ background: '#1a1c1e', borderRadius: 12, padding: 24, border: '1px solid #2a2e32' }}>
        <div style={{ color: '#8a8f98', textAlign: 'center', padding: 48 }}>
          Courses — coming soon. API endpoint: GET /api/v1/courses
        </div>
      </div>
    </div>
  )
}
