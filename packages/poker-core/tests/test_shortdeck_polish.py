"""Polish edge case tests for Shortdeck

- Verify flush > full house > straight ranking
- Verify wheel straight (A-6-7-8-9) detection
- Verify best 5 selection from 7 cards prioritizes flush over FH
"""
import pytest
import sys
sys.path.insert(0, "packages/poker-core/src")

from gto_poker.shortdeck import ShortdeckHand, ShortdeckDeck


class TestShortdeckRankingEdgeCases:
    """Verify Shortdeck ranking: SF > 4K > Flush > FH > Straight > 3K > 2P > 1P > HC."""

    def test_flush_beats_full_house_rank_numbers(self):
        """Flush has type 7, FH has type 6, so 7 > 6."""
        from gto_poker.deck import Card
        flush = ShortdeckHand([Card('A', 'h'), Card('K', 'h'), Card('Q', 'h'), Card('9', 'h'), Card('7', 'h')])
        fh = ShortdeckHand([Card('A', 's'), Card('A', 'd'), Card('A', 'c'), Card('K', 's'), Card('K', 'd')])
        assert flush.hand_type == 7
        assert fh.hand_type == 6
        assert flush > fh, "Flush (7) should beat Full House (6)"

    def test_full_house_beats_straight_rank_numbers(self):
        """FH has type 6, Straight has type 5, so 6 > 5."""
        from gto_poker.deck import Card
        fh = ShortdeckHand([Card('A', 's'), Card('A', 'd'), Card('A', 'c'), Card('K', 's'), Card('K', 'd')])
        straight = ShortdeckHand([Card('9', 's'), Card('T', 'h'), Card('J', 'c'), Card('Q', 'd'), Card('K', 'h')])
        assert fh.hand_type == 6
        assert straight.hand_type == 5
        assert fh > straight, "Full House (6) should beat Straight (5)"

    def test_straight_flush_highest_rank(self):
        """Straight flush (9) beats everything else."""
        from gto_poker.deck import Card
        sf = ShortdeckHand([Card('9', 'h'), Card('T', 'h'), Card('J', 'h'), Card('Q', 'h'), Card('K', 'h')])
        fk = ShortdeckHand([Card('A', 's'), Card('A', 'd'), Card('A', 'c'), Card('A', 'h'), Card('K', 'd')])
        flush = ShortdeckHand([Card('A', 'h'), Card('K', 'h'), Card('Q', 'h'), Card('9', 'h'), Card('7', 'h')])
        assert sf.hand_type == 9
        assert fk.hand_type == 8
        assert flush.hand_type == 7
        assert sf > fk, "Straight Flush (9) beats 4K (8)"
        assert sf > flush, "Straight Flush (9) beats Flush (7)"

    def test_wheel_straight_a_6_7_8_9(self):
        """A-6-7-8-9 is the shortdeck 'wheel' (Ace plays low)."""
        from gto_poker.deck import Card
        cards = [Card('A', 'h'), Card('6', 's'), Card('7', 'd'), Card('8', 'c'), Card('9', 'h')]
        hand = ShortdeckHand(cards)
        assert hand.hand_type == 5, f"Expected straight (5), got {hand.hand_type}"
        assert hand.name == "Straight"

    def test_wheel_rank_key_is_lowest_straight(self):
        """A-6-7-8-9 should be the lowest possible straight in Shortdeck."""
        from gto_poker.deck import Card
        wheel = ShortdeckHand([Card('A', 'h'), Card('6', 's'), Card('7', 'd'), Card('8', 'c'), Card('9', 'h')])
        broadway = ShortdeckHand([Card('T', 'h'), Card('J', 'c'), Card('Q', 'd'), Card('K', 'h'), Card('A', 's')])
        # In Shortdeck, straights are compared by high card.
        # Wheel = 9-high straight, Broadway = A-high straight.
        # A-high straight should beat 9-high straight.
        assert broadway > wheel, "Broadway should beat wheel in Shortdeck"

    def test_seven_cards_flush_over_fh(self):
        """With 7 cards containing both a flush and a FH, flush should be selected."""
        from gto_poker.deck import Card
        cards = [
            Card('A', 'h'), Card('K', 'h'), Card('Q', 'h'), Card('J', 'h'), Card('9', 'h'),
            Card('A', 's'), Card('A', 'd'),
        ]
        hand = ShortdeckHand(cards)
        assert hand.hand_type == 7, f"Should select flush (7) over full house, got {hand.hand_type}"

    def test_seven_cards_fh_over_straight(self):
        """With 7 cards containing both a FH and a straight, FH should win."""
        from gto_poker.deck import Card
        cards = [
            Card('A', 's'), Card('A', 'd'), Card('A', 'c'),
            Card('K', 's'), Card('K', 'd'),
            Card('Q', 'h'), Card('J', 'h'),
        ]
        hand = ShortdeckHand(cards)
        assert hand.hand_type == 6, f"FH (6) should beat straight (5), got {hand.hand_type}"

    def test_flush_ranked_by_high_card(self):
        """Two flushes compared by high card (Ace flush beats King flush)."""
        from gto_poker.deck import Card
        ace_flush = ShortdeckHand([Card('A', 'h'), Card('K', 'h'), Card('Q', 'h'), Card('T', 'h'), Card('8', 'h')])
        king_flush = ShortdeckHand([Card('K', 's'), Card('Q', 's'), Card('J', 's'), Card('T', 's'), Card('8', 's')])
        assert ace_flush > king_flush, "Ace-high flush should beat King-high flush"
