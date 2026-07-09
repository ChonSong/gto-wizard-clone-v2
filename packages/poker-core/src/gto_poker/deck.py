"""Deck utilities for poker"""

from typing import List
import random

RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A"]
SUITS = ["h", "d", "c", "s"]  # hearts, diamonds, clubs, spades

# Rank indices for comparison — A is high (12), 2 is low (0)
RANK_ORDER = {r: i for i, r in enumerate(RANKS)}  # 2=0, 3=1, ..., A=12


class Card:
    """Single playing card"""
    
    def __init__(self, rank: str, suit: str):
        self.rank = rank.upper()
        self.suit = suit.lower()
        if self.rank not in RANKS:
            raise ValueError(f"Invalid rank: {rank}")
        if self.suit not in SUITS:
            raise ValueError(f"Invalid suit: {suit}")
    
    @property
    def index(self) -> int:
        """0-51 card index"""
        return RANKS.index(self.rank) * 4 + SUITS.index(self.suit)
    
    @property
    def rank_index(self) -> int:
        """0-12 rank index (2=0, A=12)"""
        return RANK_ORDER[self.rank]
    
    def __str__(self):
        return f"{self.rank}{self.suit}"
    
    def __repr__(self):
        return f"Card('{self.rank}', '{self.suit}')"
    
    def __eq__(self, other):
        return self.rank == other.rank and self.suit == other.suit
    
    def __hash__(self):
        return hash((self.rank, self.suit))


class Deck:
    """Standard 52-card deck"""
    
    def __init__(self):
        self._cards = [Card(r, s) for s in SUITS for r in RANKS]
    
    def shuffle(self, seed: int = None):
        if seed is not None:
            random.seed(seed)
        random.shuffle(self._cards)
    
    def draw(self, n: int = 1) -> List[Card]:
        """Draw n cards from top of deck"""
        if n > len(self._cards):
            raise ValueError(f"Cannot draw {n} cards from deck of {len(self._cards)}")
        cards = self._cards[:n]
        self._cards = self._cards[n:]
        return cards
    
    def draw_one(self) -> Card:
        """Draw single card"""
        return self.draw(1)[0]
    
    def reset(self):
        """Reset deck to full 52 cards"""
        self._cards = [Card(r, s) for s in SUITS for r in RANKS]
    
    def __len__(self):
        return len(self._cards)
    
    def __iter__(self):
        return iter(self._cards)
    
    @staticmethod
    def parse(card_str: str) -> Card:
        """Parse card string like 'Ad', 'Th', '7c'"""
        if len(card_str) != 2:
            raise ValueError(f"Invalid card string: {card_str}")
        return Card(card_str[0], card_str[1])
    
    @staticmethod
    def parse_board(board_str: str) -> List[Card]:
        """Parse board string like 'Kd7h2c' or 'Kd,7h,2c'"""
        board_str = board_str.replace(",", "")
        if len(board_str) % 2 != 0:
            raise ValueError(f"Invalid board string: {board_str}")
        return [Deck.parse(board_str[i:i+2]) for i in range(0, len(board_str), 2)]