# Handoff

## State

- Active development — v2 rebuild in progress.
- Core backend (equity, solver, strategy, quiz, ICM, HH) is live.
- Frontend (Next.js 15 + React 19) connected to backend.
- Study and practice pages are separate concerns — never merge them.

## Next Actions

- [ ] Live deploy v2 to replace v1 deployment at wiz.codeovertcp.com
- [ ] Study page complete game tree browsing
- [ ] Practice page quiz scoring + progress tracking
- [ ] PLO and bomb-pot support

## Verify Before Ship

- [ ] `python -m pytest packages/poker-core/tests/ -v` passes
- [ ] `cd apps/web && npx vitest run` passes
- [ ] `ruff check .` passes
