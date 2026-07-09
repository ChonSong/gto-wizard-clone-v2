# AGENTS.md — GTO Wizard Clone v2

## About
Open-source GTO poker training platform. Live at `wiz.codeovertcp.com` (v1). This is v2 — rebuilt with correct architecture.

## Architecture Rule #1: Study ≠ Practice

**Study page (`/study`):** Pure range browser. Displays GTO ranges. Traverses game tree via action buttons. NO quiz mechanics — no "Check vs GTO", no correct/incorrect feedback, no stats tracking, no mode toggle.

**Practice page (`/practice`):** Quiz/training mode. Spot → player action → GTO comparison → score. HAS the quiz loop.

**NEVER mix these.** Study is a browser, Practice is a game.

## Stack
- **Frontend**: Next.js 15 + React 19 + TypeScript + Tailwind CSS v4
- **Backend**: Python 3.12 FastAPI on port 8001
- **Solver**: Python MCCFR engine (apps/solver/)
- **Cache**: Redis (with Fakeredis fallback)
- **Database**: PostgreSQL (with SQLite fallback)
- **Monorepo**: Turbo

## Key Directories
| Path | Purpose |
|------|---------|
| `apps/web/` | Next.js frontend |
| `apps/web/src/app/study/page.tsx` | Strategy browser (NO QUIZ) |
| `apps/web/src/app/practice/page.tsx` | Training quiz (HAS QUIZ LOOP) |
| `apps/api/` | FastAPI backend |
| `apps/solver/` | MCCFR solver engine |
| `packages/poker-core/` | Shared poker logic (14 modules, 7 variants) |
| `packages/ui-components/` | Shared React components |
| `packages/types/` | TypeScript type definitions |

## API Routes
`/api/v1/equity`, `/api/v1/solver`, `/api/v1/strategy`, `/api/v1/quiz`, `/api/v1/icm`,
`/api/v1/hh`, `/api/v1/courses`, `/api/v1/plo4`, `/api/v1/double-board`, `/api/v1/bomb-pot`

## Conventions
- **Setup**: `npm install && pip install -e packages/poker-core`
- **Python tests**: `python -m pytest packages/poker-core/tests/`
- **Frontend tests**: `cd apps/web && npx vitest run`
- **E2E**: `cd apps/web && npx playwright test`
- **Commits**: Conventional commits (`feat:`, `fix:`, `test:`, `docs:`)
- **Python**: 3.12+, ruff linting (line-length 100)

## Design Tokens
```css
--bg: #0e0e0f; --panel: #1a1c1e; --border: #2a2e32;
--text: #d7d7d7; --muted: #8a8f98; --teal: #00b894;
--green: #2ecc71; --red: #e74c3c; --orange: #e67e22;
--blue: #3498db;
```

## Study Page Action Button Rules
- **Hover** on position card action button → filter grid (dim non-matching to 0.08)
- **Click** on position card action button → traverse game tree
- **Click** different position → reset tree, load new RFI range
- **Change** stack depth → reset tree
- Action buttons live on POSITION CARDS (sidebar), NOT in grid cells

## Common Pitfalls
1. Study page has no quiz — don't add "Check vs GTO" or stats tracking
2. Practice page is separate — don't merge with study
3. Mode transitions (preflop→postflop) are automatic, not manual toggles
4. `treePath` is the game tree state — clicking action buttons appends to it
5. Use design tokens from `apps/web/src/lib/tokens.ts`, not hardcoded colors
6. Mixed-frequency hands use CSS gradient, not separate component

## Quick Start
```bash
# Backend
PYTHONPATH=apps/api:. uvicorn apps.api.main:app --host 0.0.0.0 --port 8001

# Frontend
npm install && npm run dev  # → http://localhost:3000
```
