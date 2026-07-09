# GTO Wizard Clone v2 — Architecture Spec

## Philosophy
Study page = **range browser** with game tree navigation. Practice page = **quiz/training mode**.
These are separate pages with separate UX philosophies. Never mix them.

## Architecture

```
apps/
  web/              # Next.js 15 frontend (React 19, TypeScript, Tailwind v4, Shadcn UI)
  api/              # FastAPI (Python 3.12) REST + WebSocket
  solver/           # Python MCCFR engine (CFR, Numba JIT)
packages/
  poker-core/       # Shared: deck, hand eval, equity, range, variants (Python + TS bindings)
  ui-components/    # Shared React components (RangeGrid, BoardRenderer, etc.)
  types/            # Shared TypeScript types
```

## Page Architecture

| Page | Route | What it does | UX philosophy |
|------|-------|-------------|---------------|
| Dashboard | `/` | Feature overview, quick links | Landing |
| Study | `/study` | Browse GTO ranges, traverse game tree | **Browser** — no quiz |
| Practice | `/practice` | Quiz spots vs GTO, track stats | **Game** — quiz loop |
| Equity | `/equity` | Hand vs range equity calculator | Tool |
| ICM | `/icm` | Tournament chip equity | Tool |
| Hand History | `/analyze` | Upload HH, leak detection | Tool |
| Strategies | `/strategies` | Strategy lookup by position/stack | Reference |
| Courses | `/courses` | Structured learning modules | Reference |
| PLO4 | `/plo4` | PLO variant tools | Tool |
| Double Board | `/double-board` | Double board PLO | Tool |
| Bomb Pot | `/bomb-pot` | Bomb pot variant | Tool |
| Push/Fold | `/push-fold` | Push/fold charts | Reference |

## Study Page — Definitive Rules

These rules are non-negotiable. They were learned through 2 rounds of rebuilding.

**Study page IS:**
- A range browser that displays GTO ranges by position and stack depth
- A game tree navigator — clicking action buttons advances the decision tree
- Static reference data: hand actions, frequencies, combo counts, sizing
- Read-only analysis views: Overview, Table, Equity Chart

**Study page IS NOT:**
- A quiz or training mode
- No "Check vs GTO" buttons
- No correct/incorrect feedback
- No "Try Again" buttons
- No quiz stats (correct/total/streak)
- No mode toggle switching between unrelated UIs

**Mode transitions are automatic:** When preflop round completes (all 6 positions acted), the page auto-deals flop cards and switches to postflop view. No manual toggle.

**Action buttons on position cards:**
- Hover → filter the grid (dim non-matching cells)
- Click → traverse game tree (append to treePath)
- Click different position → reset tree, new RFI range
- Change stack depth → reset tree

## Practice Page — Quiz Architecture

- Game loop: spot → player action → GTO comparison → score
- Spaced repetition for weak spots
- Track: accuracy, EV loss, category breakdown
- Modes: Preflop, Postflop, Mixed, Custom

## Tech Stack

| Layer | Choice |
|-------|--------|
| Frontend | Next.js 15 + React 19 + TypeScript + Tailwind v4 + Shadcn UI |
| Backend | FastAPI (Python 3.12) + Pydantic v2 |
| Solver | Python MCCFR + NumPy + Numba |
| Database | PostgreSQL (Neon serverless) + SQLite fallback |
| Cache | Redis + Fakeredis fallback |
| Monorepo | Turbo + Nx |

## API Routes

```
/api/v1/equity          — Hand vs range equity
/api/v1/solver          — MCCFR solver (preflop ranges, postflop solves)
/api/v1/strategy        — Strategy lookup by position/stack/board
/api/v1/quiz            — Quiz spots, submission, stats
/api/v1/icm             — ICM calculator
/api/v1/hh              — Hand history upload, analysis, export
/api/v1/courses         — Training courses
/api/v1/plo4            — PLO4 variant tools
/api/v1/double-board    — Double board PLO
/api/v1/bomb-pot        — Bomb pot variant
/api/v1/push-fold       — Push/fold charts
/ws                     — WebSocket for solver progress
```

## Design Tokens

```css
--bg: #0e0e0f;
--panel: #1a1c1e;
--border: #2a2e32;
--text: #d7d7d7;
--muted: #8a8f98;
--teal: #00b894;
--green: #2ecc71;
--red: #e74c3c;
--orange: #e67e22;
```

Font: Inter, system-ui, sans-serif
