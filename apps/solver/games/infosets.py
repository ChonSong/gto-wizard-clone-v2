"""
Infoset (Information Set) management for CFR.

An information set groups game states that a player cannot distinguish,
meaning they have the same available actions and same information.
"""

from typing import Dict, List, Optional
import numpy as np


class InfoSet:
    """
    Information set for imperfect recall poker.
    
    An infoset represents all states that a player considers indistinguishable.
    Key format: "player:board:pot:stack:action_history"
    """
    
    def __init__(self, key: str, actions: List[str]):
        self.key = key
        self.actions = actions
        self.n_actions = len(actions)
        
        # Action indices
        self.action_index = {a: i for i, a in enumerate(actions)}
        
        # Cumulative regrets (for regret matching)
        self.regret_sum = np.zeros(self.n_actions, dtype=np.float64)
        
        # Cumulative strategy (for averaging)
        self.strategy_sum = np.zeros(self.n_actions, dtype=np.float64)
        
        # Current strategy (computed on-demand via regret matching)
        self._current_strategy: Optional[np.ndarray] = None
        self._strategy_version = 0
    
    def get_strategy(self) -> np.ndarray:
        """
        Get current strategy via regret matching.
        
        Returns probability distribution over actions.
        """
        # Use regret matching to compute strategy
        strategy = regret_match(self.regret_sum)
        self._current_strategy = strategy
        return strategy
    
    def get_average_strategy(self) -> np.ndarray:
        """
        Get average strategy across all iterations.
        
        Returns normalized strategy sum.
        """
        return normalize_strategy(self.strategy_sum)
    
    def update_regrets(self, action_utilities: np.ndarray, strategy: np.ndarray, realization_weight: float):
        """
        Update regrets based on counterfactual values.
        
        Args:
            action_utilities: Utility of each action
            strategy: Current strategy probabilities
            realization_weight: Weight for this traverser's contribution
        """
        # Counterfactual regret: how much better is each action than the current strategy
        cf_value = np.dot(strategy, action_utilities)  # Expected value under current strategy
        regrets = action_utilities - cf_value  # Regret for each action
        
        # Accumulate positive regrets
        self.regret_sum += np.maximum(regrets, 0) * realization_weight
        
        # Accumulate strategy for averaging
        self.strategy_sum += strategy * realization_weight
    
    def __repr__(self):
        avg_strat = self.get_average_strategy()
        action_strs = [f"{a}:{avg_strat[i]:.2f}" for i, a in enumerate(self.actions)]
        return f"InfoSet({self.key[:30]}, [{', '.join(action_strs)}])"


def regret_match(regrets: np.ndarray) -> np.ndarray:
    """
    Compute strategy via regret matching.
    
    Args:
        regrets: Cumulative regret for each action
        
    Returns:
        Probability distribution over actions
    """
    n = len(regrets)
    if n == 0:
        return np.array([])
    
    # Positive regrets
    pos_regrets = np.maximum(regrets, 0)
    
    # If all regrets are zero or negative, uniform random
    if np.sum(pos_regrets) <= 0:
        return np.ones(n) / n
    
    # Regret matching: probability proportional to positive regret
    return pos_regrets / np.sum(pos_regrets)


def normalize_strategy(strategy_sum: np.ndarray) -> np.ndarray:
    """
    Normalize strategy sum to probability distribution.
    
    Args:
        strategy_sum: Cumulative strategy probabilities
        
    Returns:
        Normalized probability distribution
    """
    total = np.sum(strategy_sum)
    if total <= 0:
        n = len(strategy_sum)
        return np.ones(n) / n if n > 0 else np.array([])
    return strategy_sum / total


class InfoSetManager:
    """
    Manages all information sets in the game.
    
    Provides lookup and creation of infosets.
    """
    
    def __init__(self):
        self.infosets: Dict[str, InfoSet] = {}
    
    def get_or_create(self, key: str, actions: List[str]) -> InfoSet:
        """
        Get existing infoset or create new one.
        
        Args:
            key: Unique identifier for the infoset
            actions: Available actions at this infoset
            
        Returns:
            InfoSet object
        """
        if key not in self.infosets:
            self.infosets[key] = InfoSet(key, actions)
        else:
            # Verify actions match
            existing = self.infosets[key]
            if set(existing.actions) != set(actions):
                raise ValueError(f"Actions mismatch for infoset {key}: {actions} vs {existing.actions}")
        return self.infosets[key]
    
    def get(self, key: str) -> Optional[InfoSet]:
        """Get infoset by key if it exists."""
        return self.infosets.get(key)
    
    def all_infosets(self) -> List[InfoSet]:
        """Get all infosets."""
        return list(self.infosets.values())
    
    def __len__(self):
        return len(self.infosets)
