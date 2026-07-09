"""Trainer API Router — GTO training workflow.

Endpoints:
- POST /api/v1/trainer/question — Generate a training question from scenario + texture
- POST /api/v1/trainer/submit — Submit an action, receive feedback grade
- POST /api/v1/trainer/range-view — Get range action-split matrix for a spot
"""

import json
import logging
import random
import uuid
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from apps.api.services.database import get_session_context

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/trainer", tags=["trainer"])

# ── Scenarios ──────────────────────────────────────────
SCENARIOS = {
    "cbet-btn-vs-bb": {
        "label": "C-betting BTN vs BB",
        "hero_pos": "BTN", "villain_pos": "BB",
        "preflop_action": "BTN raised 2.5bb, BB called",
        "flop": "Ks7d2c",
        "hands": ["AhKh", "KcQc", "AcJc", "QhJh", "TT", "99"],
    },
    "srp-ip": {
        "label": "SRP IP (Single Raised Pot)",
        "hero_pos": "BTN", "villain_pos": "CO",
        "preflop_action": "CO raised 2.5bb, BTN called",
        "flop": "JdTh4c",
        "hands": ["AhJh", "KcTc", "QdJd", "TT", "AcQc"],
    },
    "srp-oop": {
        "label": "SRP OOP (Out of Position)",
        "hero_pos": "BB", "villain_pos": "BTN",
        "preflop_action": "BTN raised 2.5bb, BB called",
        "flop": "8h6d3c",
        "hands": ["Ah8h", "Kd8d", "QcJc", "77", "T9s"],
    },
    "3bet-pot-ip": {
        "label": "3-bet Pot IP",
        "hero_pos": "BTN", "villain_pos": "CO",
        "preflop_action": "CO raised 2.5bb, BTN 3bet 9bb, CO called",
        "flop": "AcTd7s",
        "hands": ["AKs", "AQs", "KK", "QQ", "JJ"],
    },
}

# ── GTO actions for spots (mock — would come from solver) ──
# Format: (hand, flop) -> {action, ev, grade}
GTO_SOLUTIONS: Dict[str, Dict[str, Any]] = {
    "AhKh:Ks7d2c": {"action": "bet_66", "ev": 3.42, "grade": "optimal", "alt_actions": {"check": 2.15}},
    "KcQc:Ks7d2c": {"action": "bet_50", "ev": 2.18, "grade": "optimal", "alt_actions": {"check": 1.85}},
    "AcJc:Ks7d2c": {"action": "check", "ev": 1.55, "grade": "optimal", "alt_actions": {"bet_33": 0.92}},
    "QhJh:Ks7d2c": {"action": "fold", "ev": 0, "grade": "optimal", "alt_actions": {"check": -0.45}},
    "TT:Ks7d2c": {"action": "bet_66", "ev": 4.1, "grade": "optimal", "alt_actions": {"check": 3.2}},
    "99:Ks7d2c": {"action": "check", "ev": 0.85, "grade": "acceptable", "alt_actions": {"bet_33": 0.42}},
}

# ── Request/Response models ───────────────────────────
class QuestionRequest(BaseModel):
    scenario: str = Field("cbet-btn-vs-bb", description="Scenario preset ID")
    texture: str = Field("random", description="Flop texture filter")

class QuestionResponse(BaseModel):
    id: str
    spot_id: str
    scenario: str
    hand: str
    board: str
    street: str
    pot: int
    hero_position: str
    villain_position: str
    description: str

class SubmitRequest(BaseModel):
    question_id: str
    action: str
    street: str = "flop"

class SubmitResponse(BaseModel):
    correct: bool
    grade: str
    explanation: str
    ev: float
    gto_action: str
    gto_ev: float

class RangeViewRequest(BaseModel):
    spot_id: str

class RangeViewResponse(BaseModel):
    hands: List[Dict[str, Any]]


@router.post("/question", response_model=QuestionResponse)
async def generate_question(req: QuestionRequest):
    """Generate a training question based on scenario and texture."""
    scenario = SCENARIOS.get(req.scenario)
    if not scenario:
        # Fallback to a random scenario
        scenario = random.choice(list(SCENARIOS.values()))

    hand = random.choice(scenario["hands"])
    board = scenario["flop"]
    pot = random.choice([6, 7, 8, 10, 12, 15])

    return QuestionResponse(
        id=str(uuid.uuid4()),
        spot_id=f"{req.scenario}:{hand}:{board}",
        scenario=req.scenario,
        hand=hand,
        board=board,
        street="flop",
        pot=pot,
        hero_position=scenario["hero_pos"],
        villain_position=scenario["villain_pos"],
        description=f"{scenario['preflop_action']}. Board: {board}. Hero ({scenario['hero_pos']}) holds {hand}.",
    )


@router.post("/submit", response_model=SubmitResponse)
async def submit_action(req: SubmitRequest):
    """Submit an action and get GTO feedback."""
    # Parse spot info from question_id: scenario:hand:board
    parts = req.question_id.split(":")
    hand = parts[1] if len(parts) > 1 else "AhKh"
    board = parts[2] if len(parts) > 2 else "Ks7d2c"

    # Look up GTO solution
    solution_key = f"{hand}:{board}"
    solution = GTO_SOLUTIONS.get(solution_key)

    if not solution:
        # Fallback: generate reasonable feedback
        default_actions = {
            "bet_66": {"ev": 2.5, "grade": "acceptable"},
            "check": {"ev": 1.2, "grade": "acceptable"},
            "fold": {"ev": 0, "grade": "inaccuracy"},
        }
        solution = default_actions.get(req.action, {"ev": 0.5, "grade": "inaccuracy"})

        return SubmitResponse(
            correct=req.action in ("bet_66", "check"),
            grade=solution["grade"],
            explanation="In this spot, consider the board texture and your hand strength relative to villain's range.",
            ev=solution["ev"],
            gto_action="bet_66",
            gto_ev=2.5,
        )

    gto_action = solution["action"]
    user_action = req.action

    # Determine grade
    if user_action == gto_action:
        grade = "optimal"
        correct = True
        ev = solution["ev"]
        explanation = f"Perfect! {gto_action} is the highest EV play ({solution['ev']:.2f})."
    elif user_action in solution.get("alt_actions", {}):
        grade = "acceptable"
        correct = True
        ev = solution["alt_actions"][user_action]
        explanation = f"{user_action} is acceptable ({ev:.2f} EV), but {gto_action} ({solution['ev']:.2f}) is higher EV."
    elif user_action == "fold":
        grade = "blunder"
        correct = False
        ev = 0
        explanation = f"Folding here loses the pot. Consider {gto_action} ({solution['ev']:.2f} EV)."
    else:
        grade = "inaccuracy"
        correct = False
        ev = -0.5
        explanation = f"{user_action} is suboptimal here. Try {gto_action} ({solution['ev']:.2f} EV)."

    return SubmitResponse(
        correct=correct,
        grade=grade,
        explanation=explanation,
        ev=ev,
        gto_action=gto_action,
        gto_ev=solution["ev"],
    )


@router.post("/range-view", response_model=RangeViewResponse)
async def get_range_view(req: RangeViewRequest):
    """Get the full range action-split matrix for a spot."""
    # Generate a simulated range view based on common GTO tendencies
    ranks = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]
    hands = []
    for i, r1 in enumerate(ranks):
        for j, r2 in enumerate(ranks):
            if i == j:
                hand = r1 + r2
                # Pairs: higher = bet, lower = check/fold
                if i <= 4: action = "bet_66"
                elif i <= 7: action = "check"
                else: action = "fold"
            elif i < j:
                hand = r1 + r2 + "s"
                # Suited broadways = bet, suited connectors = call/check
                if i <= 2: action = "bet_50"
                elif r1 == r2: action = "check"
                else: action = "fold" if i > 6 else "check"
            else:
                hand = r2 + r1 + "o"
                # Offsuit: mostly fold preflop, some calls
                if i <= 1 and j <= 2: action = "bet_50"
                elif i <= 3: action = "check"
                else: action = "fold"

            hands.append({"hand": hand, "action": action, "frequency": random.uniform(0.3, 1.0)})

    return RangeViewResponse(hands=hands)
