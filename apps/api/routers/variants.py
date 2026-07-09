"""
Variant Equity API Router — exposes equity calculation for all registered variants
via a unified endpoint using pokerkit's Monte Carlo engine.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from variants import (
    get_variant, list_variants, calculate_variant_equity,
    VARIANTS,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/variants", tags=["variants"])


class EquityRequest(BaseModel):
    hero_range: str = Field(..., description="Hero's range (e.g. 'AKs' or 'AA,KK,AKs')")
    villain_range: str = Field(..., description="Villain's range")
    board: str = Field("", description="Board cards (e.g. 'AhKhQh'). Empty for stud/draw.")
    iterations: int = Field(100000, ge=1000, le=5_000_000, description="Monte Carlo iterations")


class EquityResponse(BaseModel):
    hero_equity: float
    villain_equity: Optional[float] = None
    iterations: int
    variant: str
    variant_name: str


@router.get("")
async def list_all_variants():
    """List all registered poker variants with metadata."""
    return {"variants": list_variants(), "count": len(VARIANTS)}


@router.get("/{variant_key}")
async def get_variant_info(variant_key: str):
    """Get metadata for a specific variant."""
    vd = get_variant(variant_key)
    if vd is None:
        raise HTTPException(status_code=404, detail=f"Unknown variant: {variant_key}")
    return {
        "key": vd.key,
        "name": vd.name,
        "short_name": vd.short_name,
        "category": vd.category.value,
        "hole_count": vd.hole_count,
        "board_count": vd.board_count,
        "description": vd.description,
    }


@router.post("/{variant_key}/equity", response_model=EquityResponse)
async def variant_equity(variant_key: str, req: EquityRequest):
    """Calculate equity for any registered variant using Monte Carlo simulation."""
    try:
        result = calculate_variant_equity(
            variant_key=variant_key,
            hero_range=req.hero_range,
            villain_range=req.villain_range,
            board=req.board,
            iterations=req.iterations,
        )
        return EquityResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Equity calculation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Equity calculation failed: {e}")
