# Aggregate Flip Strip — Workflow Design

## Phase 1: Scope

```yaml
workflow: "View aggregate F/C/R stats for all positions"
persona: "Poker player studying preflop ranges"
goal: "At a glance, see fold/call/raise percentages and combo counts for every position"
trigger: "Page loads with a position selected"
done: "All 6 position stats visible, color-coded, updating when position/stack changes"
```

## Phase 2: Step Sequence

### Step 1: Page loads → aggregate strip visible
**User action:** Navigate to /study
**UI state before:** Range matrix visible for UTG
**UI state after:** Below matrix (or in sidebar), 6 position chips each showing F%/C%/R% + combo count
**Data:** Derive from `rangeData` state — but only for currently fetched position. Need ALL 6 positions.
**Data dependencies:** Need to fetch all 6 positions' data on page load

### Step 2: Position changes → strip updates
**User action:** Click a position (e.g., HJ)
**UI state before:** Strip shows previous aggregate
**UI state after:** Strip reflects new active position's full 6-position data

## Phase 3: State Machines

```
LOADING → ALL_FETCHED → DISPLAY
ERROR → RETRY
```
Fetch all 6 positions on mount. Cache results. Re-fetch on stack depth change.

## Phase 4: Implementation Tasks

### Task A: Data hook (`useAggregateStats`)
- Source: Step 1
- Fetches all 6 positions' ranges from API
- Computes per-position: fold%, call%, raise%, combo count
- Returns: `{ [position]: { fold, call, raise, combos } }`

### Task B: AggregateFlipStrip component
- Source: Step 1
- Renders horizontal bar with 6 position chips
- Each chip shows: position name, F/C/R percentages, combo count
- Color-coded bars matching action colors

### Task C: Integration into Study page
- Source: Step 1-2
- Add strip below matrix (center area, after legend)
- Wire to useAggregateStats hook
- Auto-update on position/stack change

## File Partition

```
Subagent 1: src/hooks/useAggregateStats.ts  (data fetching + computation)
Subagent 2: src/components/study/AggregateFlipStrip.tsx  (UI component)
Subagent 3: src/app/study/page.tsx  (integration — wire component)
Subagent 4: tests/  (Playwright E2E test for strip visibility)
```

No file overlaps → zero merge conflicts.
