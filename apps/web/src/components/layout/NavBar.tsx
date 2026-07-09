'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

const NAV_ITEMS = [
  { href: '/', label: 'Dashboard' },
  { href: '/study', label: 'Study' },
  { href: '/practice', label: 'Practice' },
  { href: '/equity', label: 'Equity' },
  { href: '/icm', label: 'ICM' },
  { href: '/analyze', label: 'Analyze' },
  { href: '/strategies', label: 'Strategies' },
  { href: '/courses', label: 'Courses' },
]

export function NavBar() {
  const pathname = usePathname()

  return (
    <nav
      style={{
        height: 48,
        background: '#1a1c1e',
        borderBottom: '1px solid #2a2e32',
        display: 'flex',
        alignItems: 'center',
        padding: '0 16px',
        gap: 24,
        fontSize: 14,
        flexShrink: 0,
      }}
    >
      <Link href="/" style={{ fontWeight: 700, color: '#00b894', fontSize: 16, textDecoration: 'none' }}>
        GTO Wizard
      </Link>
      {NAV_ITEMS.map(item => (
        <Link
          key={item.href}
          href={item.href}
          style={{
            color: pathname === item.href ? '#00b894' : '#8a8f98',
            textDecoration: 'none',
            fontWeight: pathname === item.href ? 600 : 400,
            paddingBottom: 2,
            borderBottom: pathname === item.href ? '2px solid #00b894' : '2px solid transparent',
            transition: 'color 0.15s, border-color 0.15s',
          }}
        >
          {item.label}
        </Link>
      ))}
    </nav>
  )
}
