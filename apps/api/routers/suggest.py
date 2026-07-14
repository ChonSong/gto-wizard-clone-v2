# ════════════════════════════════════════════════════════════
#  LLM ANNOTATION SUGGESTER
# ════════════════════════════════════════════════════════════
#
# Pipeline:
#   1. Load reference data (Kaggle poker hands, Pio/GTO+ exports)
#   2. Classify board texture (wet/dry/sticky/monotone)
#   3. Classify hand category (overpair, flush draw, etc.)
#   4. Match current spot against reference DB
#   5. LLM generates suggestion based on matched patterns
#
# Reference formats supported:
#   - Kaggle poker-hands-dataset (CSV with hand + board)
#   - PioSOLVER aggregated CSV export
#   - GTO+ / Power-Equilab weighted export
#   - GTO Wizard JSON export (round-trip)
#
# Board texture classification (from pio-hand-classifier logic):
#   - dry: no flush draw, no straight draw, unpaired
#   - wet: flush draw possible, or 3-straight on board
#   - sticky: paired board, or 2-flush on board
#   - monotone: 3+ same suit
#   - 3-straight: 3 connected cards
#   - paired: board has a pair
# ════════════════════════════════════════════════════════════

import csv
import hashlib
import io
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/suggest", tags=["suggest"])

# ── Constants ──

RANK_ORDER = "AKQJT98765432"
RANK_VALUES = {r: i for i, r in enumerate(RANK_ORDER)}  # A=0, K=1, ... 2=12
SUITS = "hdcs"

# Hand categories (from pio-hand-classifier)
HAND_CATEGORIES = [
    "overpair", "top_pair", "middle_pair", "bottom_pair", "underpair",
    "overcards", "top_kicker", "middle_kicker", "weak_kicker",
    "flush_draw", "open_ender", "gutshot", "straight_draw",
    "made_flush", "made_straight", "full_house", "quads",
    "air", "set", "two_pair", "top_two", "trips",
]

# Board textures
BOARD_TEXTURES = [
    "dry", "wet", "sticky", "monotone",
    "3-straight", "paired", "2-flush", "3-flush",
    "rainbow", "paired_dry", "paired_wet",
]


# ── Data Classes ──

@dataclass
class ClassifiedHand:
    hand: str
    board: str
    hand_category: str
    board_texture: str
    equity_bucket: str  # "high", "medium", "low"
    action: str = "fold"
    frequency: float = 0.0


@dataclass
class ReferenceEntry:
    """A single reference data point from any source."""
    hand: str
    board: str
    action: str
    frequency: float
    source: str  # "kaggle", "pio", "gto_plus", "gto_wizard"
    hand_category: str = ""
    board_texture: str = ""
    metadata: dict = field(default_factory=dict)


# ── Board Texture Classifier ──

def classify_board_texture(board: str) -> list[str]:
    """Classify board texture from card string (e.g. 'KsKc3s')."""
    if not board or len(board) < 6:
        return ["preflop"]
    
    cards = [(board[i], board[i+1]) for i in range(0, len(board), 2)]
    ranks = [c[0] for c in cards]
    suits = [c[1] for c in cards]
    
    textures = []
    
    # Count suits
    suit_counts = {}
    for s in suits:
        suit_counts[s] = suit_counts.get(s, 0) + 1
    
    max_suit_count = max(suit_counts.values()) if suit_counts else 0
    
    if max_suit_count >= 3:
        textures.append("monotone")
    elif max_suit_count == 2:
        textures.append("2-flush")
    else:
        textures.append("rainbow")
    
    # Check for paired board
    rank_counts = {}
    for r in ranks:
        rank_counts[r] = rank_counts.get(r, 0) + 1
    
    if max(rank_counts.values()) >= 2:
        textures.append("paired")
    
    # Check for 3-straight
    rank_vals = sorted([RANK_VALUES.get(r, 99) for r in ranks])
    if len(rank_vals) >= 3:
        for i in range(len(rank_vals) - 2):
            if rank_vals[i+2] - rank_vals[i] <= 4 and rank_vals[i+1] - rank_vals[i] <= 2:
                textures.append("3-straight")
                break
    
    # Wet/dry assessment
    if "3-straight" in textures or max_suit_count >= 2:
        textures.append("wet")
    elif max_suit_count == 1 and "3-straight" not in textures:
        textures.append("dry")
    else:
        textures.append("sticky")
    
    return textures


def _parse_hand(hand: str) -> tuple:
    """Parse hand string. Supports 3-char ('AKs', '72o') and 4-char ('AhKh') formats.
    
    Returns ((rank1, rank2), (suit1, suit2)).
    """
    if len(hand) >= 4 and hand[2] in SUITS:
        return (hand[0], hand[2]), (hand[1], hand[3])
    elif len(hand) >= 3 and hand[2] in "so":
        return (hand[0], hand[1]), (hand[2], hand[2])
    elif len(hand) == 2:
        return (hand[0], hand[1]), ("h", "d")
    return (hand[0], hand[1]), ("h", "h")


def classify_hand_category(hand: str, board: str) -> str:
    """Classify hand strength relative to board."""
    if not hand or not board or len(board) < 6:
        return "air"
    
    (hand_rank1, hand_rank2), (suit1, suit2) = _parse_hand(hand)
    board_cards = [(board[i], board[i+1]) for i in range(0, len(board), 2)]
    board_ranks = [c[0] for c in board_cards]
    board_suits = [c[1] for c in board_cards]
    
    # Check for flush
    hand_suits = (hand[2], hand[3]) if len(hand) >= 4 else (hand[1], hand[1])
    suit_counts = {}
    for s in board_suits:
        suit_counts[s] = suit_counts.get(s, 0) + 1
    for s in (suit1, suit2):
        suit_counts[s] = suit_counts.get(s, 0) + 1
    
    if max(suit_counts.values()) >= 5:
        return "made_flush"
    
    # Check for pairs/sets
    rank_counts = {}
    for r in board_ranks:
        rank_counts[r] = rank_counts.get(r, 0) + 1
    
    for r in (hand_rank1, hand_rank2):
        if r in rank_counts:
            if rank_counts[r] == 2:  # board has pair + hand matches = trips
                return "trips"
            elif rank_counts[r] == 1:
                # Check if it's top pair, etc.
                board_rank_vals = sorted([RANK_VALUES.get(br, 99) for br in board_ranks])
                hand_val = RANK_VALUES.get(r, 99)
                if hand_val <= board_rank_vals[0]:
                    return "top_pair"
                elif hand_val <= board_rank_vals[len(board_rank_vals)//2]:
                    return "middle_pair"
                else:
                    return "bottom_pair"
    
    # Check for overpair
    hand_val = min(RANK_VALUES.get(hand_rank1, 99), RANK_VALUES.get(hand_rank2, 99))
    board_max = min([RANK_VALUES.get(br, 99) for br in board_ranks])
    if hand_val < board_max:
        return "overpair"
    
    # Check for flush draw
    for s in (suit1, suit2):
        if suit_counts.get(s, 0) >= 4:
            return "flush_draw"
    
    # Check for straight draw
    all_ranks = board_ranks + [hand_rank1, hand_rank2]
    all_vals = sorted(set([RANK_VALUES.get(r, 99) for r in all_ranks]))
    if len(all_vals) >= 4:
        for i in range(len(all_vals) - 3):
            if all_vals[i+3] - all_vals[i] <= 4:
                return "open_ender"
    
    # Overcards
    if hand_val < board_max:
        return "overcards"
    
    return "air"


# ── Reference DB Loader ──

class ReferenceDB:
    """In-memory reference database loaded from multiple sources."""
    
    def __init__(self):
        self.entries: list[ReferenceEntry] = []
        self._by_texture: dict[str, list[ReferenceEntry]] = {}
        self._by_category: dict[str, list[ReferenceEntry]] = {}
        self._loaded = False
    
    def load_kaggle_csv(self, csv_content: str):
        """Load Kaggle poker-hands-dataset CSV format."""
        reader = csv.DictReader(io.StringIO(csv_content))
        for row in reader:
            # Kaggle format: S1,C1,S2,C2,...,S5,C5,Hand
            # S=suit, C=rank for each of 5 community cards + 2 hole cards
            try:
                board_cards = []
                for i in range(1, 4):  # first 3 = flop
                    suit = row.get(f"S{i}", "")
                    rank = row.get(f"C{i}", "")
                    if suit and rank:
                        board_cards.append(f"{rank}{suit}")
                
                hand_cards = []
                for i in range(4, 6):  # last 2 = hole cards
                    suit = row.get(f"S{i}", "")
                    rank = row.get(f"C{i}", "")
                    if suit and rank:
                        hand_cards.append(f"{rank}{suit}")
                
                if len(hand_cards) == 2 and len(board_cards) == 3:
                    hand = hand_cards[0][0] + hand_cards[1][0]
                    if hand_cards[0][1] == hand_cards[1][1]:
                        hand += "s" if hand_cards[0][0] < hand_cards[1][0] else "o"
                    board = "".join(board_cards)
                    
                    textures = classify_board_texture(board)
                    category = classify_hand_category(hand, board)
                    
                    entry = ReferenceEntry(
                        hand=hand,
                        board=board,
                        action="unknown",
                        frequency=0.5,
                        source="kaggle",
                        hand_category=category,
                        board_texture=textures[0] if textures else "unknown",
                    )
                    self.entries.append(entry)
            except Exception as e:
                logger.debug(f"Skipping Kaggle row: {e}")
    
    def load_pio_csv(self, csv_content: str):
        """Load PioSOLVER aggregated CSV export."""
        reader = csv.DictReader(io.StringIO(csv_content))
        for row in reader:
            try:
                hand = row.get("Hand", "")
                action = row.get("Action", "fold")
                freq = float(row.get("Frequency", 0))
                tree_action = row.get("TreeAction", "")
                
                if hand and freq > 0:
                    entry = ReferenceEntry(
                        hand=hand,
                        board="",  # Pio CSV doesn't always include board
                        action=action.lower(),
                        frequency=freq,
                        source="pio",
                        metadata={"tree_action": tree_action},
                    )
                    self.entries.append(entry)
            except Exception as e:
                logger.debug(f"Skipping Pio row: {e}")
    
    def load_gto_plus_txt(self, txt_content: str):
        """Load GTO+ / Power-Equilab weighted export."""
        current_action = None
        for line in txt_content.split("\n"):
            line = line.strip()
            if line.startswith("### "):
                # Section header like "### RAISE | avg freq: 0.30"
                match = re.match(r"###\s+(\w+)", line)
                if match:
                    current_action = match.group(1).lower()
            elif line.startswith("{") and ":" in line:
                # Weighted combo: {0.5: AA}
                match = re.match(r"\{([\d.]+):\s*(\w+)\}", line)
                if match and current_action:
                    freq = float(match.group(1))
                    hand = match.group(2)
                    entry = ReferenceEntry(
                        hand=hand,
                        board="",
                        action=current_action,
                        frequency=freq,
                        source="gto_plus",
                    )
                    self.entries.append(entry)
    
    def load_gto_wizard_json(self, json_content: str):
        """Load GTO Wizard JSON export."""
        try:
            data = json.loads(json_content)
            spot = data.get("spot", {})
            board = spot.get("board", "")
            for act in data.get("strategy", {}).get("actions", []):
                hand = act.get("hand", "")
                action = act.get("action", "fold")
                freq = act.get("frequency", 0)
                if hand:
                    textures = classify_board_texture(board)
                    category = classify_hand_category(hand, board)
                    entry = ReferenceEntry(
                        hand=hand,
                        board=board,
                        action=action,
                        frequency=freq,
                        source="gto_wizard",
                        hand_category=category,
                        board_texture=textures[0] if textures else "unknown",
                    )
                    self.entries.append(entry)
        except Exception as e:
            logger.warning(f"Failed to load GTO Wizard JSON: {e}")
    
    def index(self):
        """Build lookup indexes."""
        self._by_texture.clear()
        self._by_category.clear()
        for entry in self.entries:
            tex = entry.board_texture
            if tex not in self._by_texture:
                self._by_texture[tex] = []
            self._by_texture[tex].append(entry)
            
            cat = entry.hand_category
            if cat not in self._by_category:
                self._by_category[cat] = []
            self._by_category[cat].append(entry)
        self._loaded = True
    
    def find_similar(self, board_texture: str, hand_category: str, limit: int = 10) -> list[ReferenceEntry]:
        """Find reference entries matching texture + category."""
        results = []
        if board_texture in self._by_texture:
            results.extend(self._by_texture[board_texture])
        if hand_category in self._by_category:
            results.extend(self._by_category[hand_category])
        # Deduplicate
        seen = set()
        unique = []
        for r in results:
            key = (r.hand, r.board, r.action)
            if key not in seen:
                seen.add(key)
                unique.append(r)
        return unique[:limit]
    
    def stats(self) -> dict:
        return {
            "total_entries": len(self.entries),
            "by_source": {src: sum(1 for e in self.entries if e.source == src) for src in set(e.source for e in self.entries)},
            "by_texture": {t: len(v) for t, v in self._by_texture.items()},
            "by_category": {c: len(v) for c, v in self._by_category.items()},
        }


# Global reference DB instance
ref_db = ReferenceDB()


# ── LLM Suggester ──

def generate_suggestion_llm(
    hand: str,
    board: str,
    position: str,
    stack: float,
    action: str,
    frequency: float,
    board_texture: str,
    hand_category: str,
    similar: list[ReferenceEntry],
) -> str:
    """Generate annotation suggestion using LLM or rule-based fallback."""
    
    # Build context for the LLM
    context = f"""Poker spot context:
- Hand: {hand}
- Board: {board or 'preflop'}
- Position: {position}
- Stack: {stack}bb
- Current action: {action} ({frequency*100:.0f}% frequency)
- Board texture: {board_texture}
- Hand category: {hand_category}
"""
    
    if similar:
        context += f"\nSimilar reference hands ({len(similar)} found):\n"
        for ref in similar[:5]:
            context += f"  - {ref.hand} on {ref.board or 'preflop'}: {ref.action} ({ref.frequency*100:.0f}%) [{ref.source}]\n"
    
    # Try LLM if available
    llm_response = _try_llm(context)
    if llm_response:
        return llm_response
    
    # Rule-based fallback
    return _rule_based_suggestion(hand, board, action, frequency, board_texture, hand_category)


def _try_llm(context: str) -> Optional[str]:
    """Try calling an LLM for annotation suggestion."""
    # Check for configured LLM
    llm_url = os.environ.get("LLM_URL", "")
    llm_key = os.environ.get("LLM_API_KEY", "")
    llm_model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    
    if not llm_url:
        return None
    
    try:
        import httpx
        
        prompt = f"""You are a GTO poker coach. Given this spot, write a concise 1-2 sentence annotation explaining the strategic rationale. Focus on WHY the action is correct, not just what to do. Be specific about board texture and hand strength.

{context}

Annotation:"""
        
        # Try OpenAI-compatible API
        response = httpx.post(
            f"{llm_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {llm_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": llm_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 150,
                "temperature": 0.7,
            },
            timeout=10.0,
        )
        
        if response.status_code == 200:
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.debug(f"LLM call failed: {e}")
    
    return None


def _rule_based_suggestion(
    hand: str, board: str, action: str, frequency: float,
    board_texture: str, hand_category: str,
) -> str:
    """Generate suggestion using heuristics when LLM is unavailable."""
    
    parts = []
    
    # Board texture context
    if board_texture == "dry":
        parts.append(f"On this dry {board or 'preflop'} board")
    elif board_texture == "wet":
        parts.append(f"On this wet {board or 'preflop'} board")
    elif board_texture == "monotone":
        parts.append(f"On this monotone {board or 'preflop'} board")
    elif board_texture == "paired":
        parts.append(f"On this paired {board or 'preflop'} board")
    else:
        parts.append(f"On {board or 'preflop'}")
    
    # Hand category
    if hand_category == "overpair":
        parts.append(f"{hand} is an overpair")
    elif hand_category in ("top_pair", "middle_pair", "bottom_pair"):
        parts.append(f"{hand} has {hand_category.replace('_', ' ')}")
    elif hand_category == "flush_draw":
        parts.append(f"{hand} has a flush draw")
    elif hand_category == "open_ender":
        parts.append(f"{hand} has an open-ended straight draw")
    elif hand_category == "set":
        parts.append(f"{hand} has a set")
    elif hand_category == "air":
        parts.append(f"{hand} is weak air")
    else:
        parts.append(f"{hand} is {hand_category.replace('_', ' ')}")
    
    # Action rationale
    if action == "fold" and frequency > 0.7:
        parts.append("— clear fold, not enough equity to continue")
    elif action == "fold":
        parts.append("— marginal fold, could mix at low frequency")
    elif action == "call" and frequency > 0.7:
        parts.append("— strong call, realize equity well")
    elif action == "call":
        parts.append("— mixing call to protect range")
    elif action in ("raise", "bet") and frequency > 0.7:
        parts.append("— aggressive play for value/denial")
    elif action in ("raise", "bet"):
        parts.append("— mixing bet to balance range")
    elif action == "all_in":
        parts.append("— all-in is high-EV here")
    elif action == "check":
        parts.append("— check to control pot or induce")
    
    return " ".join(parts) + "."


# ── API Endpoints ──

class SuggestRequest(BaseModel):
    hand: str
    board: str = ""
    position: str = "BTN"
    stack_depth: float = 100
    action: str = "fold"
    frequency: float = 0.0
    tree_path: list[str] = []


class LoadReferenceRequest(BaseModel):
    format: str  # "kaggle", "pio", "gto_plus", "gto_wizard"
    content: str


@router.post("/annotation")
async def suggest_annotation(req: SuggestRequest):
    """Generate annotation suggestion for a hand+spot."""
    textures = classify_board_texture(req.board)
    category = classify_hand_category(req.hand, req.board)
    
    similar = []
    if ref_db._loaded:
        similar = ref_db.find_similar(textures[0] if textures else "", category)
    
    suggestion = generate_suggestion_llm(
        hand=req.hand,
        board=req.board,
        position=req.position,
        stack=req.stack_depth,
        action=req.action,
        frequency=req.frequency,
        board_texture=textures[0] if textures else "unknown",
        hand_category=category,
        similar=similar,
    )
    
    return {
        "suggestion": suggestion,
        "hand_category": category,
        "board_texture": textures,
        "reference_matches": len(similar),
    }


@router.post("/load-reference")
async def load_reference(req: LoadReferenceRequest):
    """Load reference data from external source."""
    if req.format == "kaggle":
        ref_db.load_kaggle_csv(req.content)
    elif req.format == "pio":
        ref_db.load_pio_csv(req.content)
    elif req.format == "gto_plus":
        ref_db.load_gto_plus_txt(req.content)
    elif req.format == "gto_wizard":
        ref_db.load_gto_wizard_json(req.content)
    else:
        raise HTTPException(400, f"Unknown format: {req.format}")
    
    ref_db.index()
    return {"status": "loaded", "stats": ref_db.stats()}


@router.get("/reference-stats")
async def reference_stats():
    """Get reference DB statistics."""
    if not ref_db._loaded:
        return {"status": "empty", "message": "No reference data loaded"}
    return {"status": "loaded", "stats": ref_db.stats()}


@router.post("/classify")
async def classify(req: SuggestRequest):
    """Classify board texture and hand category."""
    textures = classify_board_texture(req.board)
    category = classify_hand_category(req.hand, req.board)
    return {"board_texture": textures, "hand_category": category}
