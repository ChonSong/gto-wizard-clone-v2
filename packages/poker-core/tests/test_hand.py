"""Tests for hand module - Hand class and HandEvaluator"""
import pytest
from gto_poker.hand import Hand, HandEvaluator, hand_rank_key, HAND_NAMES
from gto_poker.deck import Card


class TestHandCreation:
    """Tests for Hand class creation"""

    def test_hand_with_5_cards(self):
        """Test hand creation with 5 cards"""
        cards = [Card('A', 'h'), Card('K', 'h'), Card('Q', 'h'), Card('J', 'h'), Card('T', 'h')]
        hand = Hand(cards)
        assert len(hand.all_cards) == 5

    def test_hand_with_6_cards(self, six_card_hand):
        """Test hand creation with 6 cards"""
        hand = Hand(six_card_hand)
        assert len(hand.all_cards) == 6

    def test_hand_with_7_cards(self, seven_card_hand):
        """Test hand creation with 7 cards"""
        hand = Hand(seven_card_hand)
        assert len(hand.all_cards) == 7

    def test_hand_too_few_cards_raises(self):
        """Test that hand with fewer than 5 cards raises"""
        with pytest.raises(ValueError, match="Need at least 5 cards"):
            Hand([Card('A', 'h'), Card('K', 'h'), Card('Q', 'h')])

    def test_hand_too_many_cards_raises(self):
        """Test that hand with more than 7 cards raises"""
        cards = [Card(r, 'h') for r in ['A', 'K', 'Q', 'J', 'T', '9', '8', '7']]
        with pytest.raises(ValueError, match="Cannot use more than 7 cards"):
            Hand(cards)


class TestHandTypes:
    """Tests for all poker hand types"""

    def test_straight_flush(self, straight_flush_cards):
        """Test straight flush detection"""
        hand = Hand(straight_flush_cards)
        assert hand.hand_type == 9
        assert hand.name == "Straight Flush"

    def test_four_of_a_kind(self, four_of_a_kind_cards):
        """Test four of a kind detection"""
        hand = Hand(four_of_a_kind_cards)
        assert hand.hand_type == 8
        assert hand.name == "Four of a Kind"

    def test_full_house(self, full_house_cards):
        """Test full house detection"""
        hand = Hand(full_house_cards)
        assert hand.hand_type == 7
        assert hand.name == "Full House"

    def test_flush(self, flush_cards):
        """Test flush detection"""
        hand = Hand(flush_cards)
        assert hand.hand_type == 6
        assert hand.name == "Flush"

    def test_straight(self, straight_cards):
        """Test straight detection"""
        hand = Hand(straight_cards)
        assert hand.hand_type == 5
        assert hand.name == "Straight"

    def test_three_of_a_kind(self, three_of_a_kind_cards):
        """Test three of a kind detection"""
        hand = Hand(three_of_a_kind_cards)
        assert hand.hand_type == 4
        assert hand.name == "Three of a Kind"

    def test_two_pair(self, two_pair_cards):
        """Test two pair detection"""
        hand = Hand(two_pair_cards)
        assert hand.hand_type == 3
        assert hand.name == "Two Pair"

    def test_one_pair(self, one_pair_cards):
        """Test one pair detection"""
        hand = Hand(one_pair_cards)
        assert hand.hand_type == 2
        assert hand.name == "One Pair"

    def test_high_card(self, high_card_cards):
        """Test high card detection"""
        hand = Hand(high_card_cards)
        assert hand.hand_type == 1
        assert hand.name == "High Card"


class TestAceLowStraight:
    """Tests for ace-low straight (A-2-3-4-5)"""

    def test_ace_low_straight(self, ace_low_straight_cards):
        """Test ace-low straight is recognized"""
        hand = Hand(ace_low_straight_cards)
        assert hand.hand_type == 5
        assert hand.name == "Straight"

    def test_broadway_straight(self):
        """Test Broadway straight (10-J-Q-K-A) - must use mixed suits to avoid flush"""
        cards = [Card('T', 'h'), Card('J', 'c'), Card('Q', 'd'), Card('K', 'h'), Card('A', 's')]
        hand = Hand(cards)
        assert hand.hand_type == 5
        assert hand.name == "Straight"


class TestHandComparison:
    """Tests for hand comparison operators"""

    def test_straight_flush_beats_four_of_a_kind(self, straight_flush_cards, four_of_a_kind_cards):
        """Test straight flush beats four of a kind"""
        sf = Hand(straight_flush_cards)
        fk = Hand(four_of_a_kind_cards)
        assert sf > fk
        assert fk < sf

    def test_four_of_a_kind_beats_full_house(self, four_of_a_kind_cards, full_house_cards):
        """Test four of a kind beats full house"""
        fk = Hand(four_of_a_kind_cards)
        fh = Hand(full_house_cards)
        assert fk > fh

    def test_full_house_beats_flush(self, full_house_cards, flush_cards):
        """Test full house beats flush"""
        fh = Hand(full_house_cards)
        fl = Hand(flush_cards)
        assert fh > fl

    def test_flush_beats_straight(self, flush_cards, straight_cards):
        """Test flush beats straight"""
        fl = Hand(flush_cards)
        st = Hand(straight_cards)
        assert fl > st

    def test_straight_beats_three_of_a_kind(self, straight_cards, three_of_a_kind_cards):
        """Test straight beats three of a kind"""
        st = Hand(straight_cards)
        tk = Hand(three_of_a_kind_cards)
        assert st > tk

    def test_three_of_a_kind_beats_two_pair(self, three_of_a_kind_cards, two_pair_cards):
        """Test three of a kind beats two pair"""
        tk = Hand(three_of_a_kind_cards)
        tp = Hand(two_pair_cards)
        assert tk > tp

    def test_two_pair_beats_one_pair(self, two_pair_cards, one_pair_cards):
        """Test two pair beats one pair"""
        tp = Hand(two_pair_cards)
        op = Hand(one_pair_cards)
        assert tp > op

    def test_one_pair_beats_high_card(self, one_pair_cards, high_card_cards):
        """Test one pair beats high card"""
        op = Hand(one_pair_cards)
        hc = Hand(high_card_cards)
        assert op > hc

    def test_higher_pair_wins(self):
        """Test higher pair wins over lower pair"""
        # Aces over kings
        aces = [Card('A', 's'), Card('A', 'd'), Card('K', 'c'), Card('Q', 'h'), Card('J', 's')]
        kings = [Card('K', 's'), Card('K', 'd'), Card('A', 'c'), Card('Q', 'h'), Card('J', 's')]
        aces_hand = Hand(aces)
        kings_hand = Hand(kings)
        assert aces_hand > kings_hand

    def test_kickers_work(self):
        """Test kickers determine winner when pairs equal"""
        # Aces with Q kicker vs Aces with J kicker
        aces_q = [Card('A', 's'), Card('A', 'd'), Card('K', 'c'), Card('Q', 'h'), Card('3', 's')]
        aces_j = [Card('A', 's'), Card('A', 'd'), Card('K', 'c'), Card('J', 'h'), Card('2', 's')]
        aces_q_hand = Hand(aces_q)
        aces_j_hand = Hand(aces_j)
        assert aces_q_hand > aces_j_hand

    def test_two_pair_kickers(self):
        """Test kicker for two pair when both have same pairs"""
        # Aces over Kings with same two pair, different kicker
        aces_q_kicker = [Card('A', 's'), Card('A', 'd'), Card('K', 'c'), Card('K', 'h'), Card('Q', 's')]
        aces_j_kicker = [Card('A', 's'), Card('A', 'd'), Card('K', 'c'), Card('K', 'h'), Card('J', 's')]
        hand1 = Hand(aces_q_kicker)
        hand2 = Hand(aces_j_kicker)
        assert hand1 > hand2

    def test_hand_equality(self, one_pair_cards):
        """Test hand equality comparison"""
        h1 = Hand(one_pair_cards)
        h2 = Hand(one_pair_cards)
        assert h1 == h2

    def test_hand_compare_to_zero(self, one_pair_cards):
        """Test compare_to with tied hands returns 0"""
        h1 = Hand(one_pair_cards)
        h2 = Hand(one_pair_cards)
        assert h1.compare_to(h2) == 0


class TestHandStr:
    """Tests for hand string representations"""

    def test_hand_str(self, straight_flush_cards):
        """Test hand string representation"""
        hand = Hand(straight_flush_cards)
        s = str(hand)
        assert "Straight Flush" in s

    def test_hand_repr(self, straight_flush_cards):
        """Test hand repr"""
        hand = Hand(straight_flush_cards)
        r = repr(hand)
        assert "Hand(" in r


class Test_hand_rank_key:
    """Tests for hand_rank_key function"""

    def test_hand_rank_key_basic(self):
        """Test hand_rank_key creates comparable tuple"""
        key1 = hand_rank_key([9, 12], [])
        key2 = hand_rank_key([9, 11], [])
        assert key1 > key2

    def test_hand_rank_key_with_kickers(self):
        """Test hand_rank_key includes kickers"""
        key1 = hand_rank_key([8, 12], [11])
        key2 = hand_rank_key([8, 12], [10])
        assert key1 > key2

    def test_hand_rank_key_empty_kickers(self):
        """Test hand_rank_key handles empty kickers"""
        key = hand_rank_key([1, 12, 11, 10, 9], [])
        assert key[0] == 1


class TestHandEvaluator:
    """Tests for HandEvaluator class"""

    def test_best_hand(self, straight_cards):
        """Test best_hand returns best 5-card hand"""
        result = HandEvaluator.best_hand(straight_cards)
        assert isinstance(result, Hand)
        assert result.hand_type == 5

    def test_compare(self):
        """Test compare returns -1, 0, or 1"""
        straight = [Card('9', 's'), Card('T', 'h'), Card('J', 'c'), Card('Q', 'd'), Card('K', 'h')]
        three_kind = [Card('A', 's'), Card('A', 'd'), Card('A', 'c'), Card('K', 'd'), Card('Q', 'h')]
        
        result = HandEvaluator.compare(straight, three_kind)
        assert result == 1  # Straight wins

    def test_compare_tie(self, one_pair_cards):
        """Test compare with tied hands returns 0"""
        result = HandEvaluator.compare(one_pair_cards, one_pair_cards)
        assert result == 0


class TestHandBest5Selection:
    """Tests for best 5-card selection from 6/7 cards"""

    def test_six_card_hand_best_5(self, six_card_hand):
        """Test 6-card hand selects best 5"""
        hand = Hand(six_card_hand)
        assert len(hand.best_5) == 5
        # Should be a full house (Aces full of Kings)
        assert hand.hand_type == 7

    def test_seven_card_hand_best_5(self, seven_card_hand):
        """Test 7-card hand selects best 5"""
        hand = Hand(seven_card_hand)
        assert len(hand.best_5) == 5
        # Should be a full house (Aces full of Kings)
        assert hand.hand_type == 7

    def test_seven_card_straight_flush_from_7(self):
        """Test 7 cards can make a straight flush"""
        # 7-8-9-T-J in hearts + 2 other cards
        cards = [
            Card('7', 'h'), Card('8', 'h'), Card('9', 'h'), 
            Card('T', 'h'), Card('J', 'h'), 
            Card('A', 's'), Card('2', 'd')
        ]
        hand = Hand(cards)
        # Straight flush should be best
        assert hand.hand_type == 9


class TestHANDNAMES:
    """Tests for HAND_NAMES constant"""

    def test_hand_names_has_all_types(self):
        """Test HAND_NAMES has all hand types"""
        assert HAND_NAMES[9] == "Straight Flush"
        assert HAND_NAMES[8] == "Four of a Kind"
        assert HAND_NAMES[7] == "Full House"
        assert HAND_NAMES[6] == "Flush"
        assert HAND_NAMES[5] == "Straight"
        assert HAND_NAMES[4] == "Three of a Kind"
        assert HAND_NAMES[3] == "Two Pair"
        assert HAND_NAMES[2] == "One Pair"
        assert HAND_NAMES[1] == "High Card"
        assert HAND_NAMES[0] == "Invalid"
