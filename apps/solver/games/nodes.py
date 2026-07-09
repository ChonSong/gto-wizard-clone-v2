"""
Game tree nodes for imperfect-information poker game tree.

Node types:
- ActionNode: Player decision point (fold/call/raise)
- ChanceNode: Card dealing nodes (stochastic)
- TerminalNode: Terminal payoffs (showdown or fold)

Each node stores an infoset_key for imperfect recall grouping.
"""

from enum import Enum
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


class NodeType(Enum):
    ACTION = "action"       # Player decision
    CHANCE = "chance"       # Card dealing
    TERMINAL = "terminal"   # Game over


@dataclass
class Node:
    """Base class for all game tree nodes."""
    
    infoset_key: str = ""  # For imperfect recall grouping
    node_type: NodeType = NodeType.ACTION
    parent: Optional["Node"] = None
    children: Dict[str, "Node"] = field(default_factory=dict)  # action -> child
    
    # Player to act (0 or 1 for 2-player, -1 for chance/terminal)
    player: int = -1
    
    def is_terminal(self) -> bool:
        return self.node_type == NodeType.TERMINAL
    
    def is_chance(self) -> bool:
        return self.node_type == NodeType.CHANCE
    
    def is_action(self) -> bool:
        return self.node_type == NodeType.ACTION


@dataclass
class ActionNode(Node):
    """Player decision point with available actions."""
    
    available_actions: List[str] = field(default_factory=list)
    node_type: NodeType = NodeType.ACTION
    
    def __post_init__(self):
        pass  # node_type already set via field default


@dataclass 
class ChanceNode(Node):
    """Stochastic node for card dealing."""
    
    # Cards that have been dealt at this point
    dealt_cards: List[str] = field(default_factory=list)
    
    # Distribution of outcomes (for sampling)
    outcomes: List[Any] = field(default_factory=list)
    outcome_probs: List[float] = field(default_factory=list)
    
    node_type: NodeType = NodeType.CHANCE
    
    def __post_init__(self):
        pass  # node_type already set via field default


@dataclass
class TerminalNode(Node):
    """Terminal game state with payoffs."""
    
    # Payoff for each player (positive = win, negative = loss)
    payoffs: List[float] = field(default_factory=lambda: [0.0, 0.0])
    
    # Terminal reason: "showdown", "fold", "all_in"
    terminal_reason: str = "showdown"
    
    node_type: NodeType = NodeType.TERMINAL
    
    def __post_init__(self):
        pass  # node_type already set via field default


class GameTreeBuilder:
    """Builds game tree for Texas Hold'em."""
    
    def __init__(self, game: "TexasHoldEm"):
        self.game = game
    
    def build_river_tree(
        self, 
        p0_hand: List[str],
        p1_hand: List[str],
        board: List[str],
        pot: float,
        stacks: List[float],
        action_history: List[Any] = None
    ) -> Node:
        """
        Build a partial river game tree given known cards.
        
        For river solver: we start at the river (5 cards on board),
        with known hole cards for both players.
        
        Returns:
            Root Node of the game tree with children linked via .children dict.
        """
        from games.texas_hold_em import create_river_state, ActionType
        
        # Create the initial river state
        state = create_river_state(
            p0_cards=p0_hand,
            p1_cards=p1_hand,
            board=board,
            pot=pot,
            stacks=stacks,
        )
        
        # Generate infoset key for the root
        infoset_key = state.infoset_key(state.current_player)
        
        # Create root action node
        valid_actions = self.game.get_valid_actions(state, state.current_player)
        root = ActionNode(
            infoset_key=infoset_key,
            available_actions=valid_actions,
            player=state.current_player,
            node_type=NodeType.ACTION,
        )
        
        # Build tree recursively
        self._build_tree_recursive(root, state)
        
        return root
    
    def _build_tree_recursive(self, parent_node: Node, state: "GameState"):
        """
        Recursively build the game tree from a given state.
        
        Args:
            parent_node: The parent node to attach children to
            state: Current game state
        """
        if self.game.is_terminal(state):
            # Create terminal node
            terminal_node = TerminalNode(
                infoset_key=state.infoset_key(-1) if state.current_player < 0 else state.infoset_key(state.current_player),
                payoffs=self.game.get_payoffs(state),
                terminal_reason=state.terminal_reason or "showdown",
                node_type=NodeType.TERMINAL,
            )
            parent_node.children["terminal"] = terminal_node
            terminal_node.parent = parent_node
            return
        
        player = state.current_player
        valid_actions = self.game.get_valid_actions(state, player)
        
        if not valid_actions:
            # No valid actions - should be terminal
            terminal_node = TerminalNode(
                infoset_key=state.infoset_key(player),
                payoffs=self.game.get_payoffs(state),
                terminal_reason="showdown",
                node_type=NodeType.TERMINAL,
            )
            parent_node.children["terminal"] = terminal_node
            terminal_node.parent = parent_node
            return
        
        # Create a child node for each valid action
        for action_str in valid_actions:
            # Create new state by applying this action
            new_state = self.game.apply_action(state, player, action_str)
            
            # Generate infoset key for the new state
            next_player = new_state.current_player
            infoset_key = new_state.infoset_key(next_player) if next_player >= 0 else state.infoset_key(player)
            
            if new_state.terminal:
                # Terminal node for fold/showdown
                child = TerminalNode(
                    infoset_key=infoset_key,
                    payoffs=new_state.payoffs if new_state.payoffs else self.game.get_payoffs(new_state),
                    terminal_reason=new_state.terminal_reason or "showdown",
                    node_type=NodeType.TERMINAL,
                )
            else:
                # Create action node for next decision point
                next_actions = self.game.get_valid_actions(new_state, next_player)
                child = ActionNode(
                    infoset_key=infoset_key,
                    available_actions=next_actions,
                    player=next_player,
                    node_type=NodeType.ACTION,
                )
            
            parent_node.children[action_str] = child
            child.parent = parent_node
            
            # Recursively build subtree
            self._build_tree_recursive(child, new_state)
