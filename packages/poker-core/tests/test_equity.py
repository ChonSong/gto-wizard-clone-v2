"""Tests for equity module - EquityCalculator class"""
import pytest
from gto_poker.equity import EquityCalculator
from gto_poker.deck import Card


class TestEquityCalculatorInit:
    """Tests for EquityCalculator initialization"""

    def test_init_without_seed(self):
        """Test init without seed"""
        calc = EquityCalculator()
        assert calc.seed is None

    def test_init_with_seed(self):
        """Test init with seed"""
        calc = EquityCalculator(seed=42)
        assert calc.seed == 42


class TestEquityCalculatorParseHand:
    """Tests for _parse_hand method"""

    def test_parse_short_form_pair(self):
        """Test parsing short form pair like 'AA'"""
        calc = EquityCalculator()
        cards = calc._parse_hand('AA')
        assert len(cards) == 2
        assert cards[0].rank == 'A'
        assert cards[1].rank == 'A'

    def test_parse_short_form_suited(self):
        """Test parsing short form suited like 'AhKh'"""
        calc = EquityCalculator()
        cards = calc._parse_hand('AhKh')
        assert len(cards) == 2
        assert cards[0].rank == 'A'
        assert cards[1].rank == 'K'

    def test_parse_short_form_offsuit(self):
        """Test parsing short form offsuit via long form 'AhKd'"""
        calc = EquityCalculator()
        cards = calc._parse_hand('AhKd')
        assert len(cards) == 2
        assert cards[0].rank == 'A'
        assert cards[1].rank == 'K'

    def test_parse_long_form(self):
        """Test parsing long form like 'AhKd'"""
        calc = EquityCalculator()
        cards = calc._parse_hand('AhKd')
        assert len(cards) == 2
        assert cards[0].rank == 'A'
        assert cards[0].suit == 'h'
        assert cards[1].rank == 'K'
        assert cards[1].suit == 'd'

    def test_parse_invalid_raises(self):
        """Test parsing invalid hand string raises"""
        calc = EquityCalculator()
        with pytest.raises(ValueError, match="Invalid hand string"):
            calc._parse_hand('ABC')


class TestCalculateEquityExact:
    """Tests for calculate_equity_exact method"""

    def test_aa_vs_kk_preflop(self):
        """Test AA vs KK preflop equity is approximately correct using Monte Carlo"""
        calc = EquityCalculator(seed=42)
        aa = [Card('A', 's'), Card('A', 'd')]
        kk = [Card('K', 's'), Card('K', 'd')]
        
        # Use Monte Carlo for preflop (5 cards to come is too many for exact)
        result = calc.calculate_equity_monte_carlo(aa, kk, [], iterations=10000)
        equity = result['equity']
        
        # AA vs KK should be around 81%
        assert 0.75 < equity < 0.85

    def test_aa_vs_kk_on_river(self):
        """Test AA vs KK on river (no cards left)"""
        calc = EquityCalculator()
        aa = [Card('A', 's'), Card('A', 'd')]
        kk = [Card('K', 's'), Card('K', 'd')]
        board = [Card('T', 'h'), Card('J', 'd'), Card('Q', 'c'), Card('3', 's'), Card('7', 'h')]
        
        equity = calc.calculate_equity_exact(aa, kk, board)
        
        # On river, should be exact win/loss/tie
        assert equity in [0.0, 0.5, 1.0]

    def test_aa_vs_kk_with_board(self):
        """Test AA vs KK on flop (2 cards to come)"""
        calc = EquityCalculator()
        aa = [Card('A', 's'), Card('A', 'd')]
        kk = [Card('K', 's'), Card('K', 'd')]
        board = [Card('T', 'h'), Card('J', 'd'), Card('Q', 'c')]
        
        equity = calc.calculate_equity_exact(aa, kk, board)
        
        # Flop equity should be around 81%
        assert 0.70 < equity < 0.90

    def test_tie_on_river(self):
        """Test exact tie on river returns 0.5"""
        calc = EquityCalculator()
        # Same hand should tie
        ahkh = [Card('A', 's'), Card('K', 'd')]
        ak = [Card('A', 'd'), Card('K', 's')]
        board = [Card('T', 'h'), Card('J', 'd'), Card('Q', 'c'), Card('3', 's'), Card('7', 'h')]
        
        equity = calc.calculate_equity_exact(ahkh, ak, board)
        assert equity == 0.5

    def test_too_many_cards_raises(self):
        """Test too many remaining cards raises (preflop with 5 cards to come)"""
        calc = EquityCalculator()
        aa = [Card('A', 's'), Card('A', 'd')]
        kk = [Card('K', 's'), Card('K', 'd')]
        
        # Preflop has 5 remaining cards — too many for exact enumeration
        with pytest.raises(ValueError, match="Too many cards"):
            calc.calculate_equity_exact(aa, kk, [])


class TestCalculateEquityMonteCarlo:
    """Tests for calculate_equity_monte_carlo method"""

    def test_monte_carlo_returns_dict(self):
        """Test monte Carlo returns expected dict structure"""
        calc = EquityCalculator(seed=42)
        aa = [Card('A', 's'), Card('A', 'd')]
        kk = [Card('K', 's'), Card('K', 'd')]
        
        result = calc.calculate_equity_monte_carlo(
            hero_cards=aa,
            villain_cards=kk,
            board=[],
            iterations=1000
        )
        
        assert 'equity' in result
        assert 'wins' in result
        assert 'ties' in result
        assert 'total' in result

    def test_monte_carlo_equity_in_range(self):
        """Test monte Carlo equity is between 0 and 1"""
        calc = EquityCalculator(seed=42)
        aa = [Card('A', 's'), Card('A', 'd')]
        kk = [Card('K', 's'), Card('K', 'd')]
        
        result = calc.calculate_equity_monte_carlo(
            hero_cards=aa,
            villain_cards=kk,
            board=[],
            iterations=1000
        )
        
        assert 0.0 <= result['equity'] <= 1.0

    def test_monte_carlo_with_flop(self):
        """Test monte Carlo with flop"""
        calc = EquityCalculator(seed=42)
        aa = [Card('A', 's'), Card('A', 'd')]
        kk = [Card('K', 's'), Card('K', 'd')]
        board = [Card('T', 'h'), Card('J', 'd'), Card('Q', 'c')]
        
        result = calc.calculate_equity_monte_carlo(
            hero_cards=aa,
            villain_cards=kk,
            board=board,
            iterations=1000
        )
        
        assert 0.0 <= result['equity'] <= 1.0
        assert result['total'] > 0

    def test_monte_carlo_with_turn(self):
        """Test monte Carlo with turn"""
        calc = EquityCalculator(seed=42)
        aa = [Card('A', 's'), Card('A', 'd')]
        kk = [Card('K', 's'), Card('K', 'd')]
        board = [Card('T', 'h'), Card('J', 'd'), Card('Q', 'c'), Card('3', 's')]
        
        result = calc.calculate_equity_monte_carlo(
            hero_cards=aa,
            villain_cards=kk,
            board=board,
            iterations=500
        )
        
        assert 0.0 <= result['equity'] <= 1.0

    def test_monte_carlo_with_river(self):
        """Test monte Carlo with river (0 cards to come)"""
        calc = EquityCalculator(seed=42)
        aa = [Card('A', 's'), Card('A', 'd')]
        kk = [Card('K', 's'), Card('K', 'd')]
        board = [Card('T', 'h'), Card('J', 'd'), Card('Q', 'c'), Card('3', 's'), Card('7', 'h')]
        
        result = calc.calculate_equity_monte_carlo(
            hero_cards=aa,
            villain_cards=kk,
            board=board,
            iterations=100
        )
        
        assert 0.0 <= result['equity'] <= 1.0

    def test_monte_carlo_default_iterations(self):
        """Test monte Carlo runs with default iterations"""
        calc = EquityCalculator()
        aa = [Card('A', 's'), Card('A', 'd')]
        kk = [Card('K', 's'), Card('K', 'd')]
        
        result = calc.calculate_equity_monte_carlo(
            hero_cards=aa,
            villain_cards=kk,
            board=[]
        )
        
        assert result['total'] > 0


class TestEquityVsRange:
    """Tests for equity_vs_range method"""

    def test_equity_vs_range_runs(self):
        """Test equity_vs_range runs without error"""
        calc = EquityCalculator(seed=42)
        ahkh = [Card('A', 's'), Card('K', 'd')]
        
        result = calc.equity_vs_range(
            hero_cards=ahkh,
            villain_range=['KK', 'QQ', 'JJ', 'TT'],
            board=[],
            iterations=100
        )
        
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_equity_vs_range_with_board(self):
        """Test equity_vs_range with board"""
        calc = EquityCalculator(seed=42)
        ahkh = [Card('A', 's'), Card('K', 'd')]
        board = [Card('T', 'h'), Card('J', 'd'), Card('Q', 'c')]
        
        result = calc.equity_vs_range(
            hero_cards=ahkh,
            villain_range=['AA', 'KK'],
            board=board,
            iterations=100
        )
        
        assert 0.0 <= result <= 1.0
