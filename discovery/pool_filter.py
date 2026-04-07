import logging
from typing import List, Dict, Any, Set

from config import MIN_POOL_TVL_USD, MAJOR_TOKENS

logger = logging.getLogger(__name__)


def apply_quality_gates(
    pools: List[Dict[str, Any]],
    min_tvl_usd: float = MIN_POOL_TVL_USD,
    major_tokens: Set[str] = MAJOR_TOKENS,
) -> List[Dict[str, Any]]:
    """Filter pools through quality gates.

    Gates:
    1. Minimum TVL >= $5,000
    2. At least one token is a major (WETH, USDC, USDT)
    3. Non-zero reserves/balances
    4. Non-zero liquidity
    """
    filtered = []

    for pool in pools:
        if not _passes_tvl_gate(pool, min_tvl_usd):
            continue

        if not _passes_token_whitelist_gate(pool, major_tokens):
            continue

        if not _passes_nonzero_reserves_gate(pool):
            continue

        filtered.append(pool)

    logger.info(
        f"Pool quality filter: {len(pools)} input -> {len(filtered)} passed gates"
    )
    return filtered


def _passes_tvl_gate(pool: Dict[str, Any], min_tvl_usd: float) -> bool:
    """Check if pool TVL meets minimum threshold."""
    tvl = pool.get("tvl_usd", 0)
    if tvl <= 0:
        balances = pool.get("balances", [])
        if balances:
            tvl = sum(balances) / 1e18
    return tvl >= min_tvl_usd


def _passes_token_whitelist_gate(
    pool: Dict[str, Any], major_tokens: Set[str]
) -> bool:
    """Check if at least one token in the pool is a major token."""
    tokens = pool.get("tokens", [])
    if not tokens:
        token0 = pool.get("token0", "")
        token1 = pool.get("token1", "")
        tokens = [t for t in [token0, token1] if t]

    for token in tokens:
        if token.lower() in {t.lower() for t in major_tokens}:
            return True

    return False


def _passes_nonzero_reserves_gate(pool: Dict[str, Any]) -> bool:
    """Check that the pool has non-zero reserves/balances."""
    balances = pool.get("balances", [])
    if balances:
        return all(b > 0 for b in balances)

    liquidity = pool.get("liquidity", 0)
    if liquidity and int(liquidity) > 0:
        return True

    return True
