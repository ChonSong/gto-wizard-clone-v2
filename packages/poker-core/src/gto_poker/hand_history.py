"""Hand history parsers for Winamax, PokerStars, and GGPoker formats."""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from enum import Enum


# ----------------------------------------------------------------------
# Enums for parsed hand data
# ----------------------------------------------------------------------

class GameType(Enum):
    HOLDEM = "Hold'em"
    PLO = "Pot Limit Omaha"
    PLO5 = "Pot Limit Omaha 5"
    RAZZ = "Razz"
    STUD = "Seven Card Stud"
    MIXED = "Mixed Games"


class LimitType(Enum):
    NO_LIMIT = "No Limit"
    POT_LIMIT = "Pot Limit"
    FIXED_LIMIT = "Fixed Limit"


class ActionType(Enum):
    BLIND = "blind"
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    BET = "bet"
    RAISE = "raise"
    ANTE = "ante"
    SHOW = "show"
    MUCK = "muck"


@dataclass
class Player:
    """Player at the table."""
    name: str
    seat: int
    stack: float
    position: Optional[str] = None  # "BTN", "SB", "BB", "UTG", etc.
    hole_cards: Optional[List[str]] = None


@dataclass
class Action:
    """A betting action."""
    player: str
    action: str  # 'fold', 'check', 'call', 'bet', 'raise', 'allin'
    amount: Optional[float] = None
    street: str = "preflop"  # preflop, flop, turn, river
    
    @property
    def action_type(self) -> str:
        """Backward compatibility alias."""
        return self.action


@dataclass
class Board:
    """Community cards board."""
    flop: Optional[List[str]] = None
    turn: Optional[str] = None
    river: Optional[str] = None

    def all_cards(self) -> List[str]:
        cards = []
        if self.flop:
            cards.extend(self.flop)
        if self.turn:
            cards.append(self.turn)
        if self.river:
            cards.append(self.river)
        return cards


@dataclass
class Winner:
    """Hand showdown winner."""
    player: str
    amount: float
    hand_description: Optional[str] = None


@dataclass
class ParsedHand:
    """Parsed hand history data structure."""
    hand_id: str = ''
    site: str = 'unknown'
    game_type: str = "No Limit Hold'em"
    limit_type: str = 'No Limit'
    stakes: Optional[tuple] = None  # (small_blind, big_blind)
    table_name: str = ''
    max_seats: int = 6
    button_position: int = 0
    players: List[Player] = field(default_factory=list)
    actions: Dict[str, List[Action]] = field(default_factory=dict)
    board: List[str] = field(default_factory=list)
    pot: float = 0.0
    rake: float = 0.0
    winners: List[tuple] = field(default_factory=list)  # [(player, amount), ...]
    hero_name: Optional[str] = None
    raw_text: str = ''


# Backward compatibility alias - PlayerInfo is the same as Player
PlayerInfo = Player


# Winamax uses € symbol
CURRENCY_SYMBOLS = ['€', '€']


def _parse_currency_amount(amount_str: str) -> float:
    """Parse currency amount, handling € symbol and formatting."""
    # Remove currency symbols and whitespace
    cleaned = amount_str.replace('€', '').replace('$', '').replace(' ', '').strip()
    # Handle European formatting (1.234,56 -> 1234.56)
    if ',' in cleaned and '.' in cleaned:
        if cleaned.rfind(',') > cleaned.rfind('.'):
            # 1.234,56 format
            cleaned = cleaned.replace('.', '').replace(',', '.')
        else:
            # 1,234.56 format
            cleaned = cleaned.replace(',', '')
    elif ',' in cleaned:
        # Could be European decimal or thousands separator
        parts = cleaned.split(',')
        if len(parts[-1]) == 2:
            # Likely decimal: 45,50
            cleaned = cleaned.replace(',', '.')
        else:
            # Likely thousands: 1,234
            cleaned = cleaned.replace(',', '')
    return float(cleaned)


def _parse_card(card_str: str) -> str:
    """Parse a card string like 'As', 'Kh', '10d'."""
    card_str = card_str.strip()
    if len(card_str) < 2:
        return ''
    # Handle 10 as 'T'
    rank = card_str[0].upper()
    if rank == '1' and card_str.startswith('10'):
        rank = 'T'
    suit = card_str[-1].lower()
    if rank in ['2', '3', '4', '5', '6', '7', '8', '9', 'T', 'J', 'Q', 'K', 'A'] and suit in ['h', 'd', 'c', 's']:
        return f"{rank}{suit}"
    return ''


def _parse_hole_cards(cards_str: str) -> List[str]:
    """Parse hole cards string like '[As Kh]' or 'As Kh'."""
    # Remove brackets
    cards_str = cards_str.strip('[]')
    cards = []
    for card in cards_str.split():
        parsed = _parse_card(card)
        if parsed:
            cards.append(parsed)
    return cards


def parse_winamax_hh(text: str) -> ParsedHand:
    """Parse Winamax hand history text into ParsedHand structure.
    
    Args:
        text: Raw Winamax hand history text
        
    Returns:
        ParsedHand dataclass with all parsed fields
    """
    lines = text.strip().split('\n')
    hand = ParsedHand(raw_text=text)
    
    # Track current street for actions
    current_street = 'preflop'
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1  # increment BEFORE continue statements
        
        # Parse header: "Winamax 8-Game - 2026-05-25" or "Winamax Hold'em - 2026-05-25"
        if line.startswith('Winamax'):
            # Set site
            hand.site = 'winamax'
            # Extract game type and date
            # Format: "Winamax [GameType] - YYYY-MM-DD"
            parts = line.split(' - ')
            if len(parts) >= 2:
                game_part = parts[0].replace('Winamax', '').strip()
                # game_part like "8-Game" or "Hold'em No Limit"
                hand.game_type = game_part
                try:
                    hand.stakes = (0.0, 0.0)  # Stakes not in header for Winamax
                except ValueError:
                    pass
            continue
        
        # Parse table line: "Table: 'Lyon' (real money) Seat #3 is the button"
        if line.startswith('Table:'):
            # Extract table name
            match = re.search(r"Table:\s*'([^']+)'", line)
            if match:
                hand.table_name = match.group(1)
            # Extract button position
            match = re.search(r"Seat\s+#(\d+)\s+is the button", line)
            if match:
                hand.button_position = int(match.group(1))
            continue
        
        # Parse seats: "Seat 1: JohnDoe (150.00€)"
        if line.startswith('Seat '):
            match = re.search(r"Seat\s+(\d+):\s+([^()]+)\s*\(([^)]+)\)", line)
            if match:
                seat = int(match.group(1))
                name = match.group(2).strip()
                stack_str = match.group(3)
                stack = _parse_currency_amount(stack_str)
                player = PlayerInfo(name=name, seat=seat, stack=stack)
                hand.players.append(player)
            continue
        
        # Parse hole cards: "Dealt to JohnDoe [As Kh]"
        if 'Dealt to' in line:
            match = re.search(r"Dealt to\s+(\S+)\s+\[([^\]]+)\]", line)
            if match:
                player_name = match.group(1)
                cards_str = match.group(2)
                hole_cards = _parse_hole_cards(cards_str)
                # Find player and set hole cards
                for p in hand.players:
                    if p.name == player_name:
                        p.hole_cards = hole_cards
                        hand.hero_name = player_name
                        break
            continue
        
        # Parse street markers
        if '*** HOLE CARDS ***' in line or '*** PREFLOP ***' in line:
            current_street = 'preflop'
            if 'preflop' not in hand.actions:
                hand.actions['preflop'] = []
        elif '*** FLOP ***' in line:
            current_street = 'flop'
            # Extract flop cards: "*** FLOP *** [7d 8c 9h]"
            match = re.search(r"\[([^\]]+)\]", line)
            if match:
                flop_str = match.group(1)
                for card in flop_str.split():
                    parsed = _parse_card(card)
                    if parsed:
                        hand.board.append(parsed)
            if 'flop' not in hand.actions:
                hand.actions['flop'] = []
        elif '*** TURN ***' in line:
            current_street = 'turn'
            # Extract turn card: "*** TURN *** [7d 8c 9h] [2s]"
            match = re.findall(r"\[([^\]]+)\]", line)
            if len(match) >= 2:
                # Second bracket is the turn card
                turn_card = _parse_card(match[1])
                if turn_card:
                    hand.board.append(turn_card)
            if 'turn' not in hand.actions:
                hand.actions['turn'] = []
        elif '*** RIVER ***' in line:
            current_street = 'river'
            # Extract river card
            match = re.findall(r"\[([^\]]+)\]", line)
            if len(match) >= 2:
                river_card = _parse_card(match[1])
                if river_card:
                    hand.board.append(river_card)
            if 'river' not in hand.actions:
                hand.actions['river'] = []
        elif '*** SHOWDOWN ***' in line:
            current_street = 'showdown'
            if 'showdown' not in hand.actions:
                hand.actions['showdown'] = []
        
        # Parse actions during betting rounds
        # Examples:
        # "JohnDoe: folds"
        # "JohnDoe: checks"
        # "JohnDoe: calls 10.00"
        # "JohnDoe: bets 20.00"
        # "JohnDoe: raises to 40.00"
        # "JohnDoe: allin 100.00"
        action_patterns = [
            (r"(\S+):\s+folds", 'fold', None),
            (r"(\S+):\s+checks", 'check', None),
            (r"(\S+):\s+calls\s+([\d,.\s€$]+)", 'call', None),
            (r"(\S+):\s+bets\s+([\d,.\s€$]+)", 'bet', None),
            (r"(\S+):\s+raises\s+to\s+([\d,.\s€$]+)", 'raise', None),
            (r"(\S+):\s+all[- ]?in\s+([\d,.\s€$]+)", 'allin', None),
            (r"(\S+):\s+all[- ]?in", 'allin', None),
        ]
        
        for pattern, action_type, _ in action_patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                player = match.group(1)
                amount = None
                if len(match.groups()) > 1:
                    try:
                        amount = _parse_currency_amount(match.group(2))
                    except (ValueError, IndexError):
                        amount = None
                action = Action(player=player, action=action_type, amount=amount, street=current_street)
                if current_street in hand.actions:
                    hand.actions[current_street].append(action)
                break
        
        # Parse showdown results: "JohnDoe: shows [As Kh] (straight 5-9)"
        if 'shows' in line and '[' in line and ']' in line:
            match = re.search(r"(\S+):\s+shows\s+\[([^\]]+)\]", line)
            if match:
                player = match.group(1)
                # Cards shown - we could track these too
            continue
        
        # Parse winner: "JohnDoe wins 45.00€"
        if 'wins' in line:
            match = re.search(r"(\S+)\s+wins\s+([\d,.\s]+)", line, re.IGNORECASE)
            if match:
                winner = match.group(1)
                amount = _parse_currency_amount(match.group(2))
                hand.winners.append((winner, amount))
            continue
        
        # Parse summary: "Pot: 45.00€ | Rake: 0.45€"
        if line.startswith('Pot:'):
            match = re.search(r"Pot:\s*([\d,.\s]+)", line)
            if match:
                hand.pot = _parse_currency_amount(match.group(1))
            match = re.search(r"Rake:\s*([\d,.\s]+)", line)
            if match:
                hand.rake = _parse_currency_amount(match.group(1))
            continue
        
        # Parse board in summary: "Board: 7d 8c 9h 2s 3d"
        if line.startswith('Board:'):
            board_str = line.replace('Board:', '').strip()
            # If board is not yet fully populated, parse it
            if len(hand.board) == 0:
                for card in board_str.split():
                    parsed = _parse_card(card)
                    if parsed:
                        hand.board.append(parsed)
            continue
        
        # Generate hand_id from table name and line content if not found
        if not hand.hand_id and hand.table_name:
            hand.hand_id = f"{hand.table_name}_{hash(text[:100])}"
    
    # Ensure all streets exist in actions
    for street in ['preflop', 'flop', 'turn', 'river', 'showdown']:
        if street not in hand.actions:
            hand.actions[street] = []
    
    # Set max_seats based on number of players
    if hand.players:
        hand.max_seats = max(len(hand.players), hand.max_seats)
    
    # Generate hand_id if still empty
    if not hand.hand_id:
        hand.hand_id = f"winamax_{hash(text)}"

    return hand


# ----------------------------------------------------------------------
# PokerStars Parser
# ----------------------------------------------------------------------

def _parse_card_ps(card_str: str) -> str:
    """Parse a card string like 'As', 'Kh', '10d' for PokerStars."""
    card_str = card_str.strip()
    if len(card_str) < 2:
        return ''
    rank = card_str[0].upper()
    if rank == '1' and card_str.startswith('10'):
        rank = 'T'
    suit = card_str[-1].lower()
    if rank in ['2', '3', '4', '5', '6', '7', '8', '9', 'T', 'J', 'Q', 'K', 'A'] and suit in ['h', 'd', 'c', 's']:
        return f"{rank}{suit}"
    return ''


def parse_pokerstars_hh(text: str) -> ParsedHand:
    """Parse PokerStars hand history text into ParsedHand structure.

    PokerStars format uses:
    - '*** HOLE CARDS ***' (with spaces)
    - '*** FLOP *** [Ad Kd Qh]'
    - '*** TURN *** [Ad Kd Qh] [8s]'
    - '*** RIVER *** [Ad Kd Qh 8s] [2c]'
    - Table: "Table 'Asteria' 6-max Seat #3 is the button"
    - Seats: "Seat 1: player (200.00 in chips)"
    """
    lines = text.strip().split('\n')
    hand = ParsedHand(raw_text=text, site='pokerstars')

    current_street = 'preflop'

    for i, line in enumerate(lines):
        line = line.strip()

        # Parse header: PokerStars Hand #123456789: Hold'em No Limit (0.01/0.02)
        if line.startswith('PokerStars Hand #'):
            match = re.search(r'Hand #(\d+):', line)
            if match:
                hand.hand_id = match.group(1)
            # Extract game type
            if "No Limit" in line:
                hand.limit_type = "No Limit"
            elif "Pot Limit" in line:
                hand.limit_type = "Pot Limit"
            if "Hold'em" in line:
                hand.game_type = "No Limit Hold'em"
            elif "Omaha" in line:
                hand.game_type = "Pot Limit Omaha"
            # Extract stakes
            stakes_match = re.search(r'\(([\d.]+)/([\d.]+)\)', line)
            if stakes_match:
                hand.stakes = (float(stakes_match.group(1)), float(stakes_match.group(2)))
            continue

        # Parse table line
        if line.startswith("Table '"):
            match = re.search(r"Table '([^']+)'\s+(\d+)-max", line)
            if match:
                hand.table_name = match.group(1)
                hand.max_seats = int(match.group(2))
            match = re.search(r"Seat #(\d+) is the button", line)
            if match:
                hand.button_position = int(match.group(1))
            continue

        # Parse seats
        if line.startswith('Seat '):
            match = re.search(r'Seat (\d+):\s+(\S+)\s+\(([\d.]+)', line)
            if match:
                seat = int(match.group(1))
                name = match.group(2)
                stack = float(match.group(3))
                hand.players.append(Player(name=name, seat=seat, stack=stack))
            continue

        # Parse hole cards
        if '*** HOLE CARDS ***' in line:
            current_street = 'preflop'
            if 'preflop' not in hand.actions:
                hand.actions['preflop'] = []
            continue

        if 'Dealt to' in line:
            match = re.search(r'Dealt to\s+(\S+)\s+\[([^\]]+)\]', line)
            if match:
                player_name = match.group(1)
                cards_str = match.group(2)
                hole_cards = [c.strip() for c in cards_str.split()]
                for p in hand.players:
                    if p.name == player_name:
                        p.hole_cards = hole_cards
                        hand.hero_name = player_name
                        break
            continue

        # Parse street markers
        if '*** FLOP ***' in line:
            current_street = 'flop'
            if 'flop' not in hand.actions:
                hand.actions['flop'] = []
            match = re.search(r'\[([^\]]+)\]', line)
            if match:
                flop_str = match.group(1)
                for card in flop_str.split():
                    parsed = _parse_card_ps(card)
                    if parsed:
                        hand.board.append(parsed)
            continue

        if '*** TURN ***' in line:
            current_street = 'turn'
            if 'turn' not in hand.actions:
                hand.actions['turn'] = []
            match = re.findall(r'\[([^\]]+)\]', line)
            if len(match) >= 2:
                turn_card = _parse_card_ps(match[1])
                if turn_card:
                    hand.board.append(turn_card)
            continue

        if '*** RIVER ***' in line:
            current_street = 'river'
            if 'river' not in hand.actions:
                hand.actions['river'] = []
            match = re.findall(r'\[([^\]]+)\]', line)
            if len(match) >= 2:
                river_card = _parse_card_ps(match[-1])
                if river_card:
                    hand.board.append(river_card)
            continue

        if '*** SHOWDOWN ***' in line:
            current_street = 'showdown'
            if 'showdown' not in hand.actions:
                hand.actions['showdown'] = []
            continue

        # Parse actions — strip currency symbols for robust matching
        line_clean = line.replace('$', '').replace('€', '')
        action_patterns = [
            (r'(\S+):\s+folds', 'fold', None),
            (r'(\S+):\s+checks', 'check', None),
            (r'(\S+):\s+calls\s+([\d.]+)', 'call', None),
            (r'(\S+):\s+bets\s+([\d.]+)', 'bet', None),
            (r'(\S+):\s+raises\s+[\d.]+\s+to\s+([\d.]+)', 'raise', None),  # "raises X to Y" (PS format)
            (r'(\S+):\s+raises\s+to\s+([\d.]+)', 'raise', None),          # "raises to X" (Winamax format)
            (r'(\S+):\s+all[- ]?in\s+([\d.]+)', 'allin', None),
            (r'(\S+):\s+all[- ]?in', 'allin', None),
        ]

        for pattern, action_type, _ in action_patterns:
            match = re.search(pattern, line_clean, re.IGNORECASE)
            if match:
                player = match.group(1)
                amount = None
                if len(match.groups()) > 1:
                    try:
                        amount = float(match.group(2))
                    except (ValueError, IndexError):
                        amount = None
                act = Action(player=player, action=action_type, amount=amount, street=current_street)
                if current_street in hand.actions:
                    hand.actions[current_street].append(act)
                break

        # Parse winners
        if 'wins' in line:
            match = re.search(r'(\S+)\s+wins\s+([\d.]+)', line_clean, re.IGNORECASE)
            if match:
                winner = match.group(1)
                amount = float(match.group(2))
                hand.winners.append((winner, amount))
            continue

        # Parse summary
        if 'Total pot' in line:
            match = re.search(r'Total pot\s+([\d.]+)', line)
            if match:
                hand.pot = float(match.group(1))
            match = re.search(r'Rake\s+([\d.]+)', line)
            if match:
                hand.rake = float(match.group(1))
            continue

        # Parse board from summary if not complete
        if line.startswith('Board:'):
            board_str = line.replace('Board:', '').strip()
            if len(hand.board) == 0:
                for card in board_str.split():
                    parsed = _parse_card_ps(card)
                    if parsed:
                        hand.board.append(parsed)
            continue

    # Ensure all streets exist
    for street in ['preflop', 'flop', 'turn', 'river', 'showdown']:
        if street not in hand.actions:
            hand.actions[street] = []

    return hand


# ----------------------------------------------------------------------
# GGPoker Parser
# ----------------------------------------------------------------------

def parse_ggpoker_hh(text: str) -> ParsedHand:
    """Parse GGPoker hand history text into ParsedHand structure.

    GGPoker format differences from PokerStars:
    - Uses '***HOLECARDS***' (no spaces) instead of '*** HOLE CARDS ***'
    - Uses '***FLOP***', '***TURN***', '***RIVER***' (no spaces)
    - Table line: "Table: 'Taverner' 6-max Seat #3 is the button"
    - Seat line: "Seat 1: PlayerA (€200.00)"
    - Card format: [Ah|Kd] (pipe separator in some cases)
    - Different header format with currency symbols like €
    """
    lines = text.strip().split('\n')
    hand = ParsedHand(raw_text=text, site='ggpoker')

    current_street = 'preflop'

    for i, line in enumerate(lines):
        line = line.strip()

        # Parse header: GGPoker Hand #123456789: Hold'em No Limit (€1.00/€2.00)
        if 'Hand #' in line and ':' in line:
            match = re.search(r'Hand #(\d+)', line)
            if match:
                hand.hand_id = match.group(1)
            # Extract game type
            if "No Limit" in line:
                hand.limit_type = "No Limit"
            elif "Pot Limit" in line:
                hand.limit_type = "Pot Limit"
            if "Hold'em" in line:
                hand.game_type = "No Limit Hold'em"
            elif "Omaha" in line:
                hand.game_type = "Pot Limit Omaha"
            # Extract stakes with currency symbol handling
            stakes_match = re.search(r'\(([^)]+)\)', line)
            if stakes_match:
                stakes_str = stakes_match.group(1)
                # Remove currency symbols and parse
                numbers_match = re.search(r'([\d.]+)/([\d.]+)', stakes_str.replace('€', '').replace('$', ''))
                if numbers_match:
                    hand.stakes = (float(numbers_match.group(1)), float(numbers_match.group(2)))
            continue

        # Parse table line (different format from PokerStars)
        if line.startswith("Table:") or (line.startswith("Table '")):
            # GGPoker format: "Table: 'Taverner' 6-max Seat #3 is the button"
            if line.startswith("Table:"):
                match = re.search(r"Table:\s*'([^']+)'\s+(\d+)-max", line)
            else:
                match = re.search(r"Table\s+'([^']+)'\s+(\d+)-max", line)
            if match:
                hand.table_name = match.group(1)
                hand.max_seats = int(match.group(2))
            match = re.search(r"Seat\s+#(\d+)\s+is the button", line)
            if match:
                hand.button_position = int(match.group(1))
            continue

        # Parse seats
        if line.startswith('Seat '):
            # GGPoker format: "Seat 1: PlayerA (€200.00)" or "Seat 1: PlayerA (200.00)"
            match = re.search(r'Seat\s+(\d+):\s+(\S+)\s+\(([^)]+)\)', line)
            if match:
                seat = int(match.group(1))
                name = match.group(2)
                stack_str = match.group(3).replace('€', '').replace('$', '').strip()
                try:
                    stack = float(stack_str)
                except ValueError:
                    stack = 0.0
                hand.players.append(Player(name=name, seat=seat, stack=stack))
            continue

        # Parse hole cards - GGPoker uses ***HOLECARDS*** (no spaces)
        if '***HOLECARDS***' in line:
            current_street = 'preflop'
            if 'preflop' not in hand.actions:
                hand.actions['preflop'] = []
            continue

        if 'Dealt to' in line:
            # Format: "Dealt to PlayerA [Ah Kd]" or "Dealt to PlayerA [Ah|Kd]"
            match = re.search(r'Dealt to\s+(\S+)\s+\[([^\]]+)\]', line)
            if match:
                player_name = match.group(1)
                cards_str = match.group(2).replace('|', ' ')  # Handle pipe separator
                hole_cards = [c.strip() for c in cards_str.split()]
                for p in hand.players:
                    if p.name == player_name:
                        p.hole_cards = hole_cards
                        hand.hero_name = player_name
                        break
            continue

        # Parse street markers (no spaces in GGPoker)
        if '***FLOP***' in line:
            current_street = 'flop'
            if 'flop' not in hand.actions:
                hand.actions['flop'] = []
            match = re.search(r'\[([^\]]+)\]', line)
            if match:
                flop_str = match.group(1).replace('|', ' ')
                for card in flop_str.split():
                    parsed = _parse_card_ps(card)
                    if parsed:
                        hand.board.append(parsed)
            continue

        if '***TURN***' in line:
            current_street = 'turn'
            if 'turn' not in hand.actions:
                hand.actions['turn'] = []
            match = re.findall(r'\[([^\]]+)\]', line)
            if len(match) >= 2:
                turn_card = _parse_card_ps(match[1].replace('|', ' '))
                if turn_card:
                    hand.board.append(turn_card)
            continue

        if '***RIVER***' in line:
            current_street = 'river'
            if 'river' not in hand.actions:
                hand.actions['river'] = []
            match = re.findall(r'\[([^\]]+)\]', line)
            if len(match) >= 2:
                river_card = _parse_card_ps(match[-1].replace('|', ' '))
                if river_card:
                    hand.board.append(river_card)
            continue

        if '***SHOWDOWN***' in line:
            current_street = 'showdown'
            if 'showdown' not in hand.actions:
                hand.actions['showdown'] = []
            continue

        # Parse actions — strip currency symbols for robust matching
        line_clean = line.replace('$', '').replace('€', '')
        action_patterns = [
            (r'(\S+):\s*folds', 'fold', None),
            (r'(\S+):\s*checks', 'check', None),
            (r'(\S+):\s*calls\s+([\d.]+)', 'call', None),
            (r'(\S+):\s*bets\s+([\d.]+)', 'bet', None),
            (r'(\S+):\s*raises\s+[\d.]+\s+to\s+([\d.]+)', 'raise', None),  # "raises X to Y" (GG format)
            (r'(\S+):\s*raises\s+(?:to\s+)?([\d.]+)', 'raise', None),      # "raises X" or "raises to X"
            (r'(\S+):\s*all[- ]?in\s+([\d.]+)', 'allin', None),
            (r'(\S+):\s*all[- ]?in', 'allin', None),
        ]

        for pattern, action_type, _ in action_patterns:
            match = re.search(pattern, line_clean, re.IGNORECASE)
            if match:
                player = match.group(1)
                amount = None
                if len(match.groups()) > 1:
                    try:
                        amount = float(match.group(2))
                    except (ValueError, IndexError):
                        amount = None
                act = Action(player=player, action=action_type, amount=amount, street=current_street)
                if current_street in hand.actions:
                    hand.actions[current_street].append(act)
                break

        # Parse winners — GGPoker uses "Player collected $X" format
        if 'collected' in line:
            match = re.search(r'(\S+)\s+collected\s+([\d.]+)', line_clean, re.IGNORECASE)
            if match:
                winner = match.group(1)
                amount = float(match.group(2))
                hand.winners.append((winner, amount))
            continue

        # Parse summary
        if 'Total Pot' in line or 'Total pot' in line:
            line_clean = line.replace('$', '').replace('€', '')
            match = re.search(r'([\d.]+)', line_clean.split('Total')[-1])
            if match:
                hand.pot = float(match.group(1))
            match = re.search(r'Rake[\s:]+([\d.]+)', line_clean)
            if match:
                hand.rake = float(match.group(1))
            continue

    # Ensure all streets exist
    for street in ['preflop', 'flop', 'turn', 'river', 'showdown']:
        if street not in hand.actions:
            hand.actions[street] = []

    return hand


# ----------------------------------------------------------------------
# Format Detection and Auto-parse
# ----------------------------------------------------------------------

def detect_format(text: str) -> Optional[str]:
    """Detect the hand history format from text.

    Returns:
        'pokerstars', 'winamax', 'ggpoker', or None if unknown
    """
    text_lower = text.lower()
    if 'winamax' in text_lower:
        return 'winamax'
    if 'pokerstars' in text_lower:
        return 'pokerstars'
    if 'ggpoker' in text_lower or 'gg poker' in text_lower:
        return 'ggpoker'
    # Fallback: check for format-specific markers
    if '***HOLECARDS***' in text or '***FLOP***' in text:
        return 'ggpoker'
    if '*** HOLE CARDS ***' in text:
        return 'pokerstars'
    return None


def parse_hand(text: str) -> ParsedHand:
    """Auto-detect format and parse hand history.

    Attempts to detect whether the hand is from Winamax, PokerStars, or GGPoker
    based on format markers, then calls the appropriate parser.

    Args:
        text: Raw hand history text

    Returns:
        ParsedHand dataclass with all parsed fields

    Raises:
        ValueError: If the format cannot be detected or parsed
    """
    fmt = detect_format(text)

    if fmt == 'winamax':
        return parse_winamax_hh(text)
    elif fmt == 'pokerstars':
        return parse_pokerstars_hh(text)
    elif fmt == 'ggpoker':
        return parse_ggpoker_hh(text)

    raise ValueError("Unknown hand history format. Could not detect site from text.")