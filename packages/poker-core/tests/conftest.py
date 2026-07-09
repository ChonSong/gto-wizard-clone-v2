"""Pytest fixtures for poker-core tests"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gto_poker.deck import Card, Deck, RANKS, SUITS
from gto_poker.hand import Hand


@pytest.fixture
def sample_deck():
    """A fresh 52-card deck"""
    return Deck()


@pytest.fixture
def shuffled_deck():
    """A deterministically shuffled deck"""
    d = Deck()
    d.shuffle(seed=42)
    return d


@pytest.fixture
def ah():
    """Ace of hearts"""
    return Card('A', 'h')


@pytest.fixture
def kh():
    """King of hearts"""
    return Card('K', 'h')


@pytest.fixture
def ad():
    """Ace of diamonds"""
    return Card('A', 'd')


@pytest.fixture
def kd():
    """King of diamonds"""
    return Card('K', 'd')


@pytest.fixture
def qh():
    """Queen of hearts"""
    return Card('Q', 'h')


@pytest.fixture
def jh():
    """Jack of hearts"""
    return Card('J', 'h')


@pytest.fixture
def th():
    """Ten of hearts"""
    return Card('T', 'h')


@pytest.fixture
def board_flop():
    """Sample flop: Kd, 7h, 2c"""
    return [Card('K', 'd'), Card('7', 'h'), Card('2', 'c')]


@pytest.fixture
def board_turn(board_flop):
    """Sample turn: Kd, 7h, 2c, 9s"""
    return board_flop + [Card('9', 's')]


@pytest.fixture
def board_river(board_turn):
    """Sample river: Kd, 7h, 2c, 9s, 3d"""
    return board_turn + [Card('3', 'd')]


@pytest.fixture
def straight_flush_cards():
    """Cards that make a straight flush: 9h, Th, Jh, Qh, Kh"""
    return [Card('9', 'h'), Card('T', 'h'), Card('J', 'h'), Card('Q', 'h'), Card('K', 'h')]


@pytest.fixture
def four_of_a_kind_cards():
    """Cards that make four of a kind: As, Ad, Ac, Ah, Kd"""
    return [Card('A', 's'), Card('A', 'd'), Card('A', 'c'), Card('A', 'h'), Card('K', 'd')]


@pytest.fixture
def full_house_cards():
    """Cards that make a full house: As, Ad, Ac, Ks, Kd"""
    return [Card('A', 's'), Card('A', 'd'), Card('A', 'c'), Card('K', 's'), Card('K', 'd')]


@pytest.fixture
def flush_cards():
    """Cards that make a flush: Ah, Kh, Qh, 9h, 3h"""
    return [Card('A', 'h'), Card('K', 'h'), Card('Q', 'h'), Card('9', 'h'), Card('3', 'h')]


@pytest.fixture
def straight_cards():
    """Cards that make a straight: 9s, Th, Jc, Qd, Kh"""
    return [Card('9', 's'), Card('T', 'h'), Card('J', 'c'), Card('Q', 'd'), Card('K', 'h')]


@pytest.fixture
def ace_low_straight_cards():
    """Cards that make ace-low straight: A, 2, 3, 4, 5"""
    return [Card('A', 'h'), Card('2', 'd'), Card('3', 'c'), Card('4', 's'), Card('5', 'h')]


@pytest.fixture
def three_of_a_kind_cards():
    """Cards that make three of a kind: As, Ad, Ac, Kd, Qh"""
    return [Card('A', 's'), Card('A', 'd'), Card('A', 'c'), Card('K', 'd'), Card('Q', 'h')]


@pytest.fixture
def two_pair_cards():
    """Cards that make two pair: As, Ad, Kc, Kh, Qh"""
    return [Card('A', 's'), Card('A', 'd'), Card('K', 'c'), Card('K', 'h'), Card('Q', 'h')]


@pytest.fixture
def one_pair_cards():
    """Cards that make one pair: As, Ad, Kc, Qh, Jd"""
    return [Card('A', 's'), Card('A', 'd'), Card('K', 'c'), Card('Q', 'h'), Card('J', 'd')]


@pytest.fixture
def high_card_cards():
    """High card hand: A, K, Q, J, 9 different suits"""
    return [Card('A', 's'), Card('K', 'd'), Card('Q', 'h'), Card('J', 'c'), Card('9', 's')]


@pytest.fixture
def six_card_hand():
    """6-card hand for testing 6-card hands"""
    return [Card('A', 's'), Card('A', 'd'), Card('A', 'c'), Card('K', 'd'), Card('K', 'c'), Card('Q', 'h')]


@pytest.fixture
def seven_card_hand():
    """7-card hand for testing 7-card hands"""
    return [Card('A', 's'), Card('A', 'd'), Card('A', 'c'), Card('K', 'd'), Card('K', 'c'), Card('Q', 'h'), Card('J', 'd')]
