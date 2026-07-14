# ════════════════════════════════════════════════════════════
#  EXPORT SYSTEM — Pio CSV / GTO+ TXT / GTO Wizard JSON
# ════════════════════════════════════════════════════════════

import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/export", tags=["export"])

# ── Constants ──

RANK_ORDER = "AKQJT98765432"
ACTIONS = ["fold", "call", "raise", "all_in", "check", "bet"]


def spot_hash(position: str, stack: float, board: str, tree_path: list[str]) -> str:
    """Stable hash identifying a unique spot (position+stack+board+actions)."""
    key = f"{position}|{stack}|{board}|{'→'.join(tree_path)}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def build_169_hands() -> list[str]:
    """Generate all 169 hand combos (AA, AKs, AKo, ..., 32s, 22)."""
    hands = []
    for i, r1 in enumerate(RANK_ORDER):
        for j, r2 in enumerate(RANK_ORDER):
            if i < j:  # strict, ordered pairs first
                hands.append(f"{r1}{r2}s")
            elif i == j:
                hands.append(f"{r1}{r2}")
    # Add offsuit versions for non-pairs
    full = []
    for i, r1 in enumerate(RANK_ORDER):
        for j, r2 in enumerate(RANK_ORDER):
            if i == j:
                full.append(f"{r1}{r2}")
            elif i < j:
                full.append(f"{r1}{r2}s")
                full.append(f"{r1}{r2}o")
    return full


# ── PioSOLVER CSV ──

@router.post("/pio")
async def export_pio(request: dict):
    """Export strategy in PioSOLVER-compatible CSV format.
    
    Format: rows of [Hand, Action, Frequency, TreeAction]
    One section per spot with '#' comments for metadata.
    """
    position = request.get("position", "BTN")
    stack = request.get("stack_depth", 100)
    board = request.get("board", "")
    tree_path = request.get("tree_path", [])
    actions_data = request.get("actions", [])
    
    buf = io.StringIO()
    buf.write(f"# GTO Wizard Export — PioSOLVER CSV\n")
    buf.write(f"# Generated: {datetime.now(timezone.utc).isoformat()}\n")
    buf.write(f"# Position: {position} | Stack: {stack}bb | Board: {board or 'preflop'}\n")
    buf.write(f"# Action tree: {' → '.join(tree_path) if tree_path else 'RFI'}\n")
    buf.write(f"#\n")
    buf.write("Hand,Action,Frequency,TreeAction\n")
    
    for act in actions_data:
        hand = act.get("hand", "")
        action = act.get("action", "fold")
        freq = act.get("frequency", 0)
        buf.write(f"{hand},{action},{freq:.4f},{'→'.join(tree_path)}\n")
    
    buf.write(f"#\n")
    buf.write(f"# SPOT_ID: {spot_hash(position, stack, board, tree_path)}\n")
    
    return {"content": buf.getvalue(), "filename": f"spot_{position}_{board or 'preflop'}.csv", "mime": "text/csv"}


# ── GTO+ / Power-Equilab TXT ──

@router.post("/gto-plus")
async def export_gto_plus(request: dict):
    """Export strategy in GTO+ / Power-Equilab compatible TXT format.
    
    Format: section headers per action, {weight: hand} lines.
    """
    position = request.get("position", "BTN")
    stack = request.get("stack_depth", 100)
    board = request.get("board", "")
    tree_path = request.get("tree_path", [])
    actions_data = request.get("actions", [])
    
    buf = io.StringIO()
    buf.write(f"### GTO Wizard Export — GTO+/Power-Equilab\n")
    buf.write(f"### Position: {position} | Stack: {stack}bb | Board: {board or 'preflop'}\n")
    buf.write(f"### Action: {' → '.join(tree_path) if tree_path else 'RFI'}\n")
    buf.write(f"### Generated: {datetime.now(timezone.utc).isoformat()}\n\n")
    
    # Group by action
    by_action: dict[str, list[dict]] = {}
    for act in actions_data:
        action = act.get("action", "fold")
        if action not in by_action:
            by_action[action] = []
        by_action[action].append(act)
    
    for action in ACTIONS:
        if action in by_action:
            items = by_action[action]
            total_freq = sum(a.get("frequency", 0) for a in items)
            buf.write(f"### {action.upper()} | avg freq: {total_freq:.2f}\n")
            for item in items:
                hand = item.get("hand", "")
                freq = item.get("frequency", 0)
                buf.write(f"{{{freq:.4f}: {hand}}}\n")
            buf.write("\n")
    
    return {"content": buf.getvalue(), "filename": f"spot_{position}_{board or 'preflop'}.txt", "mime": "text/plain"}


# ── GTO Wizard JSON (round-trip) ──

@router.post("/json")
async def export_json(request: dict):
    """Full GTO Wizard round-trip export with annotations."""
    position = request.get("position", "BTN")
    stack = request.get("stack_depth", 100)
    board = request.get("board", "")
    tree_path = request.get("tree_path", [])
    actions_data = request.get("actions", [])
    annotations = request.get("annotations", [])
    
    export = {
        "format": "gto-wizard-spot-v1",
        "version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "spot": {
            "id": spot_hash(position, stack, board, tree_path),
            "position": position,
            "stack_depth": stack,
            "board": board,
            "action_tree": tree_path,
            "street": "preflop" if len(board) < 3 else "flop" if len(board) < 4 else "turn" if len(board) < 5 else "river",
        },
        "strategy": {
            "actions": actions_data,
            "total_hands": len(actions_data),
            "source": request.get("source", "live-solver"),
        },
        "annotations": annotations,
        "metadata": {
            "locks": request.get("locked_hands", {}),
            "tree_path": tree_path,
        },
    }
    
    return {"content": json.dumps(export, indent=2), "filename": f"spot_{position}_{board or 'preflop'}.json", "mime": "application/json"}


# ── Multiple spots bundle ──

@router.post("/multiple")
async def export_multiple(request: dict):
    """Export multiple spots in one file."""
    spots = request.get("spots", [])
    fmt = request.get("format", "json")
    
    combined = []
    for spot in spots:
        if fmt == "json":
            r = await export_json(spot)
        elif fmt == "pio":
            r = await export_pio(spot)
        elif fmt == "gto-plus":
            r = await export_gto_plus(spot)
        else:
            raise HTTPException(400, f"Unknown format: {fmt}")
        combined.append({"spot": spot, "export": r})
    
    bundle = {
        "format": "gto-wizard-bundle-v1",
        "version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "spots": combined,
        "count": len(combined),
    }
    
    return {"content": json.dumps(bundle, indent=2), "filename": "gto-wizard-bundle.json", "mime": "application/json"}
