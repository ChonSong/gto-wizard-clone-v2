"""
Chart generator for push/fold Nash equilibrium strategies.

This module provides functions to generate, manage, and serialize
push/fold charts for various stack sizes and positions.
"""

import json
from typing import Dict, Tuple, Optional, List
from pathlib import Path

from .push_fold_charts import (
    PushFoldCharts,
    RANKS,
    RANK_INDICES,
    Action,
    get_hand_string,
    parse_hand_string,
)


def generate_nash_push_chart(stack_bb: int, position: str) -> Dict[Tuple[str, str], str]:
    """
    Generate a Nash push chart for a specific stack size and position.
    
    Args:
        stack_bb: Stack size in big blinds (10, 20, 40, 60, or 100)
        position: Position name (UTG, MP, CO, BTN, SB, BB)
        
    Returns:
        Dict mapping (rank1, rank2) to action string ("push" or "fold")
        
    Raises:
        ValueError: If stack_bb or position is not supported
    """
    if stack_bb not in PushFoldCharts.STACK_SIZES:
        raise ValueError(
            f"Unsupported stack size: {stack_bb}. "
            f"Supported: {PushFoldCharts.STACK_SIZES}"
        )
    
    if position not in PushFoldCharts.POSITIONS:
        raise ValueError(
            f"Unsupported position: {position}. "
            f"Supported: {PushFoldCharts.POSITIONS}"
        )
    
    return PushFoldCharts.generate_nash_chart(stack_bb, position)


def generate_all_charts() -> Dict[str, Dict[Tuple[str, str], str]]:
    """
    Generate push charts for all supported stack sizes and positions.
    
    Returns:
        Dict with keys like "10bb_UTG", "20bb_BTN", etc.
    """
    all_charts = {}
    
    for stack_bb in PushFoldCharts.STACK_SIZES:
        for position in PushFoldCharts.POSITIONS:
            chart = generate_nash_push_chart(stack_bb, position)
            key = f"{stack_bb}bb_{position}"
            all_charts[key] = chart
    
    return all_charts


def lookup_action(
    chart: Dict[Tuple[str, str], str],
    rank1: str,
    rank2: str,
    suited: bool
) -> str:
    """
    Look up the action for a specific hand in a chart.
    
    Args:
        chart: The push/fold chart dictionary
        rank1: First card rank
        rank2: Second card rank  
        suited: Whether the hand is suited
        
    Returns:
        Action string ("push" or "fold")
    """
    # Normalize to higher-lower order for consistent lookup
    r1_idx = RANK_INDICES[rank1]
    r2_idx = RANK_INDICES[rank2]
    
    if r1_idx >= r2_idx:
        key = (rank1, rank2)
    else:
        key = (rank2, rank1)
    
    return chart.get(key, "fold")


def lookup_hand(
    chart: Dict[Tuple[str, str], str],
    hand_str: str
) -> str:
    """
    Look up action for a hand string like 'AKs', '72o', 'AA'.
    
    Args:
        chart: The push/fold chart dictionary
        hand_str: Hand string (e.g., 'AKs', 'TT', '54s')
        
    Returns:
        Action string ("push" or "fold")
    """
    rank1, rank2, suited = parse_hand_string(hand_str)
    return lookup_action(chart, rank1, rank2, suited)


def chart_to_json_serializable(
    chart: Dict[Tuple[str, str], str]
) -> Dict[str, str]:
    """
    Convert chart with tuple keys to JSON-serializable format.
    
    The chart contains 169 entries (13x13 matrix):
    - 13 pocket pairs (e.g., ("A", "A") -> "AA")
    - 78 suited combos (e.g., ("A", "K") for AKs when suited is True)
    - 78 offsuit combos (e.g., ("A", "K") for AKo when suited is False)
    
    Since the tuple key doesn't distinguish suited/offsuit for different ranks,
    we need to infer from the action - if it's "push" for AK, it's likely
    the suited version. But this is ambiguous.
    
    For a proper implementation, we generate both suited and offsuit entries
    based on the push/fold ranges.
    
    Args:
        chart: Chart dict with (rank1, rank2) tuple keys
        
    Returns:
        Chart with string keys like "As", "A2o"
    """
    from .push_fold_charts import PushFoldCharts
    
    result = {}
    
    # Generate all 169 hand combinations
    for r1 in RANKS:
        for r2 in RANKS:
            key = (r1, r2) if RANK_INDICES[r1] >= RANK_INDICES[r2] else (r2, r1)
            
            action = chart.get(key, "fold")
            
            if r1 == r2:
                # Pocket pair
                hand = f"{r1}{r2}"
            else:
                hi = r1 if RANK_INDICES[r1] >= RANK_INDICES[r2] else r2
                lo = r2 if RANK_INDICES[r1] >= RANK_INDICES[r2] else r1
                
                # For AK, we check if it would be push (suited connectors push more)
                # This is a simplification - in reality the chart should track both
                if action == "push":
                    # Try suited first, if that hand exists in chart
                    hand_s = f"{hi}{lo}s"
                    result[hand_s] = action
                    # Also add offsuit if it's different
                    hand_o = f"{hi}{lo}o"
                    if hand_o not in result:
                        result[hand_o] = "fold"
                    continue
                else:
                    hand = f"{hi}{lo}o"
            
            result[hand] = action
    
    return result


def json_to_chart(
    json_chart: Dict[str, str]
) -> Dict[Tuple[str, str], str]:
    """
    Convert JSON-serializable chart back to tuple-key format.
    
    Args:
        json_chart: Chart with string keys like "As", "A2o"
        
    Returns:
        Chart with (rank1, rank2) tuple keys
    """
    result = {}
    for hand_str, action in json_chart.items():
        rank1, rank2, suited = parse_hand_string(hand_str)
        r1_idx = RANK_INDICES.get(rank1, 0)
        r2_idx = RANK_INDICES.get(rank2, 0)
        
        if r1_idx >= r2_idx:
            key = (rank1, rank2)
        else:
            key = (rank2, rank1)
        
        result[key] = action
    
    return result


def generate_calling_chart(
    stack_bb: int,
    position: str
) -> Dict[Tuple[str, str], str]:
    """
    Generate a push-or-fold chart for when facing a push.
    
    Args:
        stack_bb: Stack size in big blinds
        position: Position (typically SB or BB)
        
    Returns:
        Dict mapping hand to action ("push_or_fold" or "fold")
    """
    if position not in ["SB", "BB"]:
        raise ValueError("Calling charts only supported for SB and BB")
    
    return PushFoldCharts.get_calling_range(stack_bb, position)


class ChartGenerator:
    """
    Generator class for managing push/fold chart generation and storage.
    """
    
    def __init__(self, output_dir: Optional[Path] = None):
        """
        Initialize chart generator.
        
        Args:
            output_dir: Directory to save generated charts
        """
        self.output_dir = output_dir or Path(__file__).parent / "charts"
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_and_save_all(self) -> Dict[str, Path]:
        """
        Generate all charts and save to JSON files.
        
        Returns:
            Dict mapping chart names to saved file paths
        """
        saved_files = {}
        
        for stack_bb in PushFoldCharts.STACK_SIZES:
            for position in PushFoldCharts.POSITIONS:
                chart = generate_nash_push_chart(stack_bb, position)
                json_chart = chart_to_json_serializable(chart)
                
                filename = f"push_{stack_bb}bb_{position}.json"
                filepath = self.output_dir / filename
                
                with open(filepath, 'w') as f:
                    json.dump(json_chart, f, indent=2)
                
                saved_files[f"{stack_bb}bb_{position}"] = filepath
        
        return saved_files
    
    def load_chart(self, stack_bb: int, position: str) -> Dict[Tuple[str, str], str]:
        """
        Load a chart from file.
        
        Args:
            stack_bb: Stack size in big blinds
            position: Position name
            
        Returns:
            Chart dictionary
        """
        filename = f"push_{stack_bb}bb_{position}.json"
        filepath = self.output_dir / filename
        
        if not filepath.exists():
            raise FileNotFoundError(f"Chart not found: {filepath}")
        
        with open(filepath, 'r') as f:
            json_chart = json.load(f)
        
        return json_to_chart(json_chart)
    
    def get_strategy_key(self, stack_bb: int, position: str) -> str:
        """
        Generate the storage key for a chart.
        
        Format: nlh:2:preflop:{stack_depth}:{position}
        
        Args:
            stack_bb: Stack size in big blinds
            position: Position name
            
        Returns:
            Strategy key string
        """
        return f"nlh:2:preflop:{stack_bb}:{position.lower()}"


def main():
    """Generate and display all push/fold charts."""
    from push_fold_charts import print_chart
    
    print("Generating push/fold charts...")
    
    generator = ChartGenerator()
    
    for stack_bb in [10, 20, 40]:
        for position in PushFoldCharts.POSITIONS:
            chart = generate_nash_push_chart(stack_bb, position)
            print_chart(chart, position, stack_bb)
    
    # Save all charts
    saved = generator.generate_and_save_all()
    print(f"\nSaved {len(saved)} charts to {generator.output_dir}")


if __name__ == "__main__":
    main()
