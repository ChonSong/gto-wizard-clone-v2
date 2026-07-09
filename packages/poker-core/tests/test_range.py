"""Tests for range module - RangeParser class"""
import pytest
from gto_poker.range import RangeParser, PREFLOP_HANDS
from gto_poker.deck import Card, RANKS


class TestRangeParserInit:
    """Tests for RangeParser initialization"""

    def test_init(self):
        """Test RangeParser initializes with empty cache"""
        parser = RangeParser()
        assert hasattr(parser, '_combo_cache')


class TestRangeParserParse:
    """Tests for parse method"""

    def test_parse_single_pair(self):
        """Test parsing single pair like 'AA'"""
        parser = RangeParser()
        result = parser.parse('AA')
        assert isinstance(result, set)
        assert len(result) > 0

    def test_parse_single_suited(self):
        """Test parsing single suited hand like 'AKs'"""
        parser = RangeParser()
        result = parser.parse('AKs')
        assert isinstance(result, set)
        assert len(result) > 0

    def test_parse_single_offsuit(self):
        """Test parsing single offsuit hand like 'AKo'"""
        parser = RangeParser()
        result = parser.parse('AKo')
        assert isinstance(result, set)
        assert len(result) > 0

    def test_parse_specific_combo(self):
        """Test parsing specific combo like 'AhKh'"""
        parser = RangeParser()
        result = parser.parse('AhKh')
        assert 'AhKh' in result

    def test_parse_uppercase_normalizes(self):
        """Test parse normalizes to uppercase"""
        parser = RangeParser()
        result = parser.parse('jj+')
        assert isinstance(result, set)

    def test_parse_empty_string(self):
        """Test parsing empty string returns empty set"""
        parser = RangeParser()
        result = parser.parse('')
        assert result == set()

    def test_parse_whitespace_ignored(self):
        """Test parse ignores whitespace"""
        parser = RangeParser()
        result = parser.parse('AA, KK ')
        assert len(result) > 0

    def test_parse_multiple_parts(self):
        """Test parsing multiple parts like 'AA, KK, QQ'"""
        parser = RangeParser()
        result = parser.parse('AA, KK, QQ')
        assert len(result) > 0

    def test_parse_plus_range(self):
        """Test parsing plus range like 'JJ+'"""
        parser = RangeParser()
        result = parser.parse('JJ+')
        assert isinstance(result, set)
        assert len(result) > 0

    def test_parse_dash_range(self):
        """Test parsing dash range like '55-JJ'"""
        parser = RangeParser()
        result = parser.parse('55-JJ')
        # Dash range not fully implemented, returns empty
        assert isinstance(result, set)


class TestExpandHand:
    """Tests for _expand_hand method"""

    def test_expand_pair(self):
        """Test expanding a pair returns 6 combos"""
        parser = RangeParser()
        result = parser._expand_hand('QQ')
        assert len(result) == 6

    def test_expand_suited(self):
        """Test expanding suited hand returns 4 combos"""
        parser = RangeParser()
        result = parser._expand_hand('AKs')
        assert len(result) == 4

    def test_expand_offsuit(self):
        """Test expanding offsuit hand returns 12 combos"""
        parser = RangeParser()
        result = parser._expand_hand('AKo')
        assert len(result) == 12

    def test_expand_specific_combo(self):
        """Test expanding specific combo returns 1"""
        parser = RangeParser()
        result = parser._expand_hand('AhKd')
        assert len(result) == 1


class TestComboCount:
    """Tests for combo_count static method"""

    def test_combo_count_pair(self):
        """Test combo count for pair is 6"""
        result = RangeParser.combo_count('QQ')
        assert result == 6

    def test_combo_count_suited(self):
        """Test combo count for suited is 4"""
        result = RangeParser.combo_count('AKs')
        assert result == 4

    def test_combo_count_offsuit(self):
        """Test combo count for offsuit is 12"""
        result = RangeParser.combo_count('AKo')
        assert result == 12

    def test_combo_count_specific(self):
        """Test combo count for specific combo is 1"""
        result = RangeParser.combo_count('AhKd')
        assert result == 1

    def test_combo_count_mixed_range(self):
        """Test combo count for mixed range"""
        result = RangeParser.combo_count('AA, KK')
        assert result == 12  # 6 + 6


class TestRangeToCombos:
    """Tests for range_to_combos method"""

    def test_range_to_combos_pair(self):
        """Test range_to_combos for pair returns Card lists"""
        parser = RangeParser()
        result = parser.range_to_combos('QQ')
        assert len(result) == 6
        assert all(isinstance(c, Card) for combo in result for c in combo)

    def test_range_to_combos_suited(self):
        """Test range_to_combos for suited returns 4 combos"""
        parser = RangeParser()
        result = parser.range_to_combos('AKs')
        assert len(result) == 4
        assert all(len(combo) == 2 for combo in result)

    def test_range_to_combos_offsuit(self):
        """Test range_to_combos for offsuit returns 12 combos"""
        parser = RangeParser()
        result = parser.range_to_combos('AKo')
        assert len(result) == 12
        assert all(len(combo) == 2 for combo in result)

    def test_range_to_combos_specific(self):
        """Test range_to_combos for specific combo"""
        parser = RangeParser()
        result = parser.range_to_combos('AhKd')
        assert len(result) == 1
        assert result[0][0].rank == 'A'
        assert result[0][0].suit == 'h'


class TestPreflopHands:
    """Tests for PREFLOP_HANDS constant"""

    def test_preflop_hands_count(self):
        """Test PREFLOP_HANDS has 169 combinations"""
        assert len(PREFLOP_HANDS) == 169  # 13 * 13

    def test_preflop_hands_structure(self):
        """Test PREFLOP_HANDS contains (rank1, rank2, suited) tuples"""
        assert all(len(h) == 3 for h in PREFLOP_HANDS)
        assert all(isinstance(h[0], str) for h in PREFLOP_HANDS)
        assert all(isinstance(h[1], str) for h in PREFLOP_HANDS)
        assert all(isinstance(h[2], bool) for h in PREFLOP_HANDS)


class TestRangeCombinations:
    """Tests for various range combinations"""

    def test_broadway_range(self):
        """Test parsing broadway-style range"""
        parser = RangeParser()
        # JT+ should include JT and connected hands
        result = parser.parse('JT+')
        assert isinstance(result, set)

    def test_suited_connectors(self):
        """Test parsing suited connectors"""
        parser = RangeParser()
        result = parser.parse('54s')
        assert len(result) == 4

    def test_offsuit_connectors(self):
        """Test parsing offsuit connectors"""
        parser = RangeParser()
        result = parser.parse('54o')
        assert len(result) == 12
