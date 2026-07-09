# GTO Wizard Study Interface — Interaction Spec (Corrected)

> Captured from `app.gtowizard.com/study` via Tandem Browser CDP.
> Two distinct zones: Spot Cards (top) and Hand Matrix (below).

## Zone 1: Spot Card Bar (Top, Horizontal)

Six position cards in a scrollable row above the matrix. Each card shows the position's current action state at a glance — no clicking needed.

### Card structure (DOM)
```
div.hspotcrd_inner
  div.hspotcrd_title           → "HJ" or "UTG" or "SB"
  div.hspotcrd_actions
    div.hspotcrd_action_prompt  → "Take action" (only on acting position)
    div.hspotcrd_action         → "Fold" (hspotcrd_action_active if GTO)
    div.hspotcrd_action         → "Call" (SB/BB only)
    div.hspotcrd_action         → "Raise 3.5" (SB/BB) or "Raise 2.5" (others)
    div.hspotcrd_action         → "Allin 100"
```

### Card states
| State | Class | What shows |
|-------|-------|------------|
| **Active** (acting position) | `hspotcrd_active` | Card expanded. Shows "Take action" prompt + all action buttons. GTO recommendation highlighted. |
| **Minimized** (acted/not acting) | `hspotcrd_minimized` | Shows position name + stack. Action buttons still visible but no "Take action". |

### Per-position action sets
| Position | Actions Available |
|----------|-------------------|
| **UTG** (active/minimized) | Fold←, Raise 2.5, Allin 100 |
| **HJ** (ACTIVE) | [Take action] Fold, Raise 2.5, Allin 100 |
| **CO** (minimized) | [Take action] Fold, Raise 2.5, Allin 100 |
| **BTN** (minimized) | [Take action] Fold, Raise 2.5, Allin 100 |
| **SB** (minimized) | [Take action] Fold, **Call**, **Raise 3.5**, Allin 100 |
| **BB** (minimized) | [Take action] Fold, **Call**, **Raise 3.5**, Allin 100 |

Key: Call only appears for SB/BB. Raise sizing differs (2.5 vs 3.5).

### Scrollable container
```
div.hspotscont_inner_scrollable.hscroller_inner  → horizontal scroll
```

## Zone 2: Hand Matrix (Below Spot Cards)

### 169-cell grid (13×13)
```
grid "Hand matrix"
  row "AA, raise_2.5bb 100 percent AKs, raise_2.5bb 87 percent..."
    gridcell "AA, raise_2.5bb 100 percent" [selected]
      button "Fold"
      button "Raise 2.5, GTO recommendation"
      button "Allin 100"
    gridcell "AKs, raise_2.5bb 87 percent"
    gridcell "A6s, fold 100 percent"
```

- Cell size: 35×36px, dark bg `rgb(30, 30, 30)`
- Hand name (e.g., "AA") in `.rtc_title`
- Frequency overlay when not selected (e.g., "87%", "100%")
- Inline action buttons appear **inside the cell** when selected
- GTO action highlighted as "Raise 2.5, GTO recommendation"

### Cell states
| State | Visual |
|-------|--------|
| Default (unselected) | Hand name + action frequency (e.g., "AKs 87%") |
| Selected | Inline action buttons replace frequency |
| Folded (0% range) | Hand name only, no frequency — e.g., "A6s" with no percentage |

### Action frequency display (per cell)
Format: `{hand}, {action} {percent} percent` → e.g., "AA, raise_2.5bb 100 percent"

## Right Sidebar

### Top tabs: Overview | Table | Equity chart
- **Overview**: Position info (stacks, dead money, pot odds 40%)
- **Table**: Position table with EV ("HJ OOP EV 0.1 Combos 1326")
- **Equity chart**: Equity distribution graph

### Sub-tabs: Hand | Summary | Filters | Actions | Actions chart | Range compare | Blockers | Equity chart | Compare EV
- **Actions** (default): Aggregate frequencies: "Allin 100 0% (0 combos)", "Raise 2.5 21.7% (287.11 combos)", "Fold 78.3% (1038.88 combos)"
- **Hand**: Per-hand EV/equity
- **Summary**: Table of all hands with strategy/range/EV
- **Blockers**: Card removal analysis

## Left Tabs: Strategy | Ranges | Breakdown | Reports: Flops

- **Strategy**: Hand matrix with inline action buttons
- **Ranges**: Hand matrix with different header
- **Breakdown**: Category analysis (postflop only)
- **Reports: Flops**: Dropdown menu for postflop reports

## Layout Summary

```
┌─────────────────────────────────────────────────────┐
│ Top Bar (Cash | 100bb | 2/100 | Upgrade)            │
├─────────────────────────────────────────────────────┤
│ SPOT CARDS (horizontal scroll)                      │
│ [UTG 100] [HJ 100 ACTIVE] [CO 100] [BTN 100] [SB] │
│  Fold←      Take action   Take act   Take act  Take │
│  Raise 2.5  Fold          Fold        Fold      Call│
│  Allin 100  Raise 2.5     Raise 2.5   Raise 2.5  R3│
│             Allin 100     Allin 100   Allin 100  AI │
├──────────────────────┬──────────────────────────────┤
│ Left (460px)         │ Right Sidebar (330px)        │
│ ┌──────────────────┐ │ ┌────────────────────────┐  │
│ │ Str▾|Rng|Brk|Rep │ │ │ Overview|Table|Eq chart│  │
│ ├──────────────────┤ │ ├────────────────────────┤  │
│ │   HAND MATRIX    │ │ │ HJ 1000, CO 1000...    │  │
│ │   13×13 grid     │ │ │ Dead: 1.5+1.5 BB       │  │
│ │                  │ │ │ Pot odds: 40%          │  │
│ │ AA [F][R2.5][AI] │ │ ├────────────────────────┤  │
│ │ AKs 87%          │ │ │ Hand|Summary|Filt|Act… │  │
│ │ A6s (fold)       │ │ │ "Fold 78.3% (1038.8c)"│  │
│ └──────────────────┘ │ └────────────────────────┘  │
├──────────────────────┴──────────────────────────────┤
│ Legend: Allin 0% | Raise 2.5 100% | Fold 0%        │
└─────────────────────────────────────────────────────┘
```

## Interaction Flow

1. **Page loads** → HJ is active (acting position). UTG minimized (already acted).
2. **Click different position** → that position becomes active. Matrix updates to its range.
3. **Click a hand cell** → inline action buttons appear. Right sidebar updates with hand data.
4. **Switch left tab** → Strategy (matrix with actions) / Ranges / Breakdown / Reports
5. **Switch right tab** → Overview / Table / Equity chart
6. **Switch sub-tab** → Hand / Summary / Filters / Actions (with combo counts) / Blockers...

## Key CSS Classes

| Element | Class |
|---------|-------|
| Spot card container | `hspotcrd_inner` |
| Spot card | `hspot-card hspotcrd gw_hvr` |
| Active card | `hspotcrd_active` |
| Minimized card | `hspotcrd_minimized` |
| Action button | `hspotcrd_action` |
| Active action | `hspotcrd_action_active` |
| Action prompt | `hspotcrd_action_prompt` |
| Position name | `hspotcrd_title` |
| Scrollable container | `hspotscont_inner_scrollable hscroller_inner` |
| Matrix cell | `ra_table_cell` |
| Matrix cell title | `rtc_title` |
| Right sidebar | `laytsttd_aside` / `study-ranges-aside sttranasd std_cont_tabs` |
| Left panel | `gw_tbbox tabboxstudy flex-1` |
| Tab | `gtabs_tab gw_hvr` |
| Active tab | `gtabs_tab gw_hvr gtabs_tab_active` |
| Legend | `htc_graph_legend` |
| Legend item | `htc_graph_legend_item_bet` |
| Drawing mode | `canvas-paint_controls` / `gw_message no-events` |
