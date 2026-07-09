"""
Hand History API Router

Provides endpoints for:
- Batch import of hand histories
- Search/filter hands by various criteria
- Leak analysis
- CSV export
- Spot categorization and board texture classification
"""

import csv
import io
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.models.hh_models import (
    BoardTexture,
    HandAction,
    HandHistory,
    HandTag,
    SiteEnum,
    SpotCategory,
    classify_board_texture,
    categorize_spot,
)
from apps.api.services.database import get_db_session

router = APIRouter(prefix="/api/v1/hh", tags=["hand_history"])

# Maximum hands to process in batch
MAX_BATCH_SIZE = 1000


# ----------------------------------------------------------------------
# Pydantic Schemas
# ----------------------------------------------------------------------


class StakesSchema(BaseModel):
    """Stakes information."""

    sb: float
    bb: float


class WinnerSchema(BaseModel):
    """Winner information."""

    player: str
    amount: float


class PlayerSchema(BaseModel):
    """Player at the table."""

    name: str
    seat: int
    stack: float
    position: Optional[str] = None
    hole_cards: Optional[List[str]] = None


class ParsedDataSchema(BaseModel):
    """Parsed hand data structure."""

    game_type: Optional[str] = None
    limit_type: Optional[str] = None
    stakes: Optional[StakesSchema] = None
    table_name: Optional[str] = None
    max_seats: Optional[int] = None
    button_position: Optional[int] = None
    players: Optional[List[PlayerSchema]] = None
    actions: Optional[dict] = None
    board: Optional[List[str]] = None
    pot: Optional[float] = None
    winners: Optional[List[WinnerSchema]] = None
    hero_name: Optional[str] = None


class HandHistoryBase(BaseModel):
    """Base hand history schema."""

    hero_name: Optional[str] = None
    pot: float = 0.0
    board: Optional[List[str]] = None
    game_type: str = "No Limit Hold'em"
    table_name: Optional[str] = None
    board_texture: Optional[str] = None
    spot_category: Optional[str] = None


class HandHistoryResponse(HandHistoryBase):
    """Hand history response schema."""

    id: uuid.UUID
    user_id: uuid.UUID
    site: str
    stakes: Optional[dict] = None
    max_seats: int = 6
    button_position: Optional[int] = None
    players: Optional[List[dict]] = None
    ev_loss: Optional[float] = None
    winners: Optional[List[dict]] = None
    external_hand_id: Optional[str] = None
    created_at: datetime
    tags: Optional[List[str]] = None

    model_config = {"from_attributes": True}


class HandHistoryDetailResponse(HandHistoryResponse):
    """Detailed hand history with actions."""

    raw_text: str
    parsed_data: Optional[dict] = None
    actions: Optional[List[dict]] = None


class HandTagCreate(BaseModel):
    """Schema for creating a tag."""

    tag: str = Field(..., min_length=1, max_length=100)


class HandTagResponse(BaseModel):
    """Tag response schema."""

    id: uuid.UUID
    hand_id: uuid.UUID
    user_id: uuid.UUID
    tag: str
    created_at: datetime

    model_config = {"from_attributes": True}


class UploadResponse(BaseModel):
    """Response for hand history upload."""

    success: bool
    hand_id: Optional[uuid.UUID] = None
    message: str
    hands_imported: int = 0


class BatchImportRequest(BaseModel):
    """Request for batch import."""

    hands: List[str] = Field(..., max_length=MAX_BATCH_SIZE)


class BatchImportResponse(BaseModel):
    """Response for batch import."""

    success: bool
    message: str
    hands_imported: int
    hand_ids: List[uuid.UUID]
    errors: List[str] = []


class LeakAnalysisRequest(BaseModel):
    """Request for leak analysis."""

    user_id: uuid.UUID
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    spot_categories: Optional[List[str]] = None
    min_hands: int = Field(default=10, ge=1, le=100)


class EvLossBySpot(BaseModel):
    """EV loss broken down by spot category."""

    spot_category: str
    total_ev_loss: float
    hand_count: int
    avg_ev_loss: float
    ev_loss_percentage: float


class LeakAnalysisResponse(BaseModel):
    """Response for leak analysis."""

    user_id: uuid.UUID
    total_hands_analyzed: int
    total_ev_loss: float
    overall_avg_ev_loss: float
    by_spot: List[EvLossBySpot]
    worst_spots: List[EvLossBySpot]
    recommendation: str


class StatsResponse(BaseModel):
    """Aggregated stats for a user."""

    user_id: uuid.UUID
    total_hands: int
    total_pot: float
    total_ev_loss: Optional[float] = None
    by_site: dict
    by_board_texture: dict
    by_spot_category: dict
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None


class HandFilterParams(BaseModel):
    """Filter parameters for hand queries."""

    user_id: uuid.UUID
    site: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    board_texture: Optional[str] = None
    spot_category: Optional[str] = None
    pot_min: Optional[float] = None
    pot_max: Optional[float] = None
    position: Optional[str] = None
    hero_name: Optional[str] = None
    tag: Optional[str] = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


# ----------------------------------------------------------------------
# Helper Functions
# ----------------------------------------------------------------------


def _parse_hand_to_model(text: str, user_id: uuid.UUID) -> tuple[HandHistory, List[HandAction]]:
    """
    Parse raw hand text and create HandHistory and HandAction models.

    Returns:
        Tuple of (HandHistory model, list of HandAction models)
    """
    from gto_poker.hand_history import detect_format, parse_hand, ActionType

    # Parse the hand
    fmt = detect_format(text)

    if fmt == "winamax":
        from gto_poker.hand_history import parse_winamax_hh

        parsed = parse_winamax_hh(text)
    elif fmt == "pokerstars":
        from gto_poker.hand_history import parse_pokerstars_hh

        parsed = parse_pokerstars_hh(text)
    elif fmt == "ggpoker":
        from gto_poker.hand_history import parse_ggpoker_hh

        parsed = parse_ggpoker_hh(text)
    else:
        raise ValueError(f"Unknown hand history format")

    # Map site string to enum
    site_map = {
        "winamax": SiteEnum.WINAMAX,
        "pokerstars": SiteEnum.POKERSTARS,
        "ggpoker": SiteEnum.GGPOKER,
    }
    site = site_map.get(fmt, SiteEnum.POKERSTARS)

    # Classify board texture if we have a board
    board_texture = None
    if parsed.board and len(parsed.board) >= 3:
        try:
            board_texture = classify_board_texture(parsed.board)
        except Exception:
            pass

    # Build parsed_data dict
    parsed_data = {
        "game_type": parsed.game_type,
        "limit_type": parsed.limit_type,
        "stakes": {"sb": parsed.stakes[0], "bb": parsed.stakes[1]} if parsed.stakes else None,
        "table_name": parsed.table_name,
        "max_seats": parsed.max_seats,
        "button_position": parsed.button_position,
        "players": [
            {
                "name": p.name,
                "seat": p.seat,
                "stack": p.stack,
                "position": getattr(p, "position", None),
                "hole_cards": getattr(p, "hole_cards", None),
            }
            for p in parsed.players
        ]
        if parsed.players
        else None,
        "actions": {
            street: [
                {
                    "player": a.player,
                    "action": a.action
                    if hasattr(a, "action")
                    else a.action_type.value
                    if hasattr(a, "action_type")
                    else str(a.action_type),
                    "amount": a.amount,
                    "street": a.street,
                }
                for a in actions
            ]
            for street, actions in parsed.actions.items()
        }
        if parsed.actions
        else {},
        "winners": [{"player": w[0], "amount": w[1]} for w in parsed.winners]
        if parsed.winners
        else None,
        "hero_name": parsed.hero_name,
    }

    # Build players list
    players_list = None
    if parsed.players:
        players_list = [
            {
                "name": p.name,
                "seat": p.seat,
                "stack": p.stack,
                "position": getattr(p, "position", None),
                "hole_cards": getattr(p, "hole_cards", None),
            }
            for p in parsed.players
        ]

    # Build stakes dict
    stakes_dict = None
    if parsed.stakes:
        stakes_dict = {"sb": parsed.stakes[0], "bb": parsed.stakes[1]}

    # Build winners dict
    winners_list = None
    if parsed.winners:
        winners_list = [{"player": w[0], "amount": w[1]} for w in parsed.winners]

    # Create HandHistory model
    hand = HandHistory(
        user_id=user_id,
        site=site,
        raw_text=text,
        parsed_data=parsed_data,
        hero_name=parsed.hero_name,
        stakes=stakes_dict,
        pot=parsed.pot,
        board=parsed.board[:5] if parsed.board else None,  # Limit to 5 cards
        board_texture=board_texture,
        game_type=parsed.game_type,
        table_name=parsed.table_name,
        max_seats=parsed.max_seats,
        button_position=parsed.button_position,
        players=players_list,
        winners=winners_list,
        external_hand_id=parsed.hand_id,
    )

    # Categorize spot
    all_actions = []
    for street, street_actions in parsed.actions.items():
        for idx, action in enumerate(street_actions):
            action_dict = {
                "player": action.player,
                "action_type": action.action
                if hasattr(action, "action")
                else str(action.action_type),
                "street": street,
                "position": None,  # Would need position tracking
            }
            all_actions.append(action_dict)

    if parsed.hero_name:
        try:
            spot_cat = categorize_spot(all_actions, parsed.hero_name)
            hand.spot_category = spot_cat
        except Exception:
            pass

    # Create HandAction models
    hand_actions = []
    for street, street_actions in parsed.actions.items():
        for idx, action in enumerate(street_actions):
            act_type = action.action if hasattr(action, "action") else str(action.action_type)
            hand_action = HandAction(
                hand=hand,  # Will be replaced after flush
                player=action.player,
                action_type=act_type,
                amount=action.amount,
                street=street,
                street_index=idx,
            )
            hand_actions.append(hand_action)

    return hand, hand_actions


# ----------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------


@router.post("/import", response_model=BatchImportResponse)
async def batch_import_hands(
    request: BatchImportRequest,
    user_id: uuid.UUID = Query(..., description="User ID for the hands"),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Batch import multiple hand histories.

    Parses each hand, stores in database, and returns IDs.
    Supports PokerStars, GGPoker, and Winamax formats.
    """
    hand_ids = []
    errors = []

    for i, hand_text in enumerate(request.hands):
        try:
            hand, hand_actions = _parse_hand_to_model(hand_text, user_id)
            db.add(hand)
            await db.flush()  # Get the hand ID

            # Update hand_actions with actual hand_id
            for ha in hand_actions:
                ha.hand_id = hand.id
                db.add(ha)

            hand_ids.append(hand.id)
        except Exception as e:
            errors.append(f"Hand {i}: {str(e)}")

    await db.commit()

    return BatchImportResponse(
        success=len(errors) == 0,
        message=f"Imported {len(hand_ids)} hands",
        hands_imported=len(hand_ids),
        hand_ids=hand_ids,
        errors=errors[:100],  # Limit error list
    )


@router.post("/batch-upload", response_model=BatchImportResponse)
async def batch_upload(
    file: UploadFile = File(...),
    user_id: uuid.UUID = Query(..., description="User ID for the hands"),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Upload a file containing multiple hand histories.

    Parses all hands from the file and stores them.
    """
    content = await file.read()
    text = content.decode("utf-8", errors="ignore")

    # Split by hand boundaries (look for common patterns)
    import re

    # Split by hand ID patterns
    hand_patterns = [
        r"(?:PokerStars Hand #|Winamax |GGPoker Hand #)",
    ]

    # Try to find individual hands
    hands = []
    for pattern in hand_patterns:
        matches = list(re.finditer(pattern, text, re.MULTILINE))
        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            hand_text = text[start:end].strip()
            if hand_text:
                hands.append(hand_text)

    if not hands:
        # Treat entire text as one hand
        hands = [text.strip()]

    if len(hands) > MAX_BATCH_SIZE:
        return BatchImportResponse(
            success=False,
            message=f"Too many hands ({len(hands)}). Maximum is {MAX_BATCH_SIZE}.",
            hands_imported=0,
            hand_ids=[],
            errors=[f"Batch size exceeds limit of {MAX_BATCH_SIZE} hands"],
        )

    hand_ids = []
    errors = []

    for i, hand_text in enumerate(hands):
        try:
            hand, hand_actions = _parse_hand_to_model(hand_text, user_id)
            db.add(hand)
            await db.flush()

            for ha in hand_actions:
                ha.hand_id = hand.id
                db.add(ha)

            hand_ids.append(hand.id)
        except Exception as e:
            errors.append(f"Hand {i}: {str(e)}")

    await db.commit()

    return BatchImportResponse(
        success=len(errors) == 0,
        message=f"Imported {len(hand_ids)} hands from file",
        hands_imported=len(hand_ids),
        hand_ids=hand_ids,
        errors=errors[:100],
    )


# ----------------------------------------------------------------------
# Parse endpoint (no DB save — just parse and return structured data)
# ----------------------------------------------------------------------


class ParseRequest(BaseModel):
    """Request to parse a hand history text."""

    text: str = Field(..., min_length=10, description="Raw hand history text")


class ParseResponse(BaseModel):
    """Response from parsing a hand history."""

    success: bool
    format: Optional[str] = None
    error: Optional[str] = None
    data: Optional[dict] = None


@router.post("/parse", response_model=ParseResponse)
async def parse_hand_history(request: ParseRequest):
    """
    Parse raw hand history text and return structured data without saving to DB.

    Supports PokerStars, GGPoker, and Winamax formats.
    Returns parsed hand with street-by-street action breakdown.
    """
    try:
        from gto_poker.hand_history import detect_format, parse_hand

        fmt = detect_format(request.text)
        if not fmt:
            return ParseResponse(
                success=False,
                format=None,
                error="Could not detect hand history format. Supported: PokerStars, GGPoker, Winamax",
            )

        parsed = parse_hand(request.text)

        # Build structured response
        players_data = []
        if parsed.players:
            for p in parsed.players:
                players_data.append(
                    {
                        "name": p.name,
                        "seat": p.seat,
                        "stack": p.stack,
                        "position": getattr(p, "position", None),
                        "hole_cards": getattr(p, "hole_cards", None),
                    }
                )

        actions_data = {}
        if parsed.actions:
            for street, street_actions in parsed.actions.items():
                actions_data[street] = [
                    {
                        "player": a.player,
                        "action": a.action,
                        "amount": a.amount,
                        "street": a.street,
                    }
                    for a in street_actions
                ]

        winners_data = None
        if parsed.winners:
            winners_data = [{"player": w[0], "amount": w[1]} for w in parsed.winners]

        data = {
            "hand_id": parsed.hand_id,
            "site": fmt or parsed.site,
            "game_type": parsed.game_type,
            "limit_type": parsed.limit_type,
            "stakes": {"sb": parsed.stakes[0], "bb": parsed.stakes[1]} if parsed.stakes else None,
            "table_name": parsed.table_name,
            "max_seats": parsed.max_seats,
            "button_position": parsed.button_position,
            "players": players_data,
            "actions": actions_data,
            "board": parsed.board,
            "pot": parsed.pot,
            "rake": parsed.rake,
            "winners": winners_data,
            "hero_name": parsed.hero_name,
        }

        return ParseResponse(
            success=True,
            format=fmt,
            data=data,
        )

    except Exception as e:
        return ParseResponse(
            success=False,
            format=None,
            error=f"Parse failed: {str(e)}",
        )


@router.get("/hands", response_model=List[HandHistoryResponse])
async def query_hands(
    user_id: uuid.UUID = Query(..., description="User ID"),
    site: Optional[str] = Query(None, description="Filter by site (pokerstars, ggpoker, winamax)"),
    date_from: Optional[datetime] = Query(None, description="Filter from date"),
    date_to: Optional[datetime] = Query(None, description="Filter to date"),
    board_texture: Optional[str] = Query(None, description="Filter by board texture"),
    spot_category: Optional[str] = Query(None, description="Filter by spot category"),
    pot_min: Optional[float] = Query(None, ge=0, description="Minimum pot size"),
    pot_max: Optional[float] = Query(None, ge=0, description="Maximum pot size"),
    hero_name: Optional[str] = Query(None, description="Filter by hero name"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    position: Optional[str] = Query(None, description="Filter by position"),
    limit: int = Query(50, ge=1, le=500, description="Max results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Query hands with various filters.

    Supports filtering by:
    - site: pokerstars, ggpoker, winamax
    - date_from/date_to: date range
    - board_texture: rainbow, two_suited, monotone, paired, connected, gapped
    - spot_category: preflop_call, preflop_3bet, flop_cbet, etc.
    - pot_min/pot_max: pot size range
    - hero_name: exact hero name match
    - tag: user-defined tag
    - position: player's position
    """
    # Build query
    query = select(HandHistory).options(selectinload(HandHistory.tags))

    # Apply filters
    filters = [HandHistory.user_id == user_id]

    if site:
        try:
            site_enum = SiteEnum(site.lower())
            filters.append(HandHistory.site == site_enum)
        except ValueError:
            pass

    if date_from:
        filters.append(HandHistory.created_at >= date_from)

    if date_to:
        filters.append(HandHistory.created_at <= date_to)

    if board_texture:
        try:
            bt_enum = BoardTexture(board_texture.lower())
            filters.append(HandHistory.board_texture == bt_enum)
        except ValueError:
            pass

    if spot_category:
        try:
            sc_enum = SpotCategory(spot_category.lower())
            filters.append(HandHistory.spot_category == sc_enum)
        except ValueError:
            pass

    if pot_min is not None:
        filters.append(HandHistory.pot >= pot_min)

    if pot_max is not None:
        filters.append(HandHistory.pot <= pot_max)

    if hero_name:
        filters.append(HandHistory.hero_name == hero_name)

    if tag:
        query = query.join(HandTag).where(HandTag.tag == tag)

    # Position filter: check if hero is in that position from players JSONB
    if position:
        pos_upper = position.upper()
        # Filter hands where hero's position matches using JSONB containment
        filters.append(HandHistory.players.contains([{"position": pos_upper}]))

    if filters:
        query = query.where(and_(*filters))

    # Order by created_at desc and paginate
    query = query.order_by(HandHistory.created_at.desc()).offset(offset).limit(limit)

    result = await db.execute(query)
    hands = result.scalars().unique().all()

    # Build response
    responses = []
    for hand in hands:
        resp = HandHistoryResponse(
            id=hand.id,
            user_id=hand.user_id,
            site=hand.site.value,
            hero_name=hand.hero_name,
            pot=hand.pot,
            board=hand.board,
            game_type=hand.game_type,
            table_name=hand.table_name,
            board_texture=hand.board_texture.value if hand.board_texture else None,
            spot_category=hand.spot_category.value if hand.spot_category else None,
            stakes=hand.stakes,
            max_seats=hand.max_seats,
            button_position=hand.button_position,
            players=hand.players,
            ev_loss=hand.ev_loss,
            winners=hand.winners,
            external_hand_id=hand.external_hand_id,
            created_at=hand.created_at,
            tags=[t.tag for t in hand.tags] if hand.tags else [],
        )
        responses.append(resp)

    return responses


@router.get("/hands/{hand_id}", response_model=HandHistoryDetailResponse)
async def get_hand(
    hand_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """Get detailed information about a specific hand."""
    query = (
        select(HandHistory)
        .options(
            selectinload(HandHistory.tags),
            selectinload(HandHistory.actions),
        )
        .where(HandHistory.id == hand_id)
    )

    result = await db.execute(query)
    hand = result.scalar_one_or_none()

    if not hand:
        raise HTTPException(status_code=404, detail="Hand not found")

    return HandHistoryDetailResponse(
        id=hand.id,
        user_id=hand.user_id,
        site=hand.site.value,
        hero_name=hand.hero_name,
        pot=hand.pot,
        board=hand.board,
        game_type=hand.game_type,
        table_name=hand.table_name,
        board_texture=hand.board_texture.value if hand.board_texture else None,
        spot_category=hand.spot_category.value if hand.spot_category else None,
        stakes=hand.stakes,
        max_seats=hand.max_seats,
        button_position=hand.button_position,
        players=hand.players,
        ev_loss=hand.ev_loss,
        winners=hand.winners,
        external_hand_id=hand.external_hand_id,
        created_at=hand.created_at,
        tags=[t.tag for t in hand.tags] if hand.tags else [],
        raw_text=hand.raw_text,
        parsed_data=hand.parsed_data,
        actions=[a.to_dict() for a in hand.actions] if hand.actions else [],
    )


@router.patch("/hands/{hand_id}/tags", response_model=List[HandTagResponse])
async def update_hand_tags(
    hand_id: uuid.UUID,
    tags: List[str],
    user_id: uuid.UUID = Query(..., description="User ID"),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Add/update tags for a hand.

    Replaces all existing tags with the new list.
    """
    # Verify hand exists and belongs to user
    query = select(HandHistory).where(
        HandHistory.id == hand_id,
        HandHistory.user_id == user_id,
    )
    result = await db.execute(query)
    hand = result.scalar_one_or_none()

    if not hand:
        raise HTTPException(status_code=404, detail="Hand not found")

    # Delete existing tags
    await db.execute(delete(HandTag).where(HandTag.hand_id == hand_id))

    # Add new tags
    new_tags = []
    for tag_str in tags:
        tag = HandTag(
            hand_id=hand_id,
            user_id=user_id,
            tag=tag_str.strip(),
        )
        db.add(tag)
        new_tags.append(tag)

    await db.commit()

    # Refresh to get IDs
    for tag in new_tags:
        await db.refresh(tag)

    return [HandTagResponse.model_validate(t) for t in new_tags]


@router.get("/export")
async def export_hands(
    user_id: uuid.UUID = Query(..., description="User ID"),
    site: Optional[str] = Query(None, description="Filter by site"),
    date_from: Optional[datetime] = Query(None, description="Filter from date"),
    date_to: Optional[datetime] = Query(None, description="Filter to date"),
    board_texture: Optional[str] = Query(None, description="Filter by board texture"),
    spot_category: Optional[str] = Query(None, description="Filter by spot category"),
    pot_min: Optional[float] = Query(None, ge=0, description="Minimum pot"),
    pot_max: Optional[float] = Query(None, ge=0, description="Maximum pot"),
    limit: int = Query(10000, ge=1, le=50000, description="Max hands to export"),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Export hands as CSV.

    Returns a CSV file with hand data.
    """
    # Build query (same as query_hands but with different result processing)
    query = select(HandHistory).options(selectinload(HandHistory.actions))

    filters = [HandHistory.user_id == user_id]

    if site:
        try:
            site_enum = SiteEnum(site.lower())
            filters.append(HandHistory.site == site_enum)
        except ValueError:
            pass

    if date_from:
        filters.append(HandHistory.created_at >= date_from)

    if date_to:
        filters.append(HandHistory.created_at <= date_to)

    if board_texture:
        try:
            bt_enum = BoardTexture(board_texture.lower())
            filters.append(HandHistory.board_texture == bt_enum)
        except ValueError:
            pass

    if spot_category:
        try:
            sc_enum = SpotCategory(spot_category.lower())
            filters.append(HandHistory.spot_category == sc_enum)
        except ValueError:
            pass

    if pot_min is not None:
        filters.append(HandHistory.pot >= pot_min)

    if pot_max is not None:
        filters.append(HandHistory.pot <= pot_max)

    if filters:
        query = query.where(and_(*filters))
    query = query.order_by(HandHistory.created_at.desc()).limit(limit)

    result = await db.execute(query)
    hands = result.scalars().unique().all()

    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow(
        [
            "hand_id",
            "site",
            "hero_name",
            "game_type",
            "stakes",
            "table_name",
            "pot",
            "board",
            "board_texture",
            "spot_category",
            "ev_loss",
            "winners",
            "players",
            "created_at",
        ]
    )

    # Data rows
    for hand in hands:
        writer.writerow(
            [
                str(hand.id),
                hand.site.value,
                hand.hero_name or "",
                hand.game_type,
                str(hand.stakes) if hand.stakes else "",
                hand.table_name or "",
                hand.pot,
                " ".join(hand.board) if hand.board else "",
                hand.board_texture.value if hand.board_texture else "",
                hand.spot_category.value if hand.spot_category else "",
                hand.ev_loss or "",
                str(hand.winners) if hand.winners else "",
                str(hand.players) if hand.players else "",
                hand.created_at.isoformat() if hand.created_at else "",
            ]
        )

    output.seek(0)

    # Return as downloadable file
    from fastapi.responses import StreamingResponse

    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=hand_history_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        },
    )


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    user_id: uuid.UUID = Query(..., description="User ID"),
    date_from: Optional[datetime] = Query(None, description="Filter from date"),
    date_to: Optional[datetime] = Query(None, description="Filter to date"),
    site: Optional[str] = Query(None, description="Filter by site"),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Get aggregated statistics for a user.

    Returns counts and sums grouped by various dimensions.
    """
    filters = [HandHistory.user_id == user_id]

    if date_from:
        filters.append(HandHistory.created_at >= date_from)
    if date_to:
        filters.append(HandHistory.created_at <= date_to)
    if site:
        try:
            site_enum = SiteEnum(site.lower())
            filters.append(HandHistory.site == site_enum)
        except ValueError:
            pass

    query = select(HandHistory).where(and_(*filters))
    result = await db.execute(query)
    hands = result.scalars().all()

    total_hands = len(hands)
    total_pot = sum(h.pot for h in hands if h.pot)
    total_ev_loss = sum(h.ev_loss for h in hands if h.ev_loss is not None)

    # Group by site
    by_site = {}
    for h in hands:
        site_name = h.site.value
        if site_name not in by_site:
            by_site[site_name] = {"count": 0, "total_pot": 0.0, "total_ev_loss": 0.0}
        by_site[site_name]["count"] += 1
        by_site[site_name]["total_pot"] += h.pot or 0
        by_site[site_name]["total_ev_loss"] += h.ev_loss or 0

    # Group by board texture
    by_board_texture = {}
    for h in hands:
        if h.board_texture:
            bt = h.board_texture.value
            if bt not in by_board_texture:
                by_board_texture[bt] = {"count": 0, "total_pot": 0.0}
            by_board_texture[bt]["count"] += 1
            by_board_texture[bt]["total_pot"] += h.pot or 0

    # Group by spot category
    by_spot_category = {}
    for h in hands:
        if h.spot_category:
            sc = h.spot_category.value
            if sc not in by_spot_category:
                by_spot_category[sc] = {"count": 0, "total_pot": 0.0, "total_ev_loss": 0.0}
            by_spot_category[sc]["count"] += 1
            by_spot_category[sc]["total_pot"] += h.pot or 0
            by_spot_category[sc]["total_ev_loss"] += h.ev_loss or 0

    return StatsResponse(
        user_id=user_id,
        total_hands=total_hands,
        total_pot=total_pot,
        total_ev_loss=total_ev_loss if total_ev_loss > 0 else None,
        by_site=by_site,
        by_board_texture=by_board_texture,
        by_spot_category=by_spot_category,
        date_from=date_from,
        date_to=date_to,
    )


@router.post("/analyze-leaks", response_model=LeakAnalysisResponse)
async def analyze_leaks(
    request: LeakAnalysisRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Analyze player's EV loss by spot category.

    Compares actual actions to GTO baseline (simplified).
    In production, this would integrate with actual GTO solver data.
    """
    filters = [HandHistory.user_id == request.user_id]

    if request.date_from:
        filters.append(HandHistory.created_at >= request.date_from)
    if request.date_to:
        filters.append(HandHistory.created_at <= request.date_to)

    query = select(HandHistory).where(and_(*filters))
    result = await db.execute(query)
    hands = result.scalars().all()

    if len(hands) < request.min_hands:
        return LeakAnalysisResponse(
            user_id=request.user_id,
            total_hands_analyzed=len(hands),
            total_ev_loss=0.0,
            overall_avg_ev_loss=0.0,
            by_spot=[],
            worst_spots=[],
            recommendation=f"Not enough hands ({len(hands)} < {request.min_hands}) for reliable leak analysis",
        )

    # Calculate EV loss by spot category
    spot_stats = {}

    for hand in hands:
        if hand.spot_category and hand.ev_loss is not None:
            sc = hand.spot_category.value
            if sc not in spot_stats:
                spot_stats[sc] = {"total_ev_loss": 0.0, "count": 0}
            spot_stats[sc]["total_ev_loss"] += hand.ev_loss
            spot_stats[sc]["count"] += 1

    # Filter by requested spot categories if specified
    if request.spot_categories:
        spot_stats = {k: v for k, v in spot_stats.items() if k in request.spot_categories}

    total_ev_loss = sum(s["total_ev_loss"] for s in spot_stats.values())
    total_hands = sum(s["count"] for s in spot_stats.values())
    overall_avg = total_ev_loss / total_hands if total_hands > 0 else 0.0

    # Build by_spot list
    by_spot = []
    for spot, stats in spot_stats.items():
        avg = stats["total_ev_loss"] / stats["count"] if stats["count"] > 0 else 0.0
        pct = (avg / overall_avg * 100) if overall_avg > 0 else 0.0
        by_spot.append(
            EvLossBySpot(
                spot_category=spot,
                total_ev_loss=stats["total_ev_loss"],
                hand_count=stats["count"],
                avg_ev_loss=avg,
                ev_loss_percentage=pct,
            )
        )

    # Sort by total ev loss descending
    by_spot.sort(key=lambda x: x.total_ev_loss, reverse=True)

    # Worst spots (top 3)
    worst_spots = by_spot[:3]

    # Generate recommendation
    if worst_spots:
        worst = worst_spots[0]
        recommendation = (
            f"Your biggest leak is in {worst.spot_category.replace('_', ' ')} spots, "
            f"with an average EV loss of {worst.avg_ev_loss:.2f}bb per hand "
            f"across {worst.hand_count} hands. Focus on improving this area first."
        )
    else:
        recommendation = "No significant leaks detected based on current data."

    return LeakAnalysisResponse(
        user_id=request.user_id,
        total_hands_analyzed=len(hands),
        total_ev_loss=total_ev_loss,
        overall_avg_ev_loss=overall_avg,
        by_spot=by_spot,
        worst_spots=worst_spots,
        recommendation=recommendation,
    )


@router.get("/board-texture/{texture}")
async def get_hands_by_board_texture(
    texture: str,
    user_id: uuid.UUID = Query(..., description="User ID"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Get hands filtered by board texture classification.

    Texture types: rainbow, two_suited, monotone, paired, connected, gapped
    """
    try:
        texture_enum = BoardTexture(texture.lower())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid board texture. Valid types: {[t.value for t in BoardTexture]}",
        )

    query = (
        select(HandHistory)
        .where(
            HandHistory.user_id == user_id,
            HandHistory.board_texture == texture_enum,
        )
        .order_by(HandHistory.created_at.desc())
        .limit(limit)
    )

    result = await db.execute(query)
    hands = result.scalars().all()

    return [
        HandHistoryResponse(
            id=h.id,
            user_id=h.user_id,
            site=h.site.value,
            hero_name=h.hero_name,
            pot=h.pot,
            board=h.board,
            game_type=h.game_type,
            table_name=h.table_name,
            board_texture=h.board_texture.value if h.board_texture else None,
            spot_category=h.spot_category.value if h.spot_category else None,
            stakes=h.stakes,
            max_seats=h.max_seats,
            button_position=h.button_position,
            players=h.players,
            ev_loss=h.ev_loss,
            winners=h.winners,
            external_hand_id=h.external_hand_id,
            created_at=h.created_at,
            tags=[t.tag for t in h.tags] if hasattr(h, "tags") and h.tags else [],
        )
        for h in hands
    ]


@router.get("/spot-category/{category}")
async def get_hands_by_spot(
    category: str,
    user_id: uuid.UUID = Query(..., description="User ID"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Get hands filtered by spot category.

    Categories: preflop_call, preflop_3bet, preflop_4bet, flop_cbet,
                flop_checkraise, turn_cbet, turn_check, river_shove, river_donk
    """
    try:
        category_enum = SpotCategory(category.lower())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid spot category. Valid types: {[c.value for c in SpotCategory]}",
        )

    query = (
        select(HandHistory)
        .where(
            HandHistory.user_id == user_id,
            HandHistory.spot_category == category_enum,
        )
        .order_by(HandHistory.created_at.desc())
        .limit(limit)
    )

    result = await db.execute(query)
    hands = result.scalars().all()

    return [
        HandHistoryResponse(
            id=h.id,
            user_id=h.user_id,
            site=h.site.value,
            hero_name=h.hero_name,
            pot=h.pot,
            board=h.board,
            game_type=h.game_type,
            table_name=h.table_name,
            board_texture=h.board_texture.value if h.board_texture else None,
            spot_category=h.spot_category.value if h.spot_category else None,
            stakes=h.stakes,
            max_seats=h.max_seats,
            button_position=h.button_position,
            players=h.players,
            ev_loss=h.ev_loss,
            winners=h.winners,
            external_hand_id=h.external_hand_id,
            created_at=h.created_at,
            tags=[t.tag for t in h.tags] if hasattr(h, "tags") and h.tags else [],
        )
        for h in hands
    ]


class PlaybackStep(BaseModel):
    """A single step in hand playback."""

    step: int
    street: str
    action_index: int
    action: str
    player: str
    amount: Optional[float] = None
    pot_after: float
    board_after: List[str] = []
    is_hero_action: bool = False
    hero_position: Optional[str] = None


class HandPlaybackResponse(BaseModel):
    """Step-by-step playback of a hand."""

    hand_id: uuid.UUID
    hero_name: Optional[str] = None
    board: List[str] = []
    stakes: Optional[dict] = None
    pot: float = 0.0
    button_position: Optional[int] = None
    players: List[dict] = []
    steps: List[PlaybackStep] = []
    gto_comparison: Optional[dict] = None


@router.post("/hands/{hand_id}/recalculate-ev", response_model=HandHistoryResponse)
async def recalculate_ev(
    hand_id: uuid.UUID,
    user_id: uuid.UUID = Query(..., description="User ID"),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Recalculate EV loss for a hand by comparing actual actions to GTO baseline.
    """
    from apps.api.services.gto_comparison import compare_to_gto

    query = (
        select(HandHistory)
        .options(
            selectinload(HandHistory.actions),
        )
        .where(HandHistory.id == hand_id)
    )

    result = await db.execute(query)
    hand = result.scalar_one_or_none()

    if not hand:
        raise HTTPException(status_code=404, detail="Hand not found")

    if hand.user_id != user_id:
        raise HTTPException(status_code=403, detail="Hand does not belong to user")

    if not hand.parsed_data:
        raise HTTPException(status_code=400, detail="Hand has no parsed data")

    total_ev_loss = 0.0
    hero_name = hand.hero_name or hand.parsed_data.get("hero_name")

    if hero_name and "actions" in hand.parsed_data:
        if hand.parsed_data.get("actions"):
            try:
                comparison = compare_to_gto(hand.parsed_data, hero_name)
                total_ev_loss = comparison.ev_loss
            except Exception:
                total_ev_loss = 0.0

    hand.ev_loss = total_ev_loss
    await db.commit()
    await db.refresh(hand)

    return HandHistoryResponse(
        id=hand.id,
        user_id=hand.user_id,
        site=hand.site.value,
        hero_name=hand.hero_name,
        pot=hand.pot,
        board=hand.board,
        game_type=hand.game_type,
        table_name=hand.table_name,
        board_texture=hand.board_texture.value if hand.board_texture else None,
        spot_category=hand.spot_category.value if hand.spot_category else None,
        stakes=hand.stakes,
        max_seats=hand.max_seats,
        button_position=hand.button_position,
        players=hand.players,
        ev_loss=hand.ev_loss,
        winners=hand.winners,
        external_hand_id=hand.external_hand_id,
        created_at=hand.created_at,
        tags=[t.tag for t in hand.tags] if hasattr(hand, "tags") and hand.tags else [],
    )


@router.get("/hands/{hand_id}/playback", response_model=HandPlaybackResponse)
async def get_hand_playback(
    hand_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Get step-by-step playback data for a hand.
    """
    query = (
        select(HandHistory)
        .options(
            selectinload(HandHistory.actions),
        )
        .where(HandHistory.id == hand_id)
    )

    result = await db.execute(query)
    hand = result.scalar_one_or_none()

    if not hand:
        raise HTTPException(status_code=404, detail="Hand not found")

    hero_name = hand.hero_name or (hand.parsed_data.get("hero_name") if hand.parsed_data else None)

    steps = []
    current_pot = 0.0
    current_board: List[str] = []
    step_num = 0

    streets_order = ["preflop", "flop", "turn", "river", "showdown"]

    for street in streets_order:
        street_actions: List[dict] = []
        if hand.parsed_data and "actions" in hand.parsed_data:
            street_actions = hand.parsed_data["actions"].get(street, [])

        for idx, action in enumerate(street_actions):
            action_type = action.get("action", action.get("action_type", ""))
            player = action.get("player", "")
            amount = action.get("amount")

            if action_type in ("bet", "raise", "call"):
                if amount:
                    current_pot += amount
            elif action_type == "allin" and amount:
                current_pot += amount

            if street == "flop" and hand.board and len(hand.board) >= 3:
                current_board = hand.board[:3]
            elif street == "turn" and hand.board and len(hand.board) >= 4:
                current_board = hand.board[:4]
            elif street == "river" and hand.board and len(hand.board) >= 5:
                current_board = hand.board[:5]

            is_hero = (player == hero_name) if hero_name else False

            steps.append(
                PlaybackStep(
                    step=step_num,
                    street=street,
                    action_index=idx,
                    action=action_type,
                    player=player,
                    amount=amount,
                    pot_after=current_pot,
                    board_after=list(current_board),
                    is_hero_action=is_hero,
                    hero_position=None,
                )
            )
            step_num += 1

    gto_comp = None
    if hero_name and hand.ev_loss is not None:
        from apps.api.services.gto_comparison import compare_to_gto

        try:
            comparison = compare_to_gto(hand.parsed_data, hero_name)
            gto_comp = {
                "ev_loss": comparison.ev_loss,
                "gto_action": comparison.gto_action,
                "user_action": comparison.user_action,
                "recommendation": comparison.recommendation,
            }
        except Exception:
            pass

    return HandPlaybackResponse(
        hand_id=hand.id,
        hero_name=hero_name,
        board=hand.board or [],
        stakes=hand.stakes,
        pot=hand.pot or current_pot,
        button_position=hand.button_position,
        players=hand.players or [],
        steps=steps,
        gto_comparison=gto_comp,
    )
