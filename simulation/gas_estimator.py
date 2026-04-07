import logging
from typing import Dict, Any, List

from config import GAS_ESTIMATES, GAS_SAFETY_BUFFER

logger = logging.getLogger(__name__)


def estimate_gas(route: Dict[str, Any], fl_source: str = "balancer") -> int:
    """Estimate gas units for an arbitrage route.

    Base estimates + flash loan overhead + 25% safety buffer.
    """
    num_hops = len(route.get("steps", []))

    if num_hops <= 2:
        base_gas = GAS_ESTIMATES["2_hop_arb"]
    elif num_hops == 3:
        base_gas = GAS_ESTIMATES["3_hop_arb"]
    else:
        base_gas = GAS_ESTIMATES["4_hop_arb"]

    if fl_source == "balancer":
        fl_overhead = GAS_ESTIMATES["fl_balancer"]
    else:
        fl_overhead = GAS_ESTIMATES["fl_aave_v3"]

    total_gas = base_gas + fl_overhead
    total_with_buffer = int(total_gas * GAS_SAFETY_BUFFER)

    return total_with_buffer


def estimate_gas_cost_usd(
    gas_units: int,
    gas_price_gwei: float,
    eth_price_usd: float,
) -> float:
    """Estimate gas cost in USD.

    gas_cost = gas_units * (gas_price_gwei / 1e9) * eth_price_usd
    """
    gas_cost_eth = gas_units * (gas_price_gwei / 1e9)
    return gas_cost_eth * eth_price_usd
