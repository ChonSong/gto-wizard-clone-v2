"""Tests for Shortdeck (6+ hold'em) hand evaluation.

Shortdeck is a variant where cards 2-5 are removed from the deck (36 cards).
Hand rankings: straight flush > four of a kind > flush > full house > straight >
              three of kind > two pair > one pair > high card
(flush > full house > straight unlike standard poker).
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gto_poker.shortdeck import ShortdeckHand, ShortdeckDeck, SHORTDECK_RANKS, shortdeck_rank_index


class TestShortdeckDeck:
    """Tests for Shortdeck 36-card deck"""

    def test_shortdeck_deck_has_36_cards(self):
        """Shortdeck deck should have 36 cards (6-A removed)"""
        deck = ShortdeckDeck()
        assert len(deck) == 36

    def test_shortdeck_deck_contains_no_2_to_5(self):
        """Shortdeck deck should not contain cards 2, 3, 4, or 5"""
        deck = ShortdeckDeck()
        for card in deck:
            assert card.rank not in ["2", "3", "4", "5"]

    def test_shortdeck_deck_contains_6_to_A(self):
        """Shortdeck deck should contain ranks 6 through A"""
        deck = ShortdeckDeck()
        ranks_seen = set(card.rank for card in deck)
        expected_ranks = set(SHORTDECK_RANKS)
        assert ranks_seen == expected_ranks

    def test_shortdeck_deck_draw(self):
        """Should be able to draw cards from deck"""
        deck = ShortdeckDeck()
        cards = deck.draw(5)
        assert len(cards) == 5
        assert len(deck) == 31

    def test_shortdeck_deck_shuffle(self):
        """Deck should shuffle without error"""
        deck = ShortdeckDeck()
        deck.shuffle(seed=42)
        assert len(deck) == 36

    def test_shortdeck_deck_reset(self):
        """Deck should reset to 36 cards"""
        deck = ShortdeckDeck()
        deck.draw(10)
        deck.reset()
        assert len(deck) == 36


class TestShortdeckRankIndex:
    """Tests for shortdeck rank indexing"""

    def test_rank_index_6_is_low(self):
        """Rank 6 should be index 0 (lowest)"""
        assert shortdeck_rank_index("6") == 0

    def test_rank_index_A_is_high(self):
        """Rank A should be index 8 (highest)"""
        assert shortdeck_rank_index("A") == 8

    def test_rank_index_order(self):
        """Ranks should be ordered 6 < 7 < 8 < ... < A"""
        for i in range(len(SHORTDECK_RANKS) - 1):
            assert shortdeck_rank_index(SHORTDECK_RANKS[i]) < shortdeck_rank_index(SHORTDECK_RANKS[i + 1])


class TestShortdeckHandCreation:
    """Tests for ShortdeckHand class creation"""

    def test_hand_with_5_cards(self):
        """Test hand creation with 5 cards"""
        from gto_poker.deck import Card
        cards = [Card('A', 'h'), Card('K', 'h'), Card('Q', 'h'), Card('J', 'h'), Card('T', 'h')]
        hand = ShortdeckHand(cards)
        assert len(hand.all_cards) == 5

    def test_hand_with_6_cards(self):
        """Test hand creation with 6 cards"""
        from gto_poker.deck import Card
        cards = [Card('A', 's'), Card('A', 'd'), Card('A', 'c'), Card('K', 'd'), Card('K', 'c'), Card('Q', 'h')]
        hand = ShortdeckHand(cards)
        assert len(hand.all_cards) == 6

    def test_hand_too_few_cards_raises(self):
        """Test that hand with fewer than 5 cards raises"""
        from gto_poker.deck import Card
        with pytest.raises(ValueError, match="Need at least 5 cards"):
            ShortdeckHand([Card('A', 'h'), Card('K', 'h'), Card('Q', 'h')])


class TestShortdeckHandTypes:
    """Tests for Shortdeck hand types.

    Key difference from standard poker: flush beats full house, full house beats straight.
    """

    def test_straight_flush(self):
        """Test straight flush detection in Shortdeck"""
        from gto_poker.deck import Card
        cards = [Card('9', 'h'), Card('T', 'h'), Card('J', 'h'), Card('Q', 'h'), Card('K', 'h')]
        hand = ShortdeckHand(cards)
        assert hand.hand_type == 9
        assert hand.name == "Straight Flush"

    def test_four_of_a_kind(self):
        """Test four of a kind detection in Shortdeck"""
        from gto_poker.deck import Card
        cards = [Card('A', 's'), Card('A', 'd'), Card('A', 'c'), Card('A', 'h'), Card('K', 'd')]
        hand = ShortdeckHand(cards)
        assert hand.hand_type == 8
        assert hand.name == "Four of a Kind"

    def test_flush(self):
        """Test flush detection in Shortdeck"""
        from gto_poker.deck import Card
        cards = [Card('A', 'h'), Card('K', 'h'), Card('Q', 'h'), Card('9', 'h'), Card('7', 'h')]
        hand = ShortdeckHand(cards)
        assert hand.hand_type == 7
        assert hand.name == "Flush"

    def test_full_house(self):
        """Test full house detection in Shortdeck"""
        from gto_poker.deck import Card
        cards = [Card('A', 's'), Card('A', 'd'), Card('A', 'c'), Card('K', 's'), Card('K', 'd')]
        hand = ShortdeckHand(cards)
        assert hand.hand_type == 6
        assert hand.name == "Full House"

    def test_straight(self):
        """Test straight detection in Shortdeck"""
        from gto_poker.deck import Card
        cards = [Card('9', 's'), Card('T', 'h'), Card('J', 'c'), Card('Q', 'd'), Card('K', 'h')]
        hand = ShortdeckHand(cards)
        assert hand.hand_type == 5
        assert hand.name == "Straight"

    def test_three_of_a_kind(self):
        """Test three of a kind detection in Shortdeck"""
        from gto_poker.deck import Card
        cards = [Card('A', 's'), Card('A', 'd'), Card('A', 'c'), Card('K', 'd'), Card('Q', 'h')]
        hand = ShortdeckHand(cards)
        assert hand.hand_type == 4
        assert hand.name == "Three of a Kind"

    def test_two_pair(self):
        """Test two pair detection in Shortdeck"""
        from gto_poker.deck import Card
        cards = [Card('A', 's'), Card('A', 'd'), Card('K', 'c'), Card('K', 'h'), Card('Q', 'h')]
        hand = ShortdeckHand(cards)
        assert hand.hand_type == 3
        assert hand.name == "Two Pair"

    def test_one_pair(self):
        """Test one pair detection in Shortdeck"""
        from gto_poker.deck import Card
        cards = [Card('A', 's'), Card('A', 'd'), Card('K', 'c'), Card('Q', 'h'), Card('J', 'd')]
        hand = ShortdeckHand(cards)
        assert hand.hand_type == 2
        assert hand.name == "One Pair"

    def test_high_card(self):
        """Test high card detection in Shortdeck"""
        from gto_poker.deck import Card
        cards = [Card('A', 's'), Card('K', 'd'), Card('Q', 'h'), Card('J', 'c'), Card('9', 's')]
        hand = ShortdeckHand(cards)
        assert hand.hand_type == 1
        assert hand.name == "High Card"


class TestShortdeckHandComparison:
    """Tests for Shortdeck hand comparisons.

    Shortdeck ranking: SF > 4K > Flush > FH > Straight > 3K > 2P > 1P > HC
    (Flush > Full House > Straight unlike standard poker)
    """

    def test_flush_beats_full_house(self):
        """Test flush beats full house in Shortdeck"""
        from gto_poker.deck import Card
        flush_cards = [Card('A', 'h'), Card('K', 'h'), Card('Q', 'h'), Card('9', 'h'), Card('7', 'h')]
        fh_cards = [Card('A', 's'), Card('A', 'd'), Card('A', 'c'), Card('K', 's'), Card('K', 'd')]
        flush = ShortdeckHand(flush_cards)
        fh = ShortdeckHand(fh_cards)
        assert flush > fh

    def test_full_house_beats_straight(self):
        """Test full house beats straight in Shortdeck"""
        from gto_poker.deck import Card
        fh_cards = [Card('A', 's'), Card('A', 'd'), Card('A', 'c'), Card('K', 's'), Card('K', 'd')]
        straight_cards = [Card('9', 's'), Card('T', 'h'), Card('J', 'c'), Card('Q', 'd'), Card('K', 'h')]
        fh = ShortdeckHand(fh_cards)
        straight = ShortdeckHand(straight_cards)
        assert fh > straight

    def test_straight_beats_three_of_a_kind(self):
        """Test straight beats three of a kind in Shortdeck"""
        from gto_poker.deck import Card
        straight_cards = [Card('9', 's'), Card('T', 'h'), Card('J', 'c'), Card('Q', 'd'), Card('K', 'h')]
        trips_cards = [Card('A', 's'), Card('A', 'd'), Card('A', 'c'), Card('K', 'd'), Card('Q', 'h')]
        straight = ShortdeckHand(straight_cards)
        trips = ShortdeckHand(trips_cards)
        assert straight > trips

    def test_four_of_a_kind_beats_flush(self):
        """Test four of a kind beats flush in Shortdeck"""
        from gto_poker.deck import Card
        fk_cards = [Card('A', 's'), Card('A', 'd'), Card('A', 'c'), Card('A', 'h'), Card('K', 'd')]
        flush_cards = [Card('A', 'h'), Card('K', 'h'), Card('Q', 'h'), Card('9', 'h'), Card('7', 'h')]
        fk = ShortdeckHand(fk_cards)
        flush = ShortdeckHand(flush_cards)
        assert fk > flush

    def test_straight_flush_beats_four_of_a_kind(self):
        """Test straight flush beats four of a kind in Shortdeck"""
        from gto_poker.deck import Card
        sf_cards = [Card('9', 'h'), Card('T', 'h'), Card('J', 'h'), Card('Q', 'h'), Card('K', 'h')]
        fk_cards = [Card('A', 's'), Card('A', 'd'), Card('A', 'c'), Card('A', 'h'), Card('K', 'd')]
        sf = ShortdeckHand(sf_cards)
        fk = ShortdeckHand(fk_cards)
        assert sf > fk

    def test_higher_flush_wins(self):
        """Test higher flush wins (Ace-high flush beats King-high flush)"""
        from gto_poker.deck import Card
        ace_flush = [Card('A', 'h'), Card('K', 'h'), Card('Q', 'h'), Card('9', 'h'), Card('7', 'h')]
        king_flush = [Card('K', 'h'), Card('Q', 'h'), Card('J', 'h'), Card('9', 'h'), Card('7', 'h')]
        ace = ShortdeckHand(ace_flush)
        king = ShortdeckHand(king_flush)
        assert ace > king

    def test_full_house_comparison(self):
        """Test full house comparison (higher trips wins)"""
        from gto_poker.deck import Card
        aces_full = [Card('A', 's'), Card('A', 'd'), Card('A', 'c'), Card('K', 's'), Card('K', 'd')]
        kings_full = [Card('K', 's'), Card('K', 'd'), Card('K', 'c'), Card('A', 's'), Card('A', 'd')]
        aces = ShortdeckHand(aces_full)
        kings = ShortdeckHand(kings_full)
        assert aces > kings


class TestShortdeckLowStraights:
    """Tests for Shortdeck straights (no ace-low straights since 2-5 removed)"""

    def test_broadway_straight(self):
        """Test Broadway straight (T-J-Q-K-A) in Shortdeck"""
        from gto_poker.deck import Card
        cards = [Card('T', 'h'), Card('J', 'c'), Card('Q', 'd'), Card('K', 'h'), Card('A', 's')]
        hand = ShortdeckHand(cards)
        assert hand.hand_type == 5
        assert hand.name == "Straight"

    def test_lower_straight_6_7_8_9_T(self):
        """Test 6-7-8-9-T straight in Shortdeck"""
        from gto_poker.deck import Card
        cards = [Card('6', 'h'), Card('7', 'c'), Card('8', 'd'), Card('9', 'h'), Card('T', 's')]
        hand = ShortdeckHand(cards)
        assert hand.hand_type == 5
        assert hand.name == "Straight"


class TestShortdeckBest5Selection:
    """Tests for best 5-card selection from 6/7 cards in Shortdeck"""
    def test_six_card_hand_selects_best_5(self):
        """Test 6-card Shortdeck hand selects best 5 cards"""
        from gto_poker.deck import Card
        # Aces full of Kings (6 cards - the last Q is kicker)
        cards = [Card('A', 's'), Card('A', 'd'), Card('A', 'c'), Card('K', 'd'), Card('K', 'c'), Card('Q', 'h')]
        hand = ShortdeckHand(cards)
        assert len(hand.best_5) == 5
        # Should be a full house (Aces full of Kings)
        assert hand.hand_type == 6

    def test_seven_card_hand_selects_best_5(self):
        """Test 7-card Shortdeck hand selects best 5 cards"""
        from gto_poker.deck import Card
        # Aces full of Kings with extra cards
        cards = [Card('A', 's'), Card('A', 'd'), Card('A', 'c'), Card('K', 'd'), Card('K', 'c'), Card('Q', 'h'), Card('J', 'd')]
        hand = ShortdeckHand(cards)
        assert len(hand.best_5) == 5
        # Should be a full house (Aces full of Kings)
        assert hand.hand_type == 6

    def test_six_card_straight_flush_from_6(self):
        """Test 6 cards can make a straight flush in Shortdeck"""
        from gto_poker.deck import Card
        # 7-8-9-T-J in hearts + extra card
        cards = [
            Card('7', 'h'), Card('8', 'h'), Card('9', 'h'),
            Card('T', 'h'), Card('J', 'h'),
            Card('A', 's')
        ]
        hand = ShortdeckHand(cards)
        assert hand.hand_type == 9  # Straight Flush


class TestShortdeckHandEquality:
    """Tests for Shortdeck hand equality and comparison"""
    def test_equal_hands_tie(self):
        """Test two identical hands tie"""
        from gto_poker.deck import Card
        cards1 = [Card('A', 's'), Card('A', 'd'), Card('K', 'c'), Card('K', 'h'), Card('Q', 'h')]
        cards2 = [Card('A', 'h'), Card('A', 'c'), Card('K', 's'), Card('K', 'd'), Card('Q', 'c')]
        h1 = ShortdeckHand(cards1)
        h2 = ShortdeckHand(cards2)
        assert h1 == h2

    def test_compare_to_method(self):
        """Test compare_to method returns -1, 0, or 1"""
        from gto_poker.deck import Card
        straight = [Card('9', 's'), Card('T', 'h'), Card('J', 'c'), Card('Q', 'd'), Card('K', 'h')]
        three_kind = [Card('A', 's'), Card('A', 'd'), Card('A', 'c'), Card('K', 'd'), Card('Q', 'h')]
        h1 = ShortdeckHand(straight)
        h2 = ShortdeckHand(three_kind)
        # Straight (5) should beat Three of a Kind (4)
        assert h1.compare_to(h2) == 1

    def test_hand_str(self):
        """Test hand string representation"""
        from gto_poker.deck import Card
        cards = [Card('9', 'h'), Card('T', 'h'), Card('J', 'h'), Card('Q', 'h'), Card('K', 'h')]
        hand = ShortdeckHand(cards)
        s = str(hand)
        assert "Straight Flush" in s


class TestShortdeckEdgeCases:
    """Edge case tests for Shortdeck hand evaluation and comparison.

    Shortdeck ranking: SF > 4K > Flush > FH > Straight > 3K > 2P > 1P > HC
    """

    def test_shortdeck_wheel_straight(self):
        """A-6-7-8-9 is the shortdeck 'wheel' (Ace plays low)"""
        from gto_poker.deck import Card
        cards = [Card('A', 'h'), Card('6', 's'), Card('7', 'd'), Card('8', 'c'), Card('9', 'h')]
        hand = ShortdeckHand(cards)
        assert hand.hand_type == 5, f"Expected straight (5), got {hand.hand_type}"
        assert hand.name == "Straight"

    def test_flush_beats_fh_from_seven_cards(self):
        """With 7 cards, the best 5 should be flush over full house.
        
        Need 5 cards of the same suit for a flush. Only 4 hearts won't cut it."""
        from gto_poker.deck import Card
        # 5 hearts (possible flush) + 3 cards making full house
        cards = [
            Card('A', 'h'), Card('K', 'h'), Card('Q', 'h'), Card('J', 'h'), Card('9', 'h'),  # 5 hearts = flush
            Card('A', 's'), Card('A', 'd'),  # makes AAA-KK... but only 4 hearts used for flush
        ]
        # With 7 cards: flush (5 hearts) beats full house (AAA from As,Ad,Ah + KK...)
        # Best flush: Ah, Kh, Qh, Jh, 9h = A-K-Q-J-9 hearts flush
        hand = ShortdeckHand(cards)
        assert hand.hand_type == 7, f"Should select flush (7) over full house, got {hand.hand_type}"
        assert hand.name == "Flush"

    def test_straight_flush_always_best_from_7(self):
        """With 7 cards including straight flush, it should be selected"""
        from gto_poker.deck import Card
        cards = [
            Card('T', 'h'), Card('J', 'h'), Card('Q', 'h'), Card('K', 'h'),  # 4 hearts for SF
            Card('9', 'h'),  # completes 9-T-J-Q-K hearts straight flush
            Card('A', 's'), Card('A', 'd'),  # aces pair (weaker)
        ]
        hand = ShortdeckHand(cards)
        assert hand.hand_type == 9, f"Should select straight flush (9), got {hand.hand_type}"

    def test_higher_flush_ranked_correctly(self):
        """Ace-high flush beats King-high flush even with 7 cards.
        
        Avoid accidentally creating straight flushes — use non-consecutive cards."""
        from gto_poker.deck import Card
        ace_flush = ShortdeckHand([
            Card('A', 'h'), Card('K', 'h'), Card('Q', 'h'), Card('T', 'h'), Card('8', 'h')
        ])
        king_flush = ShortdeckHand([
            Card('K', 's'), Card('Q', 's'), Card('J', 's'), Card('T', 's'), Card('8', 's')
        ])
        assert ace_flush > king_flush

    def test_fh_vs_straight_via_seven_cards(self):
        """Full house beats straight when both possible from 7 cards"""
        from gto_poker.deck import Card
        # 4 cards make a full house, 3 make a straight
        cards = [
            Card('A', 's'), Card('A', 'd'), Card('A', 'c'),  # AAA trips
            Card('K', 's'), Card('K', 'd'),  # KK pair -> AAA-KK full house
            Card('Q', 'h'), Card('J', 'h'),  # extra broadway cards
        ]
        hand = ShortdeckHand(cards)
        assert hand.hand_type == 6, f"Full house (6) should beat straight (5), got {hand.hand_type}"
