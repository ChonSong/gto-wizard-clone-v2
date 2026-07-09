"""ICM API router - tournament Independent Chip Model calculations.

Provides endpoints for:
- ICM equity calculations
- Bubble factor calculations
- Tournament scenario management
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from apps.api.schemas.icm import (
    ICMCalculationRequest,
    ICMCalculationResponse,
    ICMResult,
    TournamentScenario,
    TournamentScenarioCreate,
    TournamentScenarioList,
)
from apps.api.services.icm_storage import get_scenario_storage
from gto_poker.icm import icm_calculate, calculate_bubble_factor


router = APIRouter(prefix="/api/v1/icm", tags=["ICM"])


@router.post("/calculate", response_model=ICMCalculationResponse)
async def calculate_icm(request: ICMCalculationRequest) -> ICMCalculationResponse:
    """Calculate ICM equity for a tournament scenario.

    Computes equity for each player based on chip stacks and prize structure
    using Monte Carlo simulation with the Malmoud-Harville formula.

    Args:
        request: ICM calculation request with stacks, prizes, and player info.

    Returns:
        ICM equity results for each player including bubble factors.

    Raises:
        HTTPException: If input validation fails or calculation error occurs.
    """
    try:
        # Generate player names if not provided
        n_players = len(request.stacks)
        players = request.players or [f"Player_{i + 1}" for i in range(n_players)]

        if len(players) != n_players:
            raise HTTPException(
                status_code=400,
                detail=f"Number of players ({len(players)}) must match number of stacks ({n_players})",
            )

        # Ensure prizes match player count
        if len(request.prizes) < n_players:
            prizes = list(request.prizes) + [0.0] * (n_players - len(request.prizes))
        else:
            prizes = request.prizes[:n_players]

        # Calculate ICM
        results = icm_calculate(
            stacks=request.stacks,
            prizes=prizes,
            players=players,
            n_simulations=request.n_simulations,
            seed=request.seed,
        )

        # Convert to response format
        icm_results = [
            ICMResult(
                player=r.player,
                equity=r.equity,
                chip_equity=r.chip_equity,
                bubble_factor=r.bubble_factor,
                ev=r.ev,
            )
            for r in results
        ]

        return ICMCalculationResponse(
            results=icm_results,
            total_prize_pool=sum(prizes),
            total_chips=sum(request.stacks),
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ICM calculation failed: {str(e)}")


@router.post("/bubble-factor")
async def get_bubble_factor(
    stacks: list[float],
    prizes: list[float],
    player_idx: int,
    n_simulations: int = Query(100_000, ge=1000, le=1_000_000),
    seed: Optional[int] = None,
) -> dict:
    """Calculate bubble factor for a specific player.

    The bubble factor indicates how valuable each chip is compared to
    raw chip equity (1.0 = fair value, >1.0 = more valuable).

    Args:
        stacks: List of chip stacks.
        prizes: Prize amounts per place.
        player_idx: Index of player to calculate bubble factor for.
        n_simulations: Number of Monte Carlo simulations.
        seed: Optional random seed.

    Returns:
        Bubble factor for the specified player.
    """
    try:
        bf = calculate_bubble_factor(
            stacks=stacks,
            prizes=prizes,
            player_idx=player_idx,
            n_simulations=n_simulations,
            seed=seed,
        )
        return {"bubble_factor": bf}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/scenarios", response_model=TournamentScenarioList)
async def list_scenarios(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> TournamentScenarioList:
    """List all stored tournament scenarios.

    Args:
        limit: Maximum number of scenarios to return.
        offset: Number of scenarios to skip.

    Returns:
        List of tournament scenarios.
    """
    storage = get_scenario_storage()
    return await storage.list_scenarios(limit=limit, offset=offset)


@router.post("/scenarios", response_model=TournamentScenario)
async def create_scenario(
    request: TournamentScenarioCreate,
) -> TournamentScenario:
    """Create a new tournament scenario.

    Stores a tournament scenario for later use in training or analysis.

    Args:
        request: Scenario data.

    Returns:
        Created scenario with ID.
    """
    scenario = TournamentScenario(
        name=request.name,
        players=request.players,
        stacks=request.stacks,
        prizes=request.prizes,
        street=request.street,
    )

    storage = get_scenario_storage()
    return await storage.create_scenario(scenario)


@router.get("/scenarios/{scenario_id}", response_model=TournamentScenario)
async def get_scenario(scenario_id: str) -> TournamentScenario:
    """Get a specific tournament scenario by ID.

    Args:
        scenario_id: UUID of the scenario.

    Returns:
        Tournament scenario.

    Raises:
        HTTPException: If scenario not found.
    """
    storage = get_scenario_storage()
    scenario = await storage.get_scenario(scenario_id)

    if scenario is None:
        raise HTTPException(status_code=404, detail="Scenario not found")

    return scenario


@router.put("/scenarios/{scenario_id}", response_model=TournamentScenario)
async def update_scenario(
    scenario_id: str,
    scenario: TournamentScenario,
) -> TournamentScenario:
    """Update an existing tournament scenario.

    Args:
        scenario_id: UUID of scenario to update.
        scenario: New scenario data.

    Returns:
        Updated scenario.

    Raises:
        HTTPException: If scenario not found.
    """
    storage = get_scenario_storage()
    updated = await storage.update_scenario(scenario_id, scenario)

    if updated is None:
        raise HTTPException(status_code=404, detail="Scenario not found")

    return updated


@router.delete("/scenarios/{scenario_id}")
async def delete_scenario(scenario_id: str) -> dict:
    """Delete a tournament scenario.

    Args:
        scenario_id: UUID of scenario to delete.

    Returns:
        Confirmation message.

    Raises:
        HTTPException: If scenario not found.
    """
    storage = get_scenario_storage()
    deleted = await storage.delete_scenario(scenario_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Scenario not found")

    return {"message": "Scenario deleted", "id": scenario_id}
