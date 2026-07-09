"""Variants module — placeholder for variant equity calculations."""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

VARIANTS: dict = {}

def get_variant(name: str):
    """Get a variant by name."""
    if name not in VARIANTS:
        raise ValueError(f"Unknown variant: {name}")
    return VARIANTS[name]

def list_variants() -> list[str]:
    """List all registered variants."""
    return list(VARIANTS.keys())

def calculate_variant_equity(variant_name: str, hero: str, villain: str, board: str | None = None, iterations: int = 10000):
    """Calculate equity for a specific variant."""
    raise NotImplementedError("Variant equity calculation not yet implemented")
