"""Storage service for tournament scenarios and ICM calculations."""

import json
import uuid
from pathlib import Path
from typing import Optional

from apps.api.schemas.icm import TournamentScenario, TournamentScenarioList


class ScenarioStorage:
    """Storage backend for tournament scenarios.
    
    Provides CRUD operations for tournament scenarios with JSON file persistence.
    Can be swapped for database backend in production.
    """
    
    def __init__(self, storage_path: str = "/tmp/icm_scenarios"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._index_file = self.storage_path / "index.json"
        self._ensure_index()
    
    def _ensure_index(self) -> None:
        """Ensure index file exists."""
        if not self._index_file.exists():
            self._save_index({})
    
    def _load_index(self) -> dict:
        """Load scenario index."""
        try:
            with open(self._index_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}
    
    def _save_index(self, index: dict) -> None:
        """Save scenario index."""
        with open(self._index_file, "w") as f:
            json.dump(index, f, indent=2)
    
    def _scenario_path(self, scenario_id: str) -> Path:
        """Get path for scenario file."""
        return self.storage_path / f"{scenario_id}.json"
    
    async def create_scenario(
        self,
        scenario: TournamentScenario,
    ) -> TournamentScenario:
        """Create a new tournament scenario.
        
        Args:
            scenario: Tournament scenario to store.
        
        Returns:
            Stored scenario with assigned ID.
        """
        scenario_id = str(uuid.uuid4())
        
        # Create data with ID
        data = scenario.model_dump()
        data["id"] = scenario_id
        
        # Save scenario file
        scenario_file = self._scenario_path(scenario_id)
        with open(scenario_file, "w") as f:
            json.dump(data, f, indent=2)
        
        # Update index
        index = self._load_index()
        index[scenario_id] = {
            "name": scenario.name,
            "created_at": str(uuid.uuid1()),
        }
        self._save_index(index)
        
        # Return with ID
        return TournamentScenario(**data)
    
    async def get_scenario(self, scenario_id: str) -> Optional[TournamentScenario]:
        """Get a scenario by ID.
        
        Args:
            scenario_id: ID of scenario to retrieve.
        
        Returns:
            Tournament scenario if found, None otherwise.
        """
        scenario_file = self._scenario_path(scenario_id)
        if not scenario_file.exists():
            return None
        
        with open(scenario_file, "r") as f:
            data = json.load(f)
        
        return TournamentScenario(**data)
    
    async def list_scenarios(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> TournamentScenarioList:
        """List all scenarios.
        
        Args:
            limit: Maximum number of scenarios to return.
            offset: Number of scenarios to skip.
        
        Returns:
            List of scenarios with total count.
        """
        index = self._load_index()
        scenario_ids = list(index.keys())
        
        scenarios = []
        for scenario_id in scenario_ids[offset : offset + limit]:
            scenario = await self.get_scenario(scenario_id)
            if scenario:
                scenarios.append(scenario)
        
        return TournamentScenarioList(
            scenarios=scenarios,
            total=len(scenario_ids),
        )
    
    async def update_scenario(
        self,
        scenario_id: str,
        scenario: TournamentScenario,
    ) -> Optional[TournamentScenario]:
        """Update an existing scenario.
        
        Args:
            scenario_id: ID of scenario to update.
            scenario: New scenario data.
        
        Returns:
            Updated scenario if found, None otherwise.
        """
        if not self._scenario_path(scenario_id).exists():
            return None
        
        data = scenario.model_dump()
        data["id"] = scenario_id
        
        with open(self._scenario_path(scenario_id), "w") as f:
            json.dump(data, f, indent=2)
        
        # Update index
        index = self._load_index()
        if scenario_id in index:
            index[scenario_id]["name"] = scenario.name
            self._save_index(index)
        
        return TournamentScenario(**data)
    
    async def delete_scenario(self, scenario_id: str) -> bool:
        """Delete a scenario.
        
        Args:
            scenario_id: ID of scenario to delete.
        
        Returns:
            True if deleted, False if not found.
        """
        scenario_file = self._scenario_path(scenario_id)
        if not scenario_file.exists():
            return False
        
        scenario_file.unlink()
        
        # Update index
        index = self._load_index()
        if scenario_id in index:
            del index[scenario_id]
            self._save_index(index)
        
        return True


# Global storage instance
_scenario_storage: Optional[ScenarioStorage] = None


def get_scenario_storage() -> ScenarioStorage:
    """Get or create global scenario storage instance."""
    global _scenario_storage
    if _scenario_storage is None:
        _scenario_storage = ScenarioStorage()
    return _scenario_storage