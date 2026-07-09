import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { NavBar } from '@/components/layout/NavBar'

const inter = Inter({ subsets: ['latin'], variable: '--font-inter' })

export const metadata: Metadata = {
  title: 'GTO Wizard',
  description: 'Open-source GTO poker training platform — equity calculator, CFR solver, strategy browser, and training quizzes',
  manifest: '/manifest.json',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="min-h-screen flex flex-col" style={{ background: '#0e0e0f', color: '#d7d7d7' }}>
        <NavBar />
        <main className="flex-1 overflow-auto">{children}</main>
      </body>
    </html>
  )
}
