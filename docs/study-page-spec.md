# Study Page Specification v2

## Source Material
- Reference interaction spec: `https://github.com/ChonSong/gto-wizard-clone/blob/main/docs/reference-study-interaction-spec.md`
- Visual comparison report: `https://github.com/ChonSong/gto-wizard-clone/blob/main/docs/reference-comparison-gtowizard.md`
- Reference screenshots: `reference-study.png`, `reference-study-top.png`, `reference-study-interface.png`
- v1 architectural rules: `poker-training-platform` skill
- v2 current implementation: `apps/web/src/app/study/page.tsx`

## Core Identity: Study Page = Range Browser, NOT Quiz

**This rule is non-negotiable** (learned through 2 rebuilds in v1):

| Study page IS | Study page IS NOT |
|--------------|-------------------|
| Display GTO ranges by position/stack | A quiz/training mode |
| Game tree navigation via action clicks | "Check vs GTO" buttons |
| Read-only analysis views | Correct/incorrect feedback |
| Traverse preflop→flop→turn→river | "Try Again" buttons |
| Static reference data | Quiz stats (correct/total/streak) |

## Layout (v2 Design — User Deliberately Deviated from Original)

The real GTO Wizard uses a **horizontal top position bar** + left tabs. The user chose a **left sidebar position layout** for v2. This is a deliberate design decision.

```
┌──────────────────────────────────────────────────────┐
│ Top Nav: GTO Wizard | Study | Practice | Equity | …  │
├────────┬─────────────────────────┬───────────────────┤
│ Left   │ CENTER                  │ RIGHT             │
│ Sidebar│                         │ Panel             │
│ 220px  │ flex:1                  │ 320px             │
│        │                         │                   │
│ POSIT- │ Context description     │ OVERVIEW          │
│ ION    │ (rfi / vs raise / ...)  │                   │
│        │                         │ Pot / Remaining   │
│ [UTG]  │ Breadcrumb (tree path)  │ (when in tree)    │
│ [HJ]   │                         │                   │
│ [CO]   │ ┌─────────────────────┐ │ Selected hand     │
│ [BTN]  │ │   13×13 MATRIX     │ │ details           │
│ [SB]   │ │   (169 buttons)    │ │ (action, freq,    │
│ [BB]   │ │                     │ │  equity, combos)  │
│        │ └─────────────────────┘ │                   │
│ STACK  │                         │ N hands • Source  │
│ DEPTH  │ Legend (colors)         │                   │
│ [20bb] │                         │                   │
│ ...    │                         │                   │
└────────┴─────────────────────────┴───────────────────┘
```

## Zones

### Zone 1: Left Sidebar (220px)

Contains position cards and stack depth selector.

#### Position Cards (6)
Each position shows:
- **Name**: UTG, HJ, CO, BTN, SB, BB
- **Active state**: Highlighted (green bg, green text) for selected position
- **Action buttons** (on active position only): Fold, Raise N, Allin N
  - **Hover** → filter the grid (dim non-matching cells to 0.08 opacity)
  - **Click** → traverse game tree (append to `treePath` state)
  - Call button only for SB/BB
  - Raise sizing: 2.5bb for non-blind positions, 3bb for SB/BB
- **Minimized state**: Non-active positions show only name (no action buttons)

On position click:
1. Set `activePosition` to clicked position
2. Reset `treePath` to `[]` and `treeNode` to `null` (new RFI range)
3. `useEffect([activePosition, stackDepth, treePath])` triggers API fetch
4. API returns range data + optional `tree_node`

#### Stack Depth Selector
Buttons: 20, 40, 60, 80, 100, 150, 200 (bb)
- Selected highlighted with green accent
- Changing stack depth resets the tree (same as position change)

#### Aggregate Flip Strip (TODO)
Currently not implemented in v2. The v1 had it. Shows:
- Position name (e.g., "UTG")
- F: 83% | C: 0% | R: 17%
- 223 combos
- Color-coded bars showing F/C/R proportions

### Zone 2: Center — Hand Matrix

#### Context Description
Shows current game state context:
- "rfi" (raise first in) — default preflop
- "vs_raise" — after someone raised
- "vs_3bet" — after a 3-bet
- Description string from `treeNode.description`

#### Tree Path Breadcrumb (when tree is active)
Shows the decision path: `UTG → Raise 2.5 → HJ → ...`
- Each step: position name + action label
- Arrow separators
- ✕ button to reset tree

#### 13×13 Hand Matrix
169 buttons in a CSS grid (13 columns × 13 rows).

**Cell rendering:**
- **Always-raise** (freq=1.0, action=raise/bet): solid red
- **Always-fold** (freq=0.0 or action=fold): solid gray
- **Mixed** (0 < freq < 1): CSS gradient — `linear-gradient(to right, RED X%, GRAY X%)`
  where X is the frequency percentage

**Cell content:**
- Hand name (e.g., "AA", "AKs") — 13px font
- Frequency chip (e.g., "50%") on mixed hands — 10px, dark pill background
- Folded hands show no frequency

**Cell states:**
| State | Visual |
|-------|--------|
| Default | Hand name + frequency (if mixed) |
| Selected | White border on selected cell |
| Filtered | actionFilter active → non-matching cells at 0.08 opacity |
| Hover | `brightness(1.3)` filter |

#### Legend (below matrix)
4 colored swatches + label:
- ■ Red = Raise
- ■ Green = Call
- ■ Dark Red = All-in
- ■ Gray = Fold

### Zone 3: Right Panel (320px)

#### Overview Section (always visible)
- **Pot** and **Remaining** values — only shown when game tree is active (`treeNode !== null`)
- Shows pot size in bb and remaining stack in bb

#### Selected Hand Details (when a hand is clicked)
- Hand name (large, bold)
- **Action**: GTO action name (colored)
- **Frequency**: percentage
- **Equity**: percentage (if available)

**TODO — Future additions from reference:**
- Tab bar: Hand (default) | Summary | Filters | Actions | Blockers
- Hand tab: EV comparison, combo counts, suit icons
- Summary tab: Full table of all hands with strategy/range/EV
- Actions tab: Aggregate frequencies with combo counts
- Blockers tab: Card removal analysis

#### Hand Count / Source
Bottom of panel: "169 hands • Source: gto-range-definitions"

## State Machines

### Position Selection State
```
IDLE → POSITION_SELECTED → RANGE_LOADED → (user action) → ...
```
Transitions:
- Click position → `loading=true` → API fetch → `loading=false, rangeData=result`
- Change stack depth → same as clicking position (resets tree)
- Click action filter button → show/hide filter (no API call)

### Game Tree Navigation State
```
RFI → ACTOR_ACTED → NEXT_ACTOR → ... → PREFLOP_COMPLETE → POSTFLOP
```
States:
- `treePath=[]` — RFI (raise first in) mode
- `treePath=[...]` — Tree is active. API returns `tree_node` with acting position + available actions
- Action validation: Only advance tree if at least 1 hand in current range uses that action
- Silent reject (no state change) if zero hands use the action

### Cell Interaction State
```
UNSELECTED → SELECTED → UNSELECTED (toggle)
```
- Click hand → toggle selected hand (only one at a time)
- Selected hand shown in right panel
- Click same hand → deselect

## API Contract

### POST `/api/v1/solver/preflop-range`

**Request:**
```json
{
  "position": "UTG",
  "stack_depth": 100,
  "game_type": "NLH",
  "players": 6,
  "tree_path": [
    {"position": "UTG", "action": "raise_2.5bb"}
  ]
}
```

**Response:**
```json
{
  "position": "UTG",
  "stack_depth": 100,
  "hands": [
    {"hand": "AA", "action": "raise_2.5bb", "frequency": 1.0, "equity": 0.852},
    {"hand": "A5s", "action": "raise_2.5bb", "frequency": 0.4, "equity": 0.62}
  ],
  "tree_node": {
    "acting_position": "HJ",
    "available_actions": [
      {"id": "fold", "actionBase": "fold", "label": "Fold"},
      {"id": "raise_2.5", "actionBase": "raise", "label": "Raise 2.5"},
      {"id": "all_in_100", "actionBase": "all_in", "label": "Allin 100"}
    ],
    "pot_size": 3.5,
    "stack_remaining": 97,
    "context": "vs_raise",
    "description": "HJ faces UTG's raise"
  },
  "source": "gto-range-definitions",
  "combos": 169
}
```

## Architectural Rules (from v1 lessons, baked in from day 1)

1. **Study page has NO quiz mechanics.** No "Check vs GTO", no correct/incorrect feedback, no "Try Again", no quiz stats. These belong on `/practice`.

2. **Mode transitions are automatic.** When preflop round completes (all 6 positions acted), auto-deal flop and switch to postflop view. NO manual mode toggle.

3. **Action validation.** Only advance tree if at least one hand in current range uses the clicked action. Silent reject otherwise.

4. **Action buttons live on position cards (sidebar), NOT inside grid cells.** This is a deliberate deviation from the original GTO Wizard.

5. **Action colors are user-specified:** raise=RED, bet=RED, all_in=DARK RED, call=GREEN, check=GREEN, fold=BLUE/GRAY.

6. **Mixed frequencies** use CSS `linear-gradient` (not separate component).

7. **Position click resets tree.** Changing position or stack depth empties `treePath` and `treeNode`.

## Planned Features (Not Yet Implemented)

| Feature | Source | Priority |
|---------|--------|----------|
| Aggregate flip strip (F/C/R per position) | v1 had it | P1 |
| Postflop mode (auto-transition, board cards) | Reference spec | P1 |
| Right sidebar tab bar (Overview/Table/Equity chart) | Reference | P2 |
| Right sidebar sub-tabs (Hand/Summary/Filters/Actions/Blockers) | Reference | P2 |
| Left tabs (Strategy/Ranges/Breakdown/Reports) | Reference | P2 |
| Game tree branching (non-linear paths) | Reference | P2 |
| Solver status indicator | v1 had it | P3 |
| Combo grid with suit icons | Reference | P3 |
| Export (PNG/CSV) | v1 had it | P3 |

## Open Questions

1. Should aggregate flip strip go in the left sidebar below position cards, or in the center above the matrix?
2. Should postflop be a separate tab/sub-page or an automatic transition within the same page?
3. Right sidebar — should we start with just the Overview section (current) or build the full tab system?
