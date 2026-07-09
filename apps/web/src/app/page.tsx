import Link from 'next/link'

const FEATURES = [
  { title: 'Strategy Browser', desc: 'Explore GTO ranges by position and stack depth', href: '/study', color: '#00b894' },
  { title: 'Training Quizzes', desc: 'Test your decisions against GTO solutions', href: '/practice', color: '#e74c3c' },
  { title: 'Equity Calculator', desc: 'Compute hand vs range equity', href: '/equity', color: '#3498db' },
  { title: 'ICM Calculator', desc: 'Tournament chip equity analysis', href: '/icm', color: '#e67e22' },
  { title: 'Hand History', desc: 'Upload and analyze your hands', href: '/analyze', color: '#2ecc71' },
  { title: 'PLO Variants', desc: 'PLO4, PLO5, Double Board, Bomb Pot', href: '/plo4', color: '#9b59b6' },
]

export default function Home() {
  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '48px 24px' }}>
      <div style={{ textAlign: 'center', marginBottom: 48 }}>
        <h1 style={{ fontSize: 36, fontWeight: 700, marginBottom: 12 }}>GTO Wizard</h1>
        <p style={{ color: '#8a8f98', fontSize: 16, maxWidth: 560, margin: '0 auto' }}>
          Open-source GTO poker training platform. Study Nash equilibrium strategies, practice your decisions,
          and analyze your game — all in one place.
        </p>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
          gap: 16,
        }}
      >
        {FEATURES.map(f => (
          <Link
            key={f.href}
            href={f.href}
            style={{
              textDecoration: 'none',
              background: '#1a1c1e',
              border: '1px solid #2a2e32',
              borderRadius: 12,
              padding: 24,
              transition: 'transform 0.15s, box-shadow 0.15s',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.transform = 'translateY(-2px)'
              e.currentTarget.style.boxShadow = `0 4px 20px ${f.color}20`
            }}
            onMouseLeave={e => {
              e.currentTarget.style.transform = 'translateY(0)'
              e.currentTarget.style.boxShadow = 'none'
            }}
          >
            <div
              style={{
                width: 40,
                height: 40,
                borderRadius: 8,
                background: `${f.color}20`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                marginBottom: 16,
                fontSize: 20,
              }}
            >
              {/* icon placeholder */}
            </div>
            <h3 style={{ color: f.color, fontSize: 18, fontWeight: 600, marginBottom: 8 }}>
              {f.title}
            </h3>
            <p style={{ color: '#8a8f98', fontSize: 14, lineHeight: 1.5 }}>{f.desc}</p>
          </Link>
        ))}
      </div>
    </div>
  )
}
