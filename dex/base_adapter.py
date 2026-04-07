from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class DEXAdapter(ABC):
    """Base interface every DEX adapter must implement."""

    def __init__(self, w3, multicall=None):
        self._w3 = w3
        self._multicall = multicall
        self._pools: List[Dict[str, Any]] = []

    @abstractmethod
    async def get_amount_out(
        self,
        token_in: str,
        token_out: str,
        amount_in: int,
        pool_address: str,
    ) -> int:
        """Calculate the output amount for a swap on this DEX."""
        raise NotImplementedError

    @abstractmethod
    async def get_all_pools(self) -> List[Dict[str, Any]]:
        """Discover and return all pools for this DEX."""
        raise NotImplementedError

    @abstractmethod
    def get_fee(self, pool_address: str) -> float:
        """Return the swap fee for a given pool."""
        raise NotImplementedError

    @abstractmethod
    def get_pool_type(self) -> str:
        """Return the DEX type identifier (e.g. 'uniswap_v3', 'balancer_v2')."""
        raise NotImplementedError

    def calculate_amount_out(
        self,
        amount_in: int,
        reserve_in: int,
        reserve_out: int,
        fee: float,
    ) -> int:
        """Default V2-style constant product calculation (xy=k).

        amount_out = (amount_in * (1 - fee) * reserve_out) / (reserve_in + amount_in * (1 - fee))
        """
        if reserve_in <= 0 or reserve_out <= 0:
            return 0

        amount_in_with_fee = int(amount_in * (1 - fee))
        numerator = amount_in_with_fee * reserve_out
        denominator = reserve_in + amount_in_with_fee

        if denominator == 0:
            return 0

        return numerator // denominator

    def estimate_slippage(self, amount_in: int, reserve_in: int, reserve_out: int) -> float:
        """Estimate price impact / slippage for a given trade size.

        slippage = 1 - (actual_output / ideal_output)
        """
        if reserve_in <= 0 or reserve_out <= 0:
            return 1.0

        ideal_rate = reserve_out / reserve_in
        ideal_output = amount_in * ideal_rate

        actual_output = self.calculate_amount_out(
            amount_in, reserve_in, reserve_out, 0.0
        )

        if ideal_output <= 0:
            return 1.0

        return 1.0 - (actual_output / ideal_output)
