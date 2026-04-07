import logging
from typing import Dict, Any, Optional

from config import MAX_BORROW_PCT

logger = logging.getLogger(__name__)

TOKEN_DECIMALS = {
    "0x4200000000000000000000000000000000000006": 18,
    "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913": 6,
    "0xfde4c96c8593536e31f229ea8f37b2ada2699bb2": 6,
}


def estimate_slippage(
    amount_in: int,
    reserve_in: int,
    reserve_out: int,
    fee: float = 0.003,
    sqrtPriceX96: Optional[int] = None,
    liquidity: Optional[int] = None,
) -> float:
    """Estimate price impact / slippage for a given trade size.

    Routes to V3 slippage model when sqrtPriceX96 and liquidity are provided.
    """
    if sqrtPriceX96 is not None and liquidity is not None and liquidity > 0:
        return estimate_v3_slippage(amount_in, liquidity, fee)

    if reserve_in <= 0 or reserve_out <= 0:
        return 1.0

    ideal_rate = reserve_out / reserve_in
    ideal_output = amount_in * ideal_rate

    amount_in_with_fee = int(amount_in * (1 - fee))
    numerator = amount_in_with_fee * reserve_out
    denominator = reserve_in + amount_in_with_fee

    if denominator == 0 or ideal_output <= 0:
        return 1.0

    actual_output = numerator / denominator
    slippage = 1.0 - (actual_output / ideal_output)

    return min(max(slippage, 0.0), 1.0)


def compute_optimal_borrow_amount(
    pool_tvl_usd: float,
    token_address: str = "",
    token_decimals: int = 18,
    max_borrow_pct: float = MAX_BORROW_PCT,
) -> int:
    """Compute optimal borrow amount capped at max_borrow_pct of pool TVL."""
    if token_address:
        token_decimals = TOKEN_DECIMALS.get(token_address.lower(), token_decimals)
    borrow_usd = pool_tvl_usd * max_borrow_pct
    borrow_wei = int(borrow_usd * (10 ** token_decimals))
    return max(borrow_wei, 0)


def estimate_v3_slippage(amount_in: int, liquidity: int, fee: float = 0.003) -> float:
    """Estimate slippage for V3 pools using liquidity depth.

    V3 pools don't have reserve0/reserve1 in the V2 sense.
    Slippage is estimated as amount_in relative to available liquidity.
    """
    if liquidity <= 0:
        return 1.0

    trade_to_liquidity_ratio = amount_in / liquidity
    slippage = trade_to_liquidity_ratio * fee + (trade_to_liquidity_ratio ** 2) * 0.5

    return min(max(slippage, 0.0), 1.0)


def apply_slippage_to_amount(amount: int, slippage: float) -> int:
    """Apply slippage reduction to an amount."""
    return int(amount * (1 - slippage))
