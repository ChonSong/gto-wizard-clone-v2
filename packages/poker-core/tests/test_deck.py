"""Tests for deck module - Card and Deck classes"""
import pytest
from gto_poker.deck import Card, Deck, RANKS, SUITS


class TestCard:
    """Tests for Card class"""

    def test_card_creation_valid(self):
        """Test card creation with valid rank and suit"""
        c = Card('A', 'h')
        assert c.rank == 'A'
        assert c.suit == 'h'

    def test_card_rank_case_insensitive(self):
        """Test that rank is uppercased"""
        c = Card('a', 'H')
        assert c.rank == 'A'
        assert c.suit == 'h'

    def test_invalid_rank_raises(self):
        """Test that invalid rank raises ValueError"""
        with pytest.raises(ValueError, match="Invalid rank"):
            Card('X', 'h')
        with pytest.raises(ValueError, match="Invalid rank"):
            Card('10', 'h')

    def test_invalid_suit_raises(self):
        """Test that invalid suit raises ValueError"""
        with pytest.raises(ValueError, match="Invalid suit"):
            Card('A', 'x')
        with pytest.raises(ValueError, match="Invalid suit"):
            Card('A', 'hearts')

    def test_index_property(self):
        """Test card index is in valid range"""
        c = Card('A', 'h')
        assert 0 <= c.index < 52
        
        # Test all suits for same rank have consecutive indices
        # RANKS.index('A') = 12, so Ah = 12*4+0=48, Ad=49, Ac=50, As=51
        for suit_idx, suit in enumerate(SUITS):
            card = Card('A', suit)
            expected = 12 * 4 + suit_idx  # A is at index 12 in RANKS
            assert card.index == expected

    def test_rank_index_property(self):
        """Test rank_index is correct for all ranks (2=0 lowest, A=12 highest)"""
        # 2 is rank index 0 (lowest)
        assert Card('2', 'h').rank_index == 0
        # 3 is rank index 1
        assert Card('3', 'h').rank_index == 1
        # 9 is rank index 7
        assert Card('9', 'h').rank_index == 7
        # T is rank index 8
        assert Card('T', 'h').rank_index == 8
        # J is rank index 9
        assert Card('J', 'h').rank_index == 9
        # Q is rank index 10
        assert Card('Q', 'h').rank_index == 10
        # K is rank index 11
        assert Card('K', 'h').rank_index == 11
        # A is rank index 12 (highest)
        assert Card('A', 'h').rank_index == 12

    def test_card_equality(self):
        """Test card equality"""
        c1 = Card('A', 'h')
        c2 = Card('A', 'h')
        c3 = Card('A', 'd')
        c4 = Card('K', 'h')
        
        assert c1 == c2
        assert c1 != c3
        assert c1 != c4
        assert c3 != c4

    def test_card_hash(self):
        """Test card is hashable"""
        c1 = Card('A', 'h')
        c2 = Card('A', 'h')
        c3 = Card('A', 'd')
        
        assert hash(c1) == hash(c2)
        assert hash(c1) != hash(c3)
        
        # Can be used in set
        s = {c1, c2, c3}
        assert len(s) == 2

    def test_card_str(self):
        """Test card string representation"""
        c = Card('A', 'h')
        assert str(c) == 'Ah'
        
        c2 = Card('T', 'd')
        assert str(c2) == 'Td'

    def test_card_repr(self):
        """Test card repr"""
        c = Card('A', 'h')
        assert repr(c) == "Card('A', 'h')"


class TestDeck:
    """Tests for Deck class"""

    def test_deck_has_52_cards(self):
        """Test deck initialization has 52 cards"""
        d = Deck()
        assert len(d) == 52

    def test_deck_contains_all_cards(self):
        """Test deck contains all 52 unique cards"""
        d = Deck()
        cards_set = set(d._cards)
        assert len(cards_set) == 52

    def test_deck_draw_reduces_count(self):
        """Test drawing cards reduces deck size"""
        d = Deck()
        initial_len = len(d)
        d.draw(5)
        assert len(d) == initial_len - 5

    def test_deck_draw_returns_cards(self):
        """Test draw returns correct cards"""
        d = Deck()
        cards = d.draw(3)
        assert len(cards) == 3
        assert all(isinstance(c, Card) for c in cards)

    def test_deck_draw_exhausts_deck(self):
        """Test drawing all cards empties deck"""
        d = Deck()
        d.draw(52)
        assert len(d) == 0

    def test_deck_draw_too_many_raises(self):
        """Test drawing more cards than available raises"""
        d = Deck()
        with pytest.raises(ValueError, match="Cannot draw"):
            d.draw(53)

    def test_deck_draw_one(self):
        """Test draw_one returns single card"""
        d = Deck()
        card = d.draw_one()
        assert isinstance(card, Card)
        assert len(d) == 51

    def test_deck_draw_one_empty_raises(self):
        """Test draw_one on empty deck raises"""
        d = Deck()
        d.draw(52)
        with pytest.raises(ValueError, match="Cannot draw"):
            d.draw_one()

    def test_deck_reset(self):
        """Test reset restores deck to 52 cards"""
        d = Deck()
        d.draw(20)
        assert len(d) == 32
        d.reset()
        assert len(d) == 52

    def test_deck_shuffle_changes_order(self):
        """Test shuffle changes card order"""
        d1 = Deck()
        original_order = list(d1._cards)
        d1.shuffle()
        # Very unlikely to be same order (1/52!)
        assert d1._cards != original_order

    def test_deck_shuffle_deterministic_with_seed(self):
        """Test shuffle with seed produces same result"""
        d1 = Deck()
        d1.shuffle(seed=42)
        order1 = list(d1._cards)
        
        d2 = Deck()
        d2.shuffle(seed=42)
        order2 = list(d2._cards)
        
        assert order1 == order2

    def test_deck_iter(self):
        """Test deck is iterable"""
        d = Deck()
        count = 0
        for card in d:
            assert isinstance(card, Card)
            count += 1
        assert count == 52

    def test_deck_len(self):
        """Test deck length"""
        d = Deck()
        assert len(d) == 52

    def test_parse_valid_card(self):
        """Test Deck.parse with valid card string"""
        c = Deck.parse('Ah')
        assert c.rank == 'A'
        assert c.suit == 'h'
        
        c2 = Deck.parse('Td')
        assert c2.rank == 'T'
        assert c2.suit == 'd'
        
        c3 = Deck.parse('7c')
        assert c3.rank == '7'
        assert c3.suit == 'c'

    def test_parse_invalid_length(self):
        """Test Deck.parse with invalid length raises"""
        with pytest.raises(ValueError, match="Invalid card string"):
            Deck.parse('A')
        with pytest.raises(ValueError, match="Invalid card string"):
            Deck.parse('Ahd')
        with pytest.raises(ValueError, match="Invalid card string"):
            Deck.parse('')

    def test_parse_invalid_rank(self):
        """Test Deck.parse with invalid rank raises"""
        with pytest.raises(ValueError):
            Deck.parse('Xh')

    def test_parse_board_valid(self):
        """Test Deck.parse_board with valid string"""
        cards = Deck.parse_board('Kd7h2c')
        assert len(cards) == 3
        assert cards[0].rank == 'K'
        assert cards[0].suit == 'd'
        assert cards[1].rank == '7'
        assert cards[1].suit == 'h'
        assert cards[2].rank == '2'
        assert cards[2].suit == 'c'

    def test_parse_board_with_commas(self):
        """Test Deck.parse_board handles commas"""
        cards = Deck.parse_board('Kd,7h,2c')
        assert len(cards) == 3

    def test_parse_board_invalid_length(self):
        """Test Deck.parse_board with odd length raises"""
        with pytest.raises(ValueError, match="Invalid board string"):
            Deck.parse_board('Kd7h2')  # 5 chars, odd

    def test_parse_board_empty(self):
        """Test Deck.parse_board with empty string"""
        cards = Deck.parse_board('')
        assert len(cards) == 0


class TestDeckConstants:
    """Tests for deck module constants"""

    def test_ranks_has_13_elements(self):
        """Test RANKS has 13 elements"""
        assert len(RANKS) == 13
        assert '2' in RANKS
        assert 'A' in RANKS

    def test_suits_has_4_elements(self):
        """Test SUITS has 4 elements"""
        assert len(SUITS) == 4
        assert 'h' in SUITS
        assert 'd' in SUITS
        assert 'c' in SUITS
        assert 's' in SUITS
