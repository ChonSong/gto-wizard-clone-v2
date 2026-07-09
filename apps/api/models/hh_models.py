"""
SQLAlchemy models for hand history storage and analysis.

Provides database models for:
- HandHistory: Individual poker hand records
- HandTag: User-defined tags for hands
- HandAction: Individual betting actions within a hand
"""

import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import List, Optional

from sqlalchemy import (
    String,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import JSON
from sqlalchemy import String
from sqlalchemy.orm import relationship

from apps.api.services.database import Base


class SiteEnum(PyEnum):
    """Supported poker sites."""
    POKERSTARS = "pokerstars"
    GGPOKER = "ggpoker"
    WINAMAX = "winamax"


class BoardTexture(PyEnum):
    """Board texture classifications."""
    RAINBOW = "rainbow"           # All different suits
    TWO_SUITED = "two_suited"     # Two cards of same suit
    MONOTONE = "monotone"         # All three cards same suit
    PAIRED = "paired"             # Contains a pair
    CONNECTED = "connected"        # Cards consecutive (3-4-5)
    GAPPED = "gapped"             # Has gaps between cards
    DOUBLE_PAIRED = "double_paired"  # Two pairs on board


class SpotCategory(PyEnum):
    """Spot categorization for leak analysis."""
    PREFLOP_CALL = "preflop_call"
    PREFLOP_3BET = "preflop_3bet"
    PREFLOP_4BET = "preflop_4bet"
    PREFLOP_SQUEEZE = "preflop_squeeze"
    FLOP_CBET = "flop_cbet"
    FLOP_CHECKRAISE = "flop_checkraise"
    FLOP_CHECKCALL = "flop_checkcall"
    TURN_CBET = "turn_cbet"
    TURN_CHECK = "turn_check"
    TURN_CHECKRAISE = "turn_checkraise"
    RIVER_SHOVE = "river_shove"
    RIVER_DONK = "river_donk"
    RIVER_CALL = "river_call"


class HandHistory(Base):
    """
    Stores a complete poker hand history.
    
    Contains both raw text and parsed data for flexibility.
    """
    __tablename__ = "hand_histories"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), nullable=False, index=True)
    
    # Site information
    site = Column(Enum(SiteEnum), nullable=False)
    
    # Raw hand history text
    raw_text = Column(Text, nullable=False)
    
    # Parsed structured data
    parsed_data = Column(JSON, nullable=True)
    
    # Hero player info
    hero_name = Column(String(100), nullable=True)
    
    # Stakes as JSON for flexibility (e.g., {"sb": 0.01, "bb": 0.02})
    stakes = Column(JSON, nullable=True)
    
    # Pot information
    pot = Column(Float, default=0.0)
    
    # Board cards as JSON list
    board = Column(JSON, nullable=True)
    
    # Board texture classification
    board_texture = Column(Enum(BoardTexture), nullable=True)
    
    # Spot categorization
    spot_category = Column(Enum(SpotCategory), nullable=True)
    
    # Game type (e.g., "No Limit Hold'em", "Pot Limit Omaha")
    game_type = Column(String(50), default="No Limit Hold'em")
    
    # Table info
    table_name = Column(String(200), nullable=True)
    max_seats = Column(Integer, default=6)
    button_position = Column(Integer, nullable=True)
    
    # Players involved
    players = Column(JSON, nullable=True)  # List of player info
    
    # EV metrics
    ev_loss = Column(Float, nullable=True)  # Expected value loss vs GTO
    
    # Winners info
    winners = Column(JSON, nullable=True)  # [{"player": "X", "amount": Y}]
    
    # Hand ID from site
    external_hand_id = Column(String(100), nullable=True, index=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    tags = relationship("HandTag", back_populates="hand", cascade="all, delete-orphan")
    actions = relationship("HandAction", back_populates="hand", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index("ix_hand_histories_user_site", "user_id", "site"),
        Index("ix_hand_histories_user_created", "user_id", "created_at"),
        Index("ix_hand_histories_board_texture", "board_texture"),
        Index("ix_hand_histories_spot_category", "spot_category"),
    )

    def to_dict(self) -> dict:
        """Convert model to dictionary."""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "site": self.site.value if self.site else None,
            "hero_name": self.hero_name,
            "stakes": self.stakes,
            "pot": self.pot,
            "board": self.board,
            "board_texture": self.board_texture.value if self.board_texture else None,
            "spot_category": self.spot_category.value if self.spot_category else None,
            "game_type": self.game_type,
            "table_name": self.table_name,
            "max_seats": self.max_seats,
            "button_position": self.button_position,
            "players": self.players,
            "ev_loss": self.ev_loss,
            "winners": self.winners,
            "external_hand_id": self.external_hand_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class HandTag(Base):
    """
    User-defined tags for hand histories.
    
    Allows users to categorize and annotate their hands.
    """
    __tablename__ = "hand_tags"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    hand_id = Column(
        String(36), 
        ForeignKey("hand_histories.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    user_id = Column(String(36), nullable=False, index=True)
    tag = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    hand = relationship("HandHistory", back_populates="tags")

    # Constraints
    __table_args__ = (
        UniqueConstraint("hand_id", "tag", name="uq_hand_tag_hand_tag"),
        Index("ix_hand_tags_user_tag", "user_id", "tag"),
    )

    def to_dict(self) -> dict:
        """Convert model to dictionary."""
        return {
            "id": str(self.id),
            "hand_id": str(self.hand_id),
            "user_id": str(self.user_id),
            "tag": self.tag,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class HandAction(Base):
    """
    Individual betting action within a hand.
    
    Stores each player's action separately for detailed analysis.
    """
    __tablename__ = "hand_actions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    hand_id = Column(
        String(36), 
        ForeignKey("hand_histories.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    
    # Player info
    player = Column(String(100), nullable=False)
    position = Column(String(20), nullable=True)  # "BTN", "SB", "BB", "UTG", etc.
    
    # Action details
    action_type = Column(String(20), nullable=False)  # "fold", "check", "call", "bet", "raise", "allin"
    amount = Column(Float, nullable=True)
    
    # Street info
    street = Column(String(20), nullable=False, default="preflop")  # "preflop", "flop", "turn", "river"
    street_index = Column(Integer, default=0)  # Index of action on this street
    
    # GTO comparison metrics
    ev_loss = Column(Float, nullable=True)  # EV loss from not using GTO action
    gto_action = Column(String(20), nullable=True)  # Recommended GTO action
    
    # Pot odds and other calculated metrics
    pot_odds = Column(Float, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    hand = relationship("HandHistory", back_populates="actions")

    # Indexes
    __table_args__ = (
        Index("ix_hand_actions_hand_street", "hand_id", "street"),
        Index("ix_hand_actions_player", "player"),
    )

    def to_dict(self) -> dict:
        """Convert model to dictionary."""
        return {
            "id": str(self.id),
            "hand_id": str(self.hand_id),
            "player": self.player,
            "position": self.position,
            "action_type": self.action_type,
            "amount": self.amount,
            "street": self.street,
            "street_index": self.street_index,
            "ev_loss": self.ev_loss,
            "gto_action": self.gto_action,
            "pot_odds": self.pot_odds,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ----------------------------------------------------------------------
# Helper Functions
# ----------------------------------------------------------------------

def classify_board_texture(board: List[str]) -> BoardTexture:
    """
    Classify a board's texture based on its cards.
    
    Args:
        board: List of card strings (e.g., ["Ah", "Kh", "Qh"])
        
    Returns:
        BoardTexture enum value
    """
    if not board or len(board) < 3:
        return BoardTexture.RAINBOW
    
    # Extract suits and ranks
    suits = [card[-1].lower() for card in board[:3]]
    ranks = [card[0].upper() for card in board[:3]]
    
    # Check for pairs
    rank_counts: dict = {}
    for r in ranks:
        rank_counts[r] = rank_counts.get(r, 0) + 1
    
    if 3 in rank_counts.values():
        return BoardTexture.PAIRED
    if 2 in rank_counts.values():
        return BoardTexture.DOUBLE_PAIRED  # Actually just paired for flop
    
    # Check suit uniformity
    if len(set(suits)) == 1:
        return BoardTexture.MONOTONE
    if len(set(suits)) == 2:
        return BoardTexture.TWO_SUITED
    
    # Check connectivity (ranks)
    rank_values = []
    for r in ranks:
        if r == 'T':
            rank_values.append(10)
        elif r == 'J':
            rank_values.append(11)
        elif r == 'Q':
            rank_values.append(12)
        elif r == 'K':
            rank_values.append(13)
        elif r == 'A':
            rank_values.append(14)
        else:
            rank_values.append(int(r))
    
    rank_values.sort()
    gaps = [rank_values[i+1] - rank_values[i] for i in range(len(rank_values)-1)]
    
    if max(gaps) <= 1:
        return BoardTexture.CONNECTED
    elif max(gaps) == 2:
        return BoardTexture.GAPPED
    
    return BoardTexture.RAINBOW


def categorize_spot(
    actions: List[dict],
    hero_name: str,
    street: str = "flop"
) -> SpotCategory:
    """
    Categorize a hand into a spot type based on actions.
    
    Args:
        actions: List of action dicts with keys: player, action_type, street, position
        hero_name: Name of the hero (user)
        street: The street to categorize (default: "flop")
        
    Returns:
        SpotCategory enum value
    """
    hero_actions = [a for a in actions if a.get("player") == hero_name]
    
    if not hero_actions:
        return SpotCategory.PREFLOP_CALL
    
    # Get last hero action on each street
    preflop_hero = [a for a in hero_actions if a.get("street") == "preflop"]
    flop_hero = [a for a in hero_actions if a.get("street") == "flop"]
    turn_hero = [a for a in hero_actions if a.get("street") == "turn"]
    river_hero = [a for a in hero_actions if a.get("street") == "river"]
    
    # Count raises in preflop to determine spot type
    preflop_raises = len([a for a in preflop_hero if a.get("action_type") in ("raise", "allin")])
    
    if preflop_raises >= 2:
        spot = SpotCategory.PREFLOP_4BET
    elif preflop_raises == 1:
        # Check if there was a 3-bet (opponent raised before)
        all_preflop_actions = [a for a in actions if a.get("street") == "preflop"]
        raise_count_before_hero = 0
        hero_idx = None
        for i, a in enumerate(all_preflop_actions):
            if a.get("player") == hero_name:
                hero_idx = i
            if a.get("action_type") in ("raise", "allin") and hero_idx is not None and i < hero_idx:
                raise_count_before_hero += 1
        
        if raise_count_before_hero > 0:
            spot = SpotCategory.PREFLOP_3BET
        else:
            spot = SpotCategory.PREFLOP_SQUEEZE
    else:
        spot = SpotCategory.PREFLOP_CALL
    
    # Check for continuation bet on flop
    if flop_hero:
        last_flop_action = flop_hero[-1]
        if last_flop_action.get("action_type") in ("bet", "allin"):
            if spot in (SpotCategory.PREFLOP_CALL, SpotCategory.PREFLOP_SQUEEZE):
                return SpotCategory.FLOP_CBET
            return SpotCategory.FLOP_CHECKRAISE
    
    # Check for check-raise on flop
    if flop_hero:
        for i, a in enumerate(flop_hero):
            if a.get("action_type") == "check":
                if i + 1 < len(flop_hero) and flop_hero[i + 1].get("action_type") in ("raise", "bet"):
                    return SpotCategory.FLOP_CHECKRAISE
    
    # Check turn actions
    if turn_hero:
        last_turn_action = turn_hero[-1]
        if last_turn_action.get("action_type") in ("bet", "allin"):
            return SpotCategory.TURN_CBET
        if last_turn_action.get("action_type") == "check":
            return SpotCategory.TURN_CHECK
    
    # Check river actions
    if river_hero:
        last_river_action = river_hero[-1]
        if last_river_action.get("action_type") in ("raise", "allin"):
            return SpotCategory.RIVER_SHOVE
        if last_river_action.get("action_type") == "bet":
            return SpotCategory.RIVER_DONK
    
    return spot
