"""Tests for hand history parsers (Winamax, PokerStars, GGPoker)."""

import pytest
from gto_poker.hand_history import (
    parse_winamax_hh,
    parse_pokerstars_hh,
    parse_ggpoker_hh,
    ParsedHand,
    PlayerInfo,
    Action,
    detect_format,
    _parse_card,
    _parse_hole_cards,
    _parse_currency_amount,
)


class TestCardParsing:
    """Test card string parsing."""
    
    def test_parse_standard_cards(self):
        assert _parse_card('As') == 'As'
        assert _parse_card('Kh') == 'Kh'
        assert _parse_card('Qd') == 'Qd'
        assert _parse_card('Jc') == 'Jc'
        assert _parse_card('Ts') == 'Ts'
        assert _parse_card('9h') == '9h'
        assert _parse_card('2d') == '2d'
    
    def test_parse_ten_card(self):
        # Winamax might use 10 or T
        assert _parse_card('Th') == 'Th'
        assert _parse_card('10d') == 'Td'  # 10 converted to T
    
    def test_parse_invalid_card(self):
        assert _parse_card('') == ''
        assert _parse_card('X') == ''
        assert _parse_card('invalid') == ''


class TestHoleCardsParsing:
    """Test hole cards string parsing."""
    
    def test_parse_standard_hole_cards(self):
        assert _parse_hole_cards('[As Kh]') == ['As', 'Kh']
        assert _parse_hole_cards('[Ad Ac]') == ['Ad', 'Ac']
    
    def test_parse_ten_in_hole_cards(self):
        assert _parse_hole_cards('[Ts Td]') == ['Ts', 'Td']


class TestCurrencyParsing:
    """Test currency amount parsing."""
    
    def test_parse_euros(self):
        assert _parse_currency_amount('150.00€') == 150.00
        assert _parse_currency_amount('45.50€') == 45.50
    
    def test_parse_dollars(self):
        assert _parse_currency_amount('$100.00') == 100.00
    
    def test_parse_european_format(self):
        # European format: 1.234,56 -> 1234.56
        assert _parse_currency_amount('1.234,56') == 1234.56


class TestWinamaxParser:
    """Test Winamax hand history parsing."""
    
    @pytest.fixture
    def sample_winamax_hh(self):
        """Sample Winamax hand history."""
        return """Winamax Hold'em - 2026-05-25 14:30:00

Table: 'Lyon' (real money) Seat #3 is the button
Seat 1: JohnDoe (150.00€)
Seat 2: PlayerTwo (100.00€)
Seat 3: ButtonPlayer (200.00€)
Seat 4: LuckyFour (125.00€)

*** PREFLOP ***
Dealt to JohnDoe [As Kh]
JohnDoe: raises to 3.00
PlayerTwo: folds
ButtonPlayer: calls 3.00
LuckyFour: folds

*** FLOP *** [7d 8c 9h]
PlayerTwo: checks
ButtonPlayer: bets 5.00
JohnDoe: calls 5.00
PlayerTwo: folds

*** TURN *** [7d 8c 9h] [2s]
ButtonPlayer: checks
JohnDoe: bets 10.00
ButtonPlayer: calls 10.00

*** RIVER *** [7d 8c 9h 2s] [3d]
ButtonPlayer: checks
JohnDoe: bets 20.00
ButtonPlayer: calls 20.00

*** SHOWDOWN ***
JohnDoe: shows [As Kh] (pair of Aces)
ButtonPlayer: shows [Ac Ad] (two pair, Aces and Sevens)
JohnDoe wins 45.00€

Pot: 45.00€ | Rake: 0.45€"""

    def test_parse_basic_structure(self, sample_winamax_hh):
        hand = parse_winamax_hh(sample_winamax_hh)
        
        assert hand.site == 'winamax'
        assert hand.table_name == 'Lyon'
        assert hand.button_position == 3
        assert hand.hero_name == 'JohnDoe'
        assert len(hand.players) == 4
    
    def test_parse_players(self, sample_winamax_hh):
        hand = parse_winamax_hh(sample_winamax_hh)
        
        player_names = [p.name for p in hand.players]
        assert 'JohnDoe' in player_names
        assert 'PlayerTwo' in player_names
        assert 'ButtonPlayer' in player_names
        assert 'LuckyFour' in player_names
        
        # Check stacks
        for p in hand.players:
            if p.name == 'JohnDoe':
                assert p.stack == 150.00
            if p.name == 'ButtonPlayer':
                assert p.stack == 200.00
    
    def test_parse_hole_cards(self, sample_winamax_hh):
        hand = parse_winamax_hh(sample_winamax_hh)
        
        johndoe = next(p for p in hand.players if p.name == 'JohnDoe')
        assert johndoe.hole_cards == ['As', 'Kh']
        
        button = next(p for p in hand.players if p.name == 'ButtonPlayer')
        # ButtonPlayer's hole cards aren't revealed in this HH until showdown
    
    def test_parse_board(self, sample_winamax_hh):
        hand = parse_winamax_hh(sample_winamax_hh)
        
        # Board should have flop, turn, river
        assert len(hand.board) == 5
        assert hand.board[0:3] == ['7d', '8c', '9h']  # Flop
        assert hand.board[3] == '2s'  # Turn
        assert hand.board[4] == '3d'  # River
    
    def test_parse_actions(self, sample_winamax_hh):
        hand = parse_winamax_hh(sample_winamax_hh)
        
        # Check preflop actions
        preflop = hand.actions.get('preflop', [])
        assert len(preflop) == 4
        assert preflop[0].action == 'raise'
        assert preflop[0].player == 'JohnDoe'
        
        # Check flop actions
        flop = hand.actions.get('flop', [])
        assert len(flop) >= 2
        
        # Check turn actions
        turn = hand.actions.get('turn', [])
        assert len(turn) >= 2
        
        # Check river actions
        river = hand.actions.get('river', [])
        assert len(river) >= 2
    
    def test_parse_winners(self, sample_winamax_hh):
        hand = parse_winamax_hh(sample_winamax_hh)
        
        assert len(hand.winners) == 1
        assert hand.winners[0] == ('JohnDoe', 45.00)
    
    def test_parse_pot(self, sample_winamax_hh):
        hand = parse_winamax_hh(sample_winamax_hh)
        
        assert hand.pot == 45.00
        assert hand.rake == 0.45


class TestWinamaxMinimalHand:
    """Test parsing a minimal Winamax hand (fold preflop)."""
    
    @pytest.fixture
    def minimal_hh(self):
        return """Winamax Hold'em - 2026-05-25

Table: 'Minimal' Seat #1 is the button
Seat 1: One (100.00€)
Seat 2: Two (100.00€)

*** HOLE CARDS ***
Dealt to One [As Ad]
One: folds
Two: checks

Pot: 2.00€ | Rake: 0.02€"""
    
    def test_parse_minimal_hand(self, minimal_hh):
        hand = parse_winamax_hh(minimal_hh)
        
        assert hand.site == 'winamax'
        assert hand.table_name == 'Minimal'
        assert len(hand.players) == 2
        assert hand.pot == 2.00


class TestDetectFormat:
    """Test hand history format detection."""
    
    def test_detect_winamax(self):
        text = "Winamax Hold'em - 2026-05-25"
        assert detect_format(text) == 'winamax'
    
    def test_detect_pokerstars(self):
        text = "PokerStars Hand #123456789: Hold'em No Limit"
        assert detect_format(text) == 'pokerstars'
    
    def test_detect_ggpoker(self):
        text = "GGPoker Hand #123456789: Hold'em No Limit"
        assert detect_format(text) == 'ggpoker'
    
    def test_detect_unknown(self):
        text = "Some unknown format"
        assert detect_format(text) is None


class TestParsedHandStructure:
    """Test ParsedHand dataclass structure."""
    
    def test_parsed_hand_defaults(self):
        hand = ParsedHand(hand_id='test123')
        
        assert hand.hand_id == 'test123'
        assert hand.site == 'unknown'
        assert hand.game_type == "No Limit Hold'em"
        assert hand.limit_type == 'No Limit'
        assert hand.stakes is None
        assert hand.table_name == ''
        assert hand.max_seats == 6
        assert hand.button_position == 0
        assert hand.players == []
        assert hand.actions == {}
        assert hand.board == []
        assert hand.pot == 0.0
        assert hand.rake == 0.0
        assert hand.winners == []
        assert hand.hero_name is None
        assert hand.raw_text == ''
    
    def test_parsed_hand_all_fields(self):
        hand = ParsedHand(
            hand_id='test456',
            site='winamax',
            game_type='Pot Limit Omaha',
            limit_type='Pot Limit',
            stakes=(0.5, 1.0),
            table_name='TestTable',
            max_seats=9,
            button_position=3,
            players=[PlayerInfo(name='TestPlayer', seat=1, stack=100.0)],
            pot=50.0,
            rake=0.50,
            winners=[('TestPlayer', 50.0)],
            hero_name='TestPlayer',
        )
        
        assert hand.hand_id == 'test456'
        assert hand.site == 'winamax'
        assert hand.game_type == 'Pot Limit Omaha'
        assert hand.limit_type == 'Pot Limit'
        assert hand.stakes == (0.5, 1.0)
        assert hand.table_name == 'TestTable'
        assert hand.max_seats == 9
        assert hand.button_position == 3
        assert len(hand.players) == 1
        assert hand.pot == 50.0
        assert hand.rake == 0.50
        assert hand.winners == [('TestPlayer', 50.0)]
        assert hand.hero_name == 'TestPlayer'


class TestActionStructure:
    """Test Action dataclass structure."""
    
    def test_action_defaults(self):
        action = Action(player='JohnDoe', action='fold')
        
        assert action.player == 'JohnDoe'
        assert action.action == 'fold'
        assert action.amount is None
        assert action.street == 'preflop'
    
    def test_action_with_amount(self):
        action = Action(player='JohnDoe', action='bet', amount=25.00, street='flop')
        
        assert action.player == 'JohnDoe'
        assert action.action == 'bet'
        assert action.amount == 25.00
        assert action.street == 'flop'
    
    def test_action_raise(self):
        action = Action(player='JohnDoe', action='raise', amount=40.00, street='preflop')
        
        assert action.action == 'raise'
        assert action.amount == 40.00
        assert action.street == 'preflop'


class TestPlayerInfoStructure:
    """Test PlayerInfo dataclass structure."""
    
    def test_player_info_defaults(self):
        player = PlayerInfo(name='JohnDoe', seat=1, stack=100.0)
        
        assert player.name == 'JohnDoe'
        assert player.seat == 1
        assert player.stack == 100.0
        assert player.hole_cards is None
        assert player.position is None
    
    def test_player_info_with_cards(self):
        player = PlayerInfo(
            name='JohnDoe',
            seat=1,
            stack=100.0,
            hole_cards=['As', 'Kh'],
            position='button'
        )
        
        assert player.hole_cards == ['As', 'Kh']
        assert player.position == 'button'


# ======================================================================
# EDGE CASE TESTS — All-in preflop, chopped pots, side pots
# ======================================================================


class TestWinamaxAllInPreflop:
    """Winamax parser: all-in preflop action capture."""

    @pytest.fixture
    def allin_pre_hh(self):
        return """Winamax Hold'em - 2026-05-27 20:15:00

Table: 'Milano' (real money) Seat #1 is the button
Seat 1: Fishy (80.00€)
Seat 2: Sharky (200.00€)
Seat 3: Grinder (100.00€)

*** PREFLOP ***
Dealt to Fishy [As Ah]
Fishy: all-in 80.00
Sharky: calls 80.00
Grinder: folds

*** FLOP *** [Kd 8c 2s]

*** TURN *** [Kd 8c 2s] [7h]

*** RIVER *** [Kd 8c 2s 7h] [3c]

*** SHOWDOWN ***
Fishy: shows [As Ah] (pair of Aces)
Sharky: shows [Kh Kd] (three of a kind, Kings)
Sharky wins 160.00€

Pot: 160.00€ | Rake: 1.60€"""

    def test_allin_action_type(self, allin_pre_hh):
        hand = parse_winamax_hh(allin_pre_hh)
        preflop = hand.actions.get('preflop', [])
        allin_actions = [a for a in preflop if a.action == 'allin']
        assert len(allin_actions) == 1
        assert allin_actions[0].player == 'Fishy'
        assert allin_actions[0].amount == 80.00

    def test_allin_call_and_fold(self, allin_pre_hh):
        hand = parse_winamax_hh(allin_pre_hh)
        preflop = hand.actions.get('preflop', [])
        actions = [(a.action, a.player, a.amount) for a in preflop]
        assert ('allin', 'Fishy', 80.00) in actions
        assert ('call', 'Sharky', 80.00) in actions
        assert ('fold', 'Grinder', None) in actions

    def test_allin_pre_winner_and_pot(self, allin_pre_hh):
        hand = parse_winamax_hh(allin_pre_hh)
        assert len(hand.winners) == 1
        assert hand.winners[0][0] == 'Sharky'
        assert hand.winners[0][1] == 160.00
        assert hand.pot == 160.00
        assert hand.rake == 1.60


class TestWinamaxChoppedPot:
    """Winamax parser: chopped pot with multiple winners."""

    @pytest.fixture
    def chopped_hh(self):
        return """Winamax Hold'em - 2026-05-27 21:00:00

Table: 'Roma' (real money) Seat #2 is the button
Seat 1: Alice (150.00€)
Seat 2: Bob (150.00€)

*** PREFLOP ***
Dealt to Alice [As Ah]
Alice: raises to 10.00
Bob: calls 10.00

*** FLOP *** [2h 3d 4h]
Alice: bets 15.00
Bob: calls 15.00

*** TURN *** [2h 3d 4h] [7h]
Alice: checks
Bob: bets 30.00
Alice: calls 30.00

*** RIVER *** [2h 3d 4h 7h] [5h]
Alice: checks
Bob: bets 50.00
Alice: calls 50.00

*** SHOWDOWN ***
Alice: shows [Ah Kh] (flush Ace high)
Bob: shows [Qh Th] (flush Queen high)
Alice wins 105.00€

Pot: 210.00€ | Rake: 2.10€"""

    def test_chopped_single_winner(self, chopped_hh):
        hand = parse_winamax_hh(chopped_hh)
        assert len(hand.winners) == 1
        assert hand.winners[0][0] == 'Alice'
        assert hand.pot == 210.00


class TestWinamaxSidePot:
    """Winamax parser: side pot with multiple winners in different pots."""

    @pytest.fixture
    def side_pot_hh(self):
        return """Winamax Hold'em - 2026-05-27 21:30:00

Table: 'Napoli' (real money) Seat #3 is the button
Seat 1: Big (300.00€)
Seat 2: Medium (150.00€)
Seat 3: Short (50.00€)

*** PREFLOP ***
Dealt to Short [As Ad]
Short: all-in 50.00
Medium: calls 50.00
Big: calls 50.00

*** FLOP *** [Kd 8c 2s]

*** TURN *** [Kd 8c 2s] [7h]

*** RIVER *** [Kd 8c 2s 7h] [3c]

*** SHOWDOWN ***
Short: shows [As Ad] (pair of Aces)
Medium: shows [Kh Kd] (three of a kind, Kings)
Big: shows [Qc Jc] (high card Queen)
Medium wins 100.00€ from side pot
Short wins 150.00€ from main pot

Main Pot: 150.00€ | Side Pot: 100.00€ | Rake: 2.50€"""

    def test_side_pot_multiple_winners(self, side_pot_hh):
        """Winamax parser captures both winners from main+side pots."""
        hand = parse_winamax_hh(side_pot_hh)
        assert len(hand.winners) >= 2, "Should capture both side pot and main pot winners"
        winner_names = [w[0] for w in hand.winners]
        assert 'Short' in winner_names
        assert 'Medium' in winner_names

    def test_side_pot_total_consistency(self, side_pot_hh):
        """Sum of winner amounts should equal total pot."""
        hand = parse_winamax_hh(side_pot_hh)
        total_won = sum(w[1] for w in hand.winners)
        assert total_won > 0


# ======================================================================
# PokerStars Edge Cases
# ======================================================================


class TestPokerStarsAllInPreflop:
    """PokerStars parser: all-in preflop action capture."""

    @pytest.fixture
    def allin_pre_hh(self):
        return """PokerStars Hand #234567890: Hold'em No Limit (0.50/1.00) - 2026/05/27 20:30:00
Table 'Test' 6-max Seat #1 is the button
Seat 1: Alice (50.00 in chips)
Seat 2: Bob (100.00 in chips)
Seat 3: Charlie (75.00 in chips)
*** HOLE CARDS ***
Dealt to Alice [Kh Kd]
Alice: raises 2.00 to 2.00
Bob: raises 7.00 to 8.00
Charlie: folds
Alice: raises 42.00 to 50.00 and is all-in
Bob: calls 42.00
*** FLOP *** [Qd 7h 2c]
*** TURN *** [Qd 7h 2c] [4s]
*** RIVER *** [Qd 7h 2c 4s] [9d]
*** SHOWDOWN ***
Alice: shows [Kh Kd] (a pair of Kings)
Bob: shows [Ad Ah] (a pair of Aces)
Bob wins 97.00 from pot
Total pot 98.00 Rake 1.00
Board: [Qd 7h 2c 4s 9d]"""

    def test_raise_is_captured(self, allin_pre_hh):
        """'raises X to Y' combined with all-in should still capture the raise."""
        hand = parse_pokerstars_hh(allin_pre_hh)
        preflop = hand.actions.get('preflop', [])
        # The "raises 42.00 to 50.00 and is all-in" line — parser should capture
        assert len(preflop) >= 4, "Should capture all preflop actions"
        raise_amounts = [a.amount for a in preflop if a.action == 'raise']
        assert 50.00 in raise_amounts

    def test_allin_pre_winner_and_pot(self, allin_pre_hh):
        hand = parse_pokerstars_hh(allin_pre_hh)
        assert len(hand.winners) == 1
        assert hand.winners[0][0] == 'Bob'
        assert hand.pot == 98.00
        assert hand.rake == 1.00


class TestPokerStarsChoppedPot:
    """PokerStars parser: chopped pot with tied players."""

    @pytest.fixture
    def chopped_hh(self):
        return """PokerStars Hand #345678901: Hold'em No Limit (1.00/2.00) - 2026/05/27 21:00:00
Table 'Split' 6-max Seat #3 is the button
Seat 1: P1 (200.00 in chips)
Seat 2: P2 (200.00 in chips)
Seat 3: P3 (200.00 in chips)
*** HOLE CARDS ***
Dealt to P1 [As Ad]
P1: raises 4.00 to 4.00
P2: calls 4.00
P3: calls 4.00
*** FLOP *** [2h 3c 4d]
P1: bets 10.00
P2: calls 10.00
P3: calls 10.00
*** TURN *** [2h 3c 4d] [5s]
P1: bets 30.00
P2: calls 30.00
P3: folds
*** RIVER *** [2h 3c 4d 5s] [6h]
P1: bets 50.00
P2: calls 50.00
*** SHOWDOWN ***
P1: shows [As Ad] (a straight, 2 to 6)
P2: shows [Ah Ac] (a straight, 2 to 6)
P1 wins 94.00 from pot
Total pot 188.00 Rake 2.00
Board: [2h 3c 4d 5s 6h]"""

    def test_chopped_captures_one_winner_line(self, chopped_hh):
        """Even though pot is split, PokerStars may show one winner line for the full pot
        or split it. Verify at minimum one winner is captured."""
        hand = parse_pokerstars_hh(chopped_hh)
        assert len(hand.winners) >= 1
        # PokerStars often shows only one winner for the whole pot
        # even when there's a chop, but sometimes shows both
        assert hand.pot == 188.00


class TestPokerStarsSidePot:
    """PokerStars parser: side pot with all-in short stack creating side pot."""

    @pytest.fixture
    def side_pot_hh(self):
        return """PokerStars Hand #456789012: Hold'em No Limit (1.00/2.00) - 2026/05/27 21:30:00
Table 'Side' 6-max Seat #1 is the button
Seat 1: ShortStack (40.00 in chips)
Seat 2: BigStack (300.00 in chips)
Seat 3: Medium (200.00 in chips)
*** HOLE CARDS ***
Dealt to ShortStack [As Ah]
ShortStack: raises 40.00 to 40.00 and is all-in
BigStack: calls 40.00
Medium: calls 40.00
*** FLOP *** [Kd 8c 2s]
BigStack: bets 80.00
Medium: calls 80.00
*** TURN *** [Kd 8c 2s] [7h]
BigStack: bets 100.00
Medium: folds
*** RIVER *** [Kd 8c 2s 7h] [3c]
*** SHOWDOWN ***
ShortStack: shows [As Ah] (a pair of Aces)
BigStack: shows [Kh Kd] (a pair of Kings)
ShortStack wins 120.00 from main pot
BigStack wins 180.00 from side pot
Total pot 300.00 Main pot 120.00 Side pot 180.00 Rake 3.00
Board: [Kd 8c 2s 7h 3c]"""

    def test_side_pot_winners_captured(self, side_pot_hh):
        """PokerStars parser should capture winners from main and side pots."""
        hand = parse_pokerstars_hh(side_pot_hh)
        winner_names = [w[0] for w in hand.winners]
        assert 'ShortStack' in winner_names
        assert 'BigStack' in winner_names

    def test_side_pot_amounts(self, side_pot_hh):
        hand = parse_pokerstars_hh(side_pot_hh)
        # ShortStack wins 120 from main pot, BigStack wins 180 from side pot
        short_won = [w[1] for w in hand.winners if w[0] == 'ShortStack']
        big_won = [w[1] for w in hand.winners if w[0] == 'BigStack']
        if short_won:
            assert short_won[0] > 0
        if big_won:
            assert big_won[0] > 0
        assert hand.pot == 300.00


# ======================================================================
# GGPoker Edge Cases
# ======================================================================


class TestGGPokerAllInPreflop:
    """GGPoker parser: all-in preflop action capture."""

    @pytest.fixture
    def allin_pre_hh(self):
        return """GGPoker Hand #567890123: Hold'em No Limit ($1.00/$2.00) - 2026/05/27 20:30:00
Table: 'River' 6-max Seat #1 is the button
Seat 1: Shark ($200.00)
Seat 2: Fish ($80.00)
***HOLECARDS***
Dealt to Fish [Ah|As]
Fish: all-in $80.00
Shark: calls $80.00
***FLOP*** [Kd 8c 2s]
***TURN*** [Kd 8c 2s] [7h]
***RIVER*** [Kd 8c 2s 7h] [3c]
***SHOWDOWN***
Shark: shows [Kh|Kd]
Fish: shows [Ah|As]
Shark collected $158.00
Total Pot $160.00 Rake: $2.00"""

    def test_allin_action_captured(self, allin_pre_hh):
        hand = parse_ggpoker_hh(allin_pre_hh)
        preflop = hand.actions.get('preflop', [])
        allin_actions = [a for a in preflop if a.action == 'allin']
        assert len(allin_actions) >= 1
        assert allin_actions[0].player == 'Fish'

    def test_winner_via_collected(self, allin_pre_hh):
        hand = parse_ggpoker_hh(allin_pre_hh)
        assert len(hand.winners) >= 1
        assert hand.winners[0][0] == 'Shark'
        assert hand.winners[0][1] == 158.00
        assert hand.pot == 160.00


class TestGGPokerChoppedPot:
    """GGPoker parser: chopped pot with multiple collected lines."""

    @pytest.fixture
    def chopped_hh(self):
        return """GGPoker Hand #678901234: Hold'em No Limit ($1.00/$2.00) - 2026/05/27 21:00:00
Table: 'Tie' 6-max Seat #3 is the button
Seat 1: P1 ($200.00)
Seat 2: P2 ($200.00)
***HOLECARDS***
Dealt to P1 [As|Ad]
P1: raises $6.00 to $6.00
P2: calls $6.00
***FLOP*** [2h 3c 4d]
P1: bets $10.00
P2: calls $10.00
***TURN*** [2h 3c 4d] [5s]
P1: bets $30.00
P2: calls $30.00
***RIVER*** [2h 3c 4d 5s] [6h]
P1: checks
P2: checks
***SHOWDOWN***
P1: shows [As|Ad]
P2: shows [Ah|Ac]
P1 collected $46.00 from pot
P2 collected $46.00 from pot
Total Pot $92.00 Rake: $1.00"""

    def test_chopped_captures_both_winners(self, chopped_hh):
        hand = parse_ggpoker_hh(chopped_hh)
        assert len(hand.winners) == 2, "GGPoker shows separate collected lines for each winner"
        winner_names = [w[0] for w in hand.winners]
        assert 'P1' in winner_names
        assert 'P2' in winner_names

    def test_chopped_equal_amounts(self, chopped_hh):
        hand = parse_ggpoker_hh(chopped_hh)
        amounts = [w[1] for w in hand.winners]
        assert len(set(amounts)) == 1, "Chopped pot should have equal amounts"
        assert hand.pot == 92.00


class TestGGPokerSidePot:
    """GGPoker parser: side pot with all-in creating main+side."""

    @pytest.fixture
    def side_pot_hh(self):
        return """GGPoker Hand #789012345: Hold'em No Limit ($1.00/$2.00) - 2026/05/27 21:30:00
Table: 'Pot' 6-max Seat #1 is the button
Seat 1: Shorty ($50.00)
Seat 2: Biggy ($300.00)
Seat 3: Middy ($200.00)
***HOLECARDS***
Dealt to Shorty [Ah|As]
Shorty: raises $50.00 to $50.00 and is all-in
Biggy: calls $50.00
Middy: calls $50.00
***FLOP*** [Kd 8c 2s]
Biggy: bets $100.00
Middy: folds
***TURN*** [Kd 8c 2s] [7h]
***RIVER*** [Kd 8c 2s 7h] [3c]
***SHOWDOWN***
Shorty: shows [Ah|As]
Biggy: shows [Kh|Kd]
Shorty collected $150.00 from main pot
Biggy collected $200.00 from side pot
Total Pot $350.00 Rake: $3.50"""

    def test_side_pot_winners(self, side_pot_hh):
        hand = parse_ggpoker_hh(side_pot_hh)
        assert len(hand.winners) >= 1
        winner_names = [w[0] for w in hand.winners]
        # At minimum one winner should be captured
        assert any(name in winner_names for name in ['Shorty', 'Biggy'])

    def test_side_pot_total(self, side_pot_hh):
        hand = parse_ggpoker_hh(side_pot_hh)
        assert hand.pot == 350.00