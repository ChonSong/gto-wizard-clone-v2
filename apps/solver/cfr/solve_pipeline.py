"""
Multi-street GTO Solve Pipeline

Orchestrates solving across multiple streets (flop -> turn -> river) with proper
state management and chance sampling at each street. Supports partial solves
(e.g., just flop, or flop+turn).

Usage:
    from cfr.solve_pipeline import SolvePipeline, SolveConfig, Street
    config = SolveConfig.flop_only()
    pipeline = SolvePipeline(game_type="holdem", config=config)
    result = pipeline.solve(starting_street=Street.FLOP, streets=[Street.FLOP])
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple, Any, Callable
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class Street(Enum):
    """Poker streets in order."""
    PREFLOP = auto()
    FLOP = auto()
    TURN = auto()
    RIVER = auto()


STREETS_IN_ORDER = [Street.FLOP, Street.TURN, Street.RIVER]


@dataclass
class TurnTicket:
    """Represents a turn card outcome for chance sampling."""
    card: str  # e.g., "Th", "7d"
    weight: float = 1.0


@dataclass
class RiverTicket:
    """Represents a river card outcome for chance sampling."""
    card: str
    weight: float = 1.0


@dataclass
class FlopTicket:
    """Represents a flop outcome for chance sampling."""
    cards: Tuple[str, str, str]  # e.g., ("Kh", "Qs", "2c")
    weight: float = 1.0


@dataclass
class StreetState:
    """Immutable state for a single street."""
    street: Street
    board: Tuple[str, ...]  # e.g., ("Kh", "Qs", "2c") for flop, +1 turn, +1 river
    pot: float
    effective_stack: float  # effective stack
    acting_order: Tuple[int, ...]  # player indices in order
    current_player: int
    terminal: bool = False
    actions_so_far: Tuple[str, ...] = field(default_factory=tuple)


@dataclass
class MultiStreetState:
    """Full game state across all streets."""
    # Starting conditions
    game_type: str
    initial_pot: float
    effective_stack: float
    player_range_sizes: Tuple[int, int]  # number of combos per player
    
    # Street progression
    streets_completed: List[Street] = field(default_factory=list)
    current_street: Street = Street.PREFLOP
    
    # Resolved chance outcomes (flop -> turn -> river)
    flop_cards: Optional[Tuple[str, str, str]] = None
    turn_card: Optional[str] = None
    river_card: Optional[str] = None
    
    # Strategy trees by street (populated as we solve)
    flop_tree: Optional[Any] = None
    turn_tree: Optional[Any] = None
    river_tree: Optional[Any] = None
    
    # Cumulative strategy (merged from all streets)
    merged_strategy: Optional[Dict] = None
    
    @property
    def board(self) -> Tuple[str, ...]:
        """Current board cards based on street progress."""
        if self.current_street == Street.FLOP:
            return self.flop_cards or ()
        elif self.current_street == Street.TURN:
            return (self.flop_cards + (self.turn_card,)) if self.flop_cards else ()
        elif self.current_street == Street.RIVER:
            return (self.flop_cards + (self.turn_card, self.river_card)) if self.flop_cards else ()
        return ()
    
    def is_terminal(self) -> bool:
        return self.current_street == Street.RIVER and self.river_card is not None


@dataclass
class SolveConfig:
    """Configuration for the solve pipeline."""
    # CFR parameters
    cfr_iters: int = 500
    cfr_batch_size: int = 100
    cfr_convergence_threshold: float = 0.0001
    cfr_trickle_reset_threshold: float = 0.001
    
    # Chance sampling
    num_flop_samples: int = 1  # typically 1 for full-game solving
    num_turn_samples: int = 1
    num_river_samples: int = 1
    chance_sampling_mode: str = "exact"  # "exact" | "importance" | "both"
    
    # Street options
    solve_preflop: bool = False  # If True, solve preflop first
    street_stoporders: Dict[Street, int] = field(default_factory=lambda: {
        Street.FLOP: 50,
        Street.TURN: 50,
        Street.RIVER: 50,
    })
    
    # Partial solve options
    starting_street: Street = Street.FLOP
    streets_to_solve: List[Street] = field(default_factory=lambda: [Street.FLOP, Street.TURN, Street.RIVER])
    
    # Output options
    save_trees: bool = True
    checkpoint_frequency: int = 100
    
    @classmethod
    def flop_only(cls) -> "SolveConfig":
        """Config for solving only the flop."""
        return cls(starting_street=Street.FLOP, streets_to_solve=[Street.FLOP])
    
    @classmethod
    def flop_turn_only(cls) -> "SolveConfig":
        """Config for solving flop + turn."""
        return cls(starting_street=Street.FLOP, streets_to_solve=[Street.FLOP, Street.TURN])
    
    @classmethod
    def full_game(cls) -> "SolveConfig":
        """Config for solving the full game (flop + turn + river)."""
        return cls(starting_street=Street.FLOP, streets_to_solve=[Street.FLOP, Street.TURN, Street.RIVER])


class ChanceSampler(ABC):
    """Abstract base for chance sampling strategies."""
    
    @abstractmethod
    def sample_flop(self, deck: List[str], board_type: Optional[str] = None) -> List[FlopTicket]:
        """Sample flop outcomes."""
        pass
    
    @abstractmethod
    def sample_turn(self, deck: List[str], known_board: Tuple[str, ...]) -> List[TurnTicket]:
        """Sample turn outcomes."""
        pass
    
    @abstractmethod
    def sample_river(self, deck: List[str], known_board: Tuple[str, ...]) -> List[RiverTicket]:
        """Sample river outcomes."""
        pass


class ExactChanceSampler(ChanceSampler):
    """
    Exact chance sampling - enumerate all possible cards.
    Used when solving single streets or when importance sampling isn't needed.
    """
    
    def __init__(self, ignore_first_card: bool = False):
        self.ignore_first_card = ignore_first_card
    
    def sample_flop(self, deck: List[str], board_type: Optional[str] = None) -> List[FlopTicket]:
        """Sample all possible flops (or a subset for importance sampling)."""
        all_flops = self._enumerate_all_flops(deck)
        
        if board_type == "dry":
            return all_flops[:1]  # Just one dry flop
        elif board_type == "wet":
            # Could filter for wet boards; for now return all
            return all_flops
        
        return all_flops
    
    def _enumerate_all_flops(self, deck: List[str]) -> List[FlopTicket]:
        """Enumerate all possible flops from remaining deck."""
        flops = []
        seen = set()
        
        for i, c1 in enumerate(deck):
            for j, c2 in enumerate(deck[i+1:], i+1):
                for k, c3 in enumerate(deck[j+1:], j+1):
                    # Sort for canonical ordering
                    sorted_cards = tuple(sorted([c1, c2, c3], key=self._card_rank))
                    if sorted_cards not in seen:
                        seen.add(sorted_cards)
                        flops.append(FlopTicket(cards=sorted_cards))
        
        return flops
    
    def _card_rank(self, card: str) -> int:
        """Get numeric rank for sorting."""
        ranks = "23456789TJQKA"
        return ranks.index(card[0])
    
    def sample_turn(self, deck: List[str], known_board: Tuple[str, ...]) -> List[TurnTicket]:
        """Sample all possible turn cards."""
        remaining = [c for c in deck if c not in known_board]
        return [TurnTicket(card=c) for c in remaining]
    
    def sample_river(self, deck: List[str], known_board: Tuple[str, ...]) -> List[RiverTicket]:
        """Sample all possible river cards."""
        remaining = [c for c in deck if c not in known_board]
        return [RiverTicket(card=c) for c in remaining]


class ImportanceChanceSampler(ChanceSampler):
    """
    Importance sampling for chance nodes - focuses on relevant outcomes.
    Uses equity weighting to sample more important lines more often.
    """
    
    def __init__(self, equity_model, num_samples: int = 10):
        self.equity_model = equity_model
        self.num_samples = num_samples
    
    def sample_flop(self, deck: List[str], board_type: Optional[str] = None) -> List[FlopTicket]:
        """Sample flops using importance sampling based on equity differences."""
        all_flops = self._enumerate_all_flops(deck)
        
        if len(all_flops) <= self.num_samples:
            return all_flops
        
        # Weight by equity variance (simplified - just return random subset)
        sampled = random.sample(all_flops, self.num_samples)
        return [FlopTicket(cards=fc.cards, weight=1.0/self.num_samples) for fc in sampled]
    
    def _enumerate_all_flops(self, deck: List[str]) -> List[FlopTicket]:
        """Enumerate all possible flops."""
        flops = []
        for i, c1 in enumerate(deck):
            for j, c2 in enumerate(deck[i+1:], i+1):
                for k, c3 in enumerate(deck[j+1:], j+1):
                    flops.append(FlopTicket(cards=(c1, c2, c3)))
        return flops
    
    def sample_turn(self, deck: List[str], known_board: Tuple[str, ...]) -> List[TurnTicket]:
        """Sample turn cards."""
        remaining = [c for c in deck if c not in known_board]
        
        if len(remaining) <= self.num_samples:
            return [TurnTicket(card=c) for c in remaining]
        
        sampled = random.sample(remaining, self.num_samples)
        return [TurnTicket(card=c, weight=1.0/self.num_samples) for c in sampled]
    
    def sample_river(self, deck: List[str], known_board: Tuple[str, ...]) -> List[RiverTicket]:
        """Sample river cards."""
        remaining = [c for c in deck if c not in known_board]
        
        if len(remaining) <= self.num_samples:
            return [RiverTicket(card=c) for c in remaining]
        
        sampled = random.sample(remaining, self.num_samples)
        return [RiverTicket(card=c, weight=1.0/self.num_samples) for c in sampled]


class StreetSolver(ABC):
    """Abstract base for street-specific solvers."""
    
    @abstractmethod
    def solve_street(
        self,
        state: MultiStreetState,
        config: SolveConfig,
    ) -> Any:
        """Solve a single street, returning the strategy tree."""
        pass


class CFREngine:
    """
    CFR (Counterfactual Regret Minimization) engine for solving poker streets.
    
    This is a simplified reference implementation. Production implementations
    would use numba/jit compilation and specialized game tree structures.
    """
    
    def __init__(self, game_type: str = "holdem"):
        self.game_type = game_type
        self._node_cache: Dict[str, Any] = {}
    
    def create_root_node(
        self,
        state: MultiStreetState,
        acting_player: int,
    ) -> Any:
        """Create root node for CFR solving."""
        return {
            "type": "root",
            "street": state.current_street,
            "board": state.board,
            "acting_player": acting_player,
            "actions": [],
            "children": {},
        }
    
    def cfr_iteration(
        self,
        node: Dict,
        reach_probabilities: Tuple[float, float],
        state: MultiStreetState,
    ) -> Tuple[float, float]:
        """
        Run one iteration of CFR.
        
        Returns (utility_p1, utility_p2) tuple.
        """
        # Simplified - actual implementation would traverse game tree
        return 0.0, 0.0
    
    def run_cfr(
        self,
        root_node: Dict,
        state: MultiStreetState,
        config: SolveConfig,
        progress_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """
        Run CFR to convergence.
        
        Returns strategy dictionary with action probabilities.
        """
        iters = config.cfr_iters
        
        for i in range(iters):
            self.cfr_iteration(root_node, (1.0, 1.0), state)
            
            if progress_callback and i % config.checkpoint_frequency == 0:
                progress_callback(i, iters)
            
            if i > 0 and i % 100 == 0:
                logger.debug(f"CFR iteration {i}/{iters}")
        
        return self._extract_strategy(root_node)
    
    def _extract_strategy(self, node: Dict) -> Dict[str, Any]:
        """Extract average strategy from a node."""
        return {"actions": {}, "utils": (0.0, 0.0)}


class SolvePipeline:
    """
    Multi-street GTO solve pipeline.
    
    Orchestrates solving across streets with proper state management,
    chance sampling, and strategy merging.
    
    Example:
        >>> config = SolveConfig.full_game()
        >>> pipeline = SolvePipeline(game_type="holdem", config=config)
        >>> result = pipeline.solve(
        ...     initial_pot=100.0,
        ...     effective_stack=1000.0,
        ...     player_range_sizes=(169, 169),
        ... )
        >>> print(f"Flop EV: {result.flop_ev}")
    """
    
    def __init__(
        self,
        game_type: str = "holdem",
        config: Optional[SolveConfig] = None,
        solver: Optional[CFREngine] = None,
        sampler: Optional[ChanceSampler] = None,
    ):
        self.game_type = game_type
        self.config = config or SolveConfig()
        self.solver = solver or CFREngine(game_type)
        self.sampler = sampler or ExactChanceSampler()
        
        self._checkpoints: List[MultiStreetState] = []
        self._last_progress_check: float = 0.0
    
    def solve(
        self,
        initial_pot: float,
        effective_stack: float,
        player_range_sizes: Tuple[int, int],
        preflop_tree: Optional[Dict] = None,
        progress_callback: Optional[callable] = None,
    ) -> "SolveResult":
        """
        Run the full solve pipeline.
        
        Args:
            initial_pot: Starting pot size in chips
            effective_stack: Effective stack depth
            player_range_sizes: (p1_combos, p2_combos)
            preflop_tree: Optional preflop strategy tree to start from
            progress_callback: Optional callback(street, completed_iters, total_iters)
        
        Returns:
            SolveResult with strategy trees and EVs
        """
        # Initialize state
        state = MultiStreetState(
            game_type=self.game_type,
            initial_pot=initial_pot,
            effective_stack=effective_stack,
            player_range_sizes=player_range_sizes,
            current_street=self.config.starting_street,
        )
        
        logger.info(f"Starting multi-street solve: {self.config.streets_to_solve}")
        logger.info(f"Starting street: {self.config.starting_street}")
        logger.info(f"Initial pot: {initial_pot}, stack: {effective_stack}")
        
        # Solve each requested street
        all_strategies = {}
        
        for street in self.config.streets_to_solve:
            street_idx = STREET_ORDERING.index(street)
            logger.info(f"Solving street {street.name} (index {street_idx})")
            
            if progress_callback:
                progress_callback(street, 0, self.config.cfr_iters)
            
            street_result = self._solve_street(
                state,
                preflop_tree if street == Street.FLOP else None,
                progress_callback,
            )
            
            # Store strategy tree
            all_strategies[street.name.lower()] = street_result.strategy_tree
            
            # Advance state for next street
            state = self._advance_to_next_street(state, street_result)
            
    def _create_deck(self) -> List[str]:
        """Create a standard 52-card deck."""
        ranks = "23456789TJQKA"
        suits = ["c", "d", "h", "s"]
        return [r + s for r in ranks for s in suits]
    
    def _solve_street(
        self,
        state: MultiStreetState,
        preflop_tree: Optional[Dict],
        progress_callback: Optional[callable],
    ) -> "StreetSolveResult":
        """Solve a single street."""
        deck = self._create_deck()
        
        if state.current_street == Street.FLOP:
            return self._solve_flop(state, deck, preflop_tree, progress_callback)
        elif state.current_street == Street.TURN:
            return self._solve_turn(state, deck, progress_callback)
        elif state.current_street == Street.RIVER:
            return self._solve_river(state, deck, progress_callback)
        else:
            raise ValueError(f"Unknown street: {state.current_street}")
    
    def _solve_flop(
        self,
        state: MultiStreetState,
        deck: List[str],
        preflop_tree: Optional[Dict],
        progress_callback: Optional[callable],
    ) -> "StreetSolveResult":
        """Solve the flop street."""
        logger.info("Starting flop solve")
        
        # Sample flop outcomes
        flop_tickets = self.sampler.sample_flop(deck)
        logger.info(f"Sampling {len(flop_tickets)} flop outcomes")
        
        total_ev_p1 = 0.0
        total_ev_p2 = 0.0
        strategy_trees = []
        
        for idx, flop_ticket in enumerate(flop_tickets):
            logger.debug(f"Flop {idx+1}/{len(flop_tickets)}: {flop_ticket.cards}")
            
            # Update state with flop
            state.flop_cards = flop_ticket.cards
            
            # Create root node and solve
            root = self.solver.create_root_node(
                state=state,
                acting_player=0,  # P1 acts first on flop (typical)
            )
            
            strategy = self.solver.run_cfr(
                root_node=root,
                state=state,
                config=self.config,
                progress_callback=None,
            )
            
            # Track weighted EV
            ev_p1, ev_p2 = self._calculate_street_ev(strategy, state)
            total_ev_p1 += ev_p1 * flop_ticket.weight
            total_ev_p2 += ev_p2 * flop_ticket.weight
            
            strategy_trees.append({
                "flop": flop_ticket.cards,
                "strategy": strategy,
                "weight": flop_ticket.weight,
            })
        
        return StreetSolveResult(
            street=Street.FLOP,
            strategy_tree={"type": "flop_root", "children": strategy_trees},
            ev_p1=total_ev_p1,
            ev_p2=total_ev_p2,
            chance_outcomes=flop_tickets,
        )
    
    def _solve_turn(
        self,
        state: MultiStreetState,
        deck: List[str],
        progress_callback: Optional[callable],
    ) -> "StreetSolveResult":
        """Solve the turn street."""
        logger.info("Starting turn solve")
        
        if state.flop_cards is None:
            raise ValueError("Flop must be resolved before turn")
        
        # Sample turn outcomes
        turn_tickets = self.sampler.sample_turn(deck, state.flop_cards)
        logger.info(f"Sampling {len(turn_tickets)} turn outcomes")
        
        total_ev_p1 = 0.0
        total_ev_p2 = 0.0
        strategy_trees = []
        
        for idx, turn_ticket in enumerate(turn_tickets):
            logger.debug(f"Turn {idx+1}/{len(turn_tickets)}: {turn_ticket.card}")
            
            # Update state with turn
            state.turn_card = turn_ticket.card
            
            # Run CFR for this turn card
            root = self.solver.create_root_node(
                state=state,
                acting_player=0,
            )
            
            strategy = self.solver.run_cfr(
                root_node=root,
                state=state,
                config=self.config,
                progress_callback=None,
            )
            
            ev_p1, ev_p2 = self._calculate_street_ev(strategy, state)
            total_ev_p1 += ev_p1 * turn_ticket.weight
            total_ev_p2 += ev_p2 * turn_ticket.weight
            
            strategy_trees.append({
                "turn": turn_ticket.card,
                "strategy": strategy,
                "weight": turn_ticket.weight,
            })
        
        return StreetSolveResult(
            street=Street.TURN,
            strategy_tree={"type": "turn_root", "children": strategy_trees},
            ev_p1=total_ev_p1,
            ev_p2=total_ev_p2,
            chance_outcomes=turn_tickets,
        )
    
    def _solve_river(
        self,
        state: MultiStreetState,
        deck: List[str],
        progress_callback: Optional[callable],
    ) -> "StreetSolveResult":
        """Solve the river street."""
        logger.info("Starting river solve")
        
        if state.turn_card is None:
            raise ValueError("Turn must be resolved before river")
        if state.flop_cards is None:
            raise ValueError("Flop must be resolved before river")
        
        # Sample river outcomes
        river_tickets = self.sampler.sample_river(
            deck, 
            state.flop_cards + (state.turn_card,)
        )
        logger.info(f"Sampling {len(river_tickets)} river outcomes")
        
        total_ev_p1 = 0.0
        total_ev_p2 = 0.0
        strategy_trees = []
        
        for idx, river_ticket in enumerate(river_tickets):
            logger.debug(f"River {idx+1}/{len(river_tickets)}: {river_ticket.card}")
            
            # Update state with river
            state.river_card = river_ticket.card
            
            # Solve river (terminal street)
            root = self.solver.create_root_node(
                state=state,
                acting_player=0,
            )
            
            strategy = self.solver.run_cfr(
                root_node=root,
                state=state,
                config=self.config,
                progress_callback=None,
            )
            
            ev_p1, ev_p2 = self._calculate_street_ev(strategy, state)
            total_ev_p1 += ev_p1 * river_ticket.weight
            total_ev_p2 += ev_p2 * river_ticket.weight
            
            strategy_trees.append({
                "river": river_ticket.card,
                "strategy": strategy,
                "weight": river_ticket.weight,
            })
        
        return StreetSolveResult(
            street=Street.RIVER,
            strategy_tree={"type": "river_root", "children": strategy_trees},
            ev_p1=total_ev_p1,
            ev_p2=total_ev_p2,
            chance_outcomes=river_tickets,
        )
    
    def _advance_to_next_street(
        self,
        state: MultiStreetState,
        result: "StreetSolveResult",
    ) -> MultiStreetState:
        """Advance state to the next street after solving."""
        # Store completed street info
        state.streets_completed.append(result.street)
        
        # Reset chance outcomes from previous street
        # (they become part of the board for next street)
        
        if result.street == Street.FLOP:
            state.flop_tree = result.strategy_tree
        elif result.street == Street.TURN:
            state.turn_tree = result.strategy_tree
        elif result.street == Street.RIVER:
            state.river_tree = result.strategy_tree
        
        # Advance current street
        if result.street == Street.FLOP and Street.TURN in self.config.streets_to_solve:
            state.current_street = Street.TURN
            state.turn_card = None
        elif result.street == Street.TURN and Street.RIVER in self.config.streets_to_solve:
            state.current_street = Street.RIVER
            state.river_card = None
        
        return state
    
    def _calculate_street_ev(
        self,
        strategy: Dict,
        state: MultiStreetState,
    ) -> Tuple[float, float]:
        """Calculate expected value for a street strategy."""
        # Simplified - actual implementation would traverse strategy tree
        return (0.0, 0.0)
    
    def get_strategy_summary(self, result: "SolveResult") -> Dict[str, Any]:
        """Get a human-readable strategy summary."""
        summary = {}
        
        for street_name, tree in result.strategy_trees.items():
            summary[street_name] = {
                "num_nodes": self._count_nodes(tree),
                "ev_p1": result.ev_by_street.get(street_name, {}).get("p1", 0.0),
                "ev_p2": result.ev_by_street.get(street_name, {}).get("p2", 0.0),
            }
        
        return summary
    
    def _count_nodes(self, tree: Dict) -> int:
        """Count total nodes in a strategy tree."""
        if not tree or "children" not in tree:
            return 0
        
        count = 1
        for child in tree["children"].values():
            if isinstance(child, dict):
                count += self._count_nodes(child)
        
        return count


# Immutable result classes
@dataclass(frozen=True)
class StreetSolveResult:
    """Result from solving a single street."""
    street: Street
    strategy_tree: Dict[str, Any]
    ev_p1: float
    ev_p2: float
    chance_outcomes: Tuple[Any, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SolveResult:
    """
    Final result from the full solve pipeline.
    
    Contains strategy trees for each solved street, overall EVs,
    and metadata about the solve.
    """
    strategy_trees: Dict[str, Dict[str, Any]]
    ev_by_street: Dict[str, Dict[str, float]]
    total_flop_ev_p1: float
    total_flop_ev_p2: float
    solve_config: SolveConfig
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def flop_ev(self) -> Tuple[float, float]:
        return (self.total_flop_ev_p1, self.total_flop_ev_p2)


# Internal ordering for street validation
STREET_ORDERING = [Street.FLOP, Street.TURN, Street.RIVER]


# Convenience factory functions
def create_flop_only_pipeline(
    game_type: str = "holdem",
    cfr_iters: int = 500,
) -> SolvePipeline:
    """Create a pipeline that solves only the flop."""
    config = SolveConfig(
        starting_street=Street.FLOP,
        streets_to_solve=[Street.FLOP],
        cfr_iters=cfr_iters,
    )
    return SolvePipeline(game_type=game_type, config=config)


def create_flop_turn_pipeline(
    game_type: str = "holdem",
    cfr_iters: int = 500,
) -> SolvePipeline:
    """Create a pipeline that solves flop + turn."""
    config = SolveConfig(
        starting_street=Street.FLOP,
        streets_to_solve=[Street.FLOP, Street.TURN],
        cfr_iters=cfr_iters,
    )
    return SolvePipeline(game_type=game_type, config=config)


def create_full_game_pipeline(
    game_type: str = "holdem",
    cfr_iters: int = 500,
) -> SolvePipeline:
    """Create a pipeline that solves the full game (flop + turn + river)."""
    config = SolveConfig(
        starting_street=Street.FLOP,
        streets_to_solve=[Street.FLOP, Street.TURN, Street.RIVER],
        cfr_iters=cfr_iters,
    )
    return SolvePipeline(game_type=game_type, config=config)
