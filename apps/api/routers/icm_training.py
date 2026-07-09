"""Tournament scenario builder for ICM-based training.

Provides tools for building and managing tournament scenarios
for training AI poker agents using ICM equity calculations.
"""

import random
from dataclasses import dataclass, field
from typing import Optional

from apps.api.schemas.icm import TournamentScenario, ICMResult
from apps.api.services.icm_storage import get_scenario_storage
from gto_poker.icm import icm_calculate


@dataclass
class TrainingScenarioConfig:
    """Configuration for generating training scenarios."""
    min_players: int = 2
    max_players: int = 10
    min_stack: float = 1000.0
    max_stack: float = 50000.0
    prize_pool: float = 10000.0
    typical_structures: list = field(
        default_factory=lambda: [
            [0.5, 0.3, 0.2],  # 3 players
            [0.4, 0.25, 0.2, 0.15],  # 4 players
            [0.3, 0.2, 0.15, 0.1, 0.08, 0.05, 0.05, 0.04, 0.03],  # 9-max
        ]
    )


@dataclass
class GeneratedScenario:
    """A generated training scenario with metadata."""
    scenario: TournamentScenario
    difficulty: float  # 0.0 to 1.0, based on stack disparity
    icm_positions: list[ICMResult]


class TournamentScenarioBuilder:
    """Builder for creating tournament training scenarios.
    
    Provides methods to generate realistic tournament situations
    for training poker AI agents with ICM-informed decisions.
    """
    
    def __init__(self, config: Optional[TrainingScenarioConfig] = None):
        self.config = config or TrainingScenarioConfig()
    
    def generate_player_names(self, n_players: int) -> list[str]:
        """Generate realistic player names.
        
        Args:
            n_players: Number of players.
        
        Returns:
            List of player names.
        """
        prefixes = ["Pro", "Ami", "Nit", "LAG", "TAG", "Fish", "Rock", "Maniac", "Hero", "Villain"]
        suffixes = ["1", "2", "3", "4", "5", "6", "7", "8", "9"]
        
        names = []
        for i in range(n_players):
            # Mix of styles
            if i < len(prefixes):
                name = f"{prefixes[i]}_{suffixes[i]}"
            else:
                name = f"Player_{i+1}"
            names.append(name)
        
        return names
    
    def generate_random_stacks(self, n_players: int) -> list[float]:
        """Generate random chip stacks within configured range.
        
        Args:
            n_players: Number of players.
        
        Returns:
            List of chip stacks.
        """
        stacks = []
        for _ in range(n_players):
            # Random stack within range
            stack = random.uniform(self.config.min_stack, self.config.max_stack)
            # Round to reasonable number
            stack = round(stack / 100) * 100
            stacks.append(stack)
        
        return stacks
    
    def select_prize_structure(self, n_players: int) -> list[float]:
        """Select appropriate prize structure for number of players.
        
        Args:
            n_players: Number of players.
        
        Returns:
            List of prize percentages summing to 1.0.
        """
        for structure in self.config.typical_structures:
            if len(structure) >= n_players:
                return structure[:n_players]
        
        # Default even distribution
        return [1.0 / n_players] * n_players
    
    def calculate_difficulty(self, stacks: list[float]) -> float:
        """Calculate scenario difficulty based on stack disparity.
        
        Args:
            stacks: List of chip stacks.
        
        Returns:
            Difficulty score from 0.0 (even) to 1.0 (highly uneven).
        """
        if len(stacks) < 2:
            return 0.0
        
        max_stack = max(stacks)
        min_stack = min(stacks)
        
        if max_stack == 0:
            return 0.0
        
        # Ratio of max to min
        ratio = max_stack / max(min_stack, 1)
        
        # Normalize to 0-1 range (ratio of 1 = 0 difficulty, ratio of 10+ = max difficulty)
        difficulty = min((ratio - 1) / 9, 1.0)
        
        return round(difficulty, 3)
    
    def generate_scenario(
        self,
        name: Optional[str] = None,
        n_players: Optional[int] = None,
        street: Optional[str] = None,
        preserve_stacks: Optional[list[float]] = None,
    ) -> GeneratedScenario:
        """Generate a random tournament scenario.
        
        Args:
            name: Optional scenario name.
            n_players: Optional specific number of players.
            street: Optional tournament street (bubble, FT, etc).
            preserve_stacks: Optional stacks to use instead of generating.
        
        Returns:
            Generated scenario with ICM positions.
        """
        # Determine number of players
        if n_players is None:
            n_players = random.randint(self.config.min_players, self.config.max_players)
        
        # Generate or use provided stacks
        if preserve_stacks:
            stacks = preserve_stacks
        else:
            stacks = self.generate_random_stacks(n_players)
        
        # Generate player names
        players = self.generate_player_names(n_players)
        
        # Select prize structure
        prize_percents = self.select_prize_structure(n_players)
        prize_pool = self.config.prize_pool
        prizes = [prize_pool * p for p in prize_percents]
        
        # Create scenario
        scenario_name = name or f"Scenario_{random.randint(1000, 9999)}"
        scenario = TournamentScenario(
            name=scenario_name,
            players=players,
            stacks=stacks,
            prizes=prizes,
            street=street or self._infer_street(n_players, stacks),
        )
        
        # Calculate ICM positions
        icm_results = icm_calculate(
            stacks=stacks,
            prizes=prizes,
            players=players,
        )
        
        difficulty = self.calculate_difficulty(stacks)
        
        return GeneratedScenario(
            scenario=scenario,
            difficulty=difficulty,
            icm_positions=icm_results,
        )
    
    def _infer_street(self, n_players: int, stacks: list[float]) -> str:
        """Infer tournament street from situation.
        
        Args:
            n_players: Number of players.
            stacks: Chip stacks.
        
        Returns:
            Inferred tournament street.
        """
        total_chips = sum(stacks)
        avg_stack = total_chips / n_players if n_players > 0 else 0
        
        # Simple heuristics
        if n_players <= 3:
            return "final"
        elif n_players <= 6:
            return "FT"  # Final table
        else:
            # Check if short stacks exist
            short_stacks = [s for s in stacks if s < avg_stack * 0.3]
            if len(short_stacks) >= 2:
                return "bubble"
            return "early"
    
    def generate_batch(
        self,
        count: int,
        name_prefix: str = "Training",
    ) -> list[GeneratedScenario]:
        """Generate a batch of training scenarios.
        
        Args:
            count: Number of scenarios to generate.
            name_prefix: Prefix for scenario names.
        
        Returns:
            List of generated scenarios.
        """
        scenarios = []
        for i in range(count):
            scenario = self.generate_scenario(
                name=f"{name_prefix}_{i+1}",
            )
            scenarios.append(scenario)
        
        return scenarios
    
    async def save_scenario(self, scenario: TournamentScenario) -> TournamentScenario:
        """Save a scenario to storage.
        
        Args:
            scenario: Scenario to save.
        
        Returns:
            Saved scenario with ID.
        """
        storage = get_scenario_storage()
        return await storage.create_scenario(scenario)
    
    async def generate_and_save(
        self,
        name: Optional[str] = None,
        n_players: Optional[int] = None,
    ) -> TournamentScenario:
        """Generate and immediately save a scenario.
        
        Args:
            name: Optional scenario name.
            n_players: Optional number of players.
        
        Returns:
            Saved tournament scenario.
        """
        generated = self.generate_scenario(name=name, n_players=n_players)
        return await self.save_scenario(generated.scenario)


class BubbleScenarioBuilder(TournamentScenarioBuilder):
    """Specialized builder for bubble situations.
    
    Generates scenarios specifically around the bubble (when one
    more elimination = prize jump) for focused training.
    """
    
    def __init__(self):
        super().__init__()
        # Override config for bubble scenarios
        self.config.min_players = 4
        self.config.max_players = 12
    
    def generate_bubble_scenario(
        self,
        n_players_at_money: int = 9,
        short_stack_multiplier: float = 0.2,
    ) -> GeneratedScenario:
        """Generate a bubble scenario near the money bubble.
        
        Args:
            n_players_at_money: Number of players that make the money.
            short_stack_multiplier: How short the short stack is relative to avg.
        
        Returns:
            Bubble scenario with one clearly short player.
        """
        n_players = n_players_at_money + random.randint(1, 3)
        
        # Generate prize structure where bubble matters
        prize_pool = self.config.prize_pool
        prizes = self.select_prize_structure(n_players)
        prizes = [prize_pool * p for p in prizes]
        
        # Make sure there's a significant jump at the bubble
        bubble_prize = prizes[n_players_at_money - 1] if n_players_at_money <= len(prizes) else 0
        next_prize = prizes[n_players_at_money] if n_players_at_money < len(prizes) else 0
        
        # Ensure bubble jump is meaningful
        if bubble_prize > 0 and next_prize == 0:
            # Adjust to create jump
            prizes[n_players_at_money] = bubble_prize * 0.1
        
        # Generate stacks with one short stack
        avg_stack = random.uniform(5000, 15000)
        stacks = []
        
        for i in range(n_players):
            if i == n_players - 1:
                # Last player is short
                stack = avg_stack * short_stack_multiplier
            else:
                # Others are around average
                stack = avg_stack * random.uniform(0.8, 1.5)
            stacks.append(round(stack / 100) * 100)
        
        players = self.generate_player_names(n_players)
        
        scenario = TournamentScenario(
            name=f"Bubble_{n_players_at_money}m_{n_players}p",
            players=players,
            stacks=stacks,
            prizes=prizes,
            street="bubble",
        )
        
        icm_results = icm_calculate(
            stacks=stacks,
            prizes=prizes,
            players=players,
        )
        
        return GeneratedScenario(
            scenario=scenario,
            difficulty=0.8,  # Bubble scenarios are inherently difficult
            icm_positions=icm_results,
        )


class FinalTableScenarioBuilder(TournamentScenarioBuilder):
    """Specialized builder for final table scenarios.
    
    Generates scenarios at the final table with significant
    prize jumps between positions.
    """
    
    def __init__(self):
        super().__init__()
        self.config.min_players = 6
        self.config.max_players = 10
    
    def generate_final_table_scenario(
        self,
        hero_stack: Optional[float] = None,
        n_players: int = 9,
    ) -> GeneratedScenario:
        """Generate a final table scenario.
        
        Args:
            hero_stack: Optional specific stack for 'hero' player.
            n_players: Number of players at final table.
        
        Returns:
            Final table scenario.
        """
        # Standard final table prize structure
        prize_pool = self.config.prize_pool * 2  # Final table usually has overlay
        if n_players == 9:
            prize_structure = [0.30, 0.20, 0.14, 0.10, 0.08, 0.06, 0.05, 0.04, 0.03]
        elif n_players == 10:
            prize_structure = [0.25, 0.18, 0.14, 0.10, 0.08, 0.07, 0.06, 0.05, 0.04, 0.03]
        else:
            prize_structure = self.select_prize_structure(n_players)
        
        prizes = [prize_pool * p for p in prize_structure[:n_players]]
        
        # Generate stacks
        stacks = []
        for i in range(n_players):
            if hero_stack and i == 0:
                stacks.append(hero_stack)
            else:
                # Increasing stacks as we go around the table
                base = prize_pool / n_players
                stack = base * random.uniform(0.5, 2.0)
                stacks.append(round(stack / 100) * 100)
        
        players = ["Hero"] + self.generate_player_names(n_players - 1)
        
        scenario = TournamentScenario(
            name=f"FT_{n_players}max",
            players=players,
            stacks=stacks,
            prizes=prizes,
            street="FT",
        )
        
        icm_results = icm_calculate(
            stacks=stacks,
            prizes=prizes,
            players=players,
        )
        
        difficulty = self.calculate_difficulty(stacks)
        
        return GeneratedScenario(
            scenario=scenario,
            difficulty=difficulty,
            icm_positions=icm_results,
        )