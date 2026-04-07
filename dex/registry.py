import logging
from typing import Dict, List, Optional, Any

from web3 import AsyncWeb3

from dex.base_adapter import DEXAdapter
from dex.uniswap_v3 import UniswapV3Adapter
from dex.balancer_v2 import BalancerV2Adapter
from dex.curve import CurveAdapter
from config import (
    UNISWAP_V3_FACTORY,
    SUSHISWAP_V3_FACTORY,
    PANCAKESWAP_V3_FACTORY,
    AERODROME_FACTORY,
    CURVE_REGISTRY_BASE,
    BALANCER_VAULT,
)

logger = logging.getLogger(__name__)


class DEXRegistry:
    """Central registry of all DEX adapters. Manages discovery and routing."""

    def __init__(self, w3: AsyncWeb3, multicall=None):
        self._w3 = w3
        self._multicall = multicall
        self._adapters: Dict[str, DEXAdapter] = {}
        self._initialized = False

    async def initialize(self):
        """Initialize all DEX adapters."""
        if self._initialized:
            return

        self._adapters["uniswap_v3"] = UniswapV3Adapter(
            self._w3, factory_address=UNISWAP_V3_FACTORY, dex_name="uniswap_v3", multicall=self._multicall
        )
        self._adapters["sushiswap_v3"] = UniswapV3Adapter(
            self._w3, factory_address=SUSHISWAP_V3_FACTORY, dex_name="sushiswap_v3", multicall=self._multicall
        )
        self._adapters["pancakeswap_v3"] = UniswapV3Adapter(
            self._w3, factory_address=PANCAKESWAP_V3_FACTORY, dex_name="pancakeswap_v3", multicall=self._multicall
        )
        self._adapters["aerodrome"] = UniswapV3Adapter(
            self._w3, factory_address=AERODROME_FACTORY, dex_name="aerodrome", multicall=self._multicall
        )
        self._adapters["balancer_v2"] = BalancerV2Adapter(
            self._w3, vault_address=BALANCER_VAULT, multicall=self._multicall
        )
        self._adapters["curve"] = CurveAdapter(
            self._w3, registry_addresses=[CURVE_REGISTRY_BASE], multicall=self._multicall
        )

        self._initialized = True
        logger.info(f"DEXRegistry initialized with {len(self._adapters)} adapters")

    def get_adapter(self, dex_name: str) -> Optional[DEXAdapter]:
        """Get a DEX adapter by name."""
        return self._adapters.get(dex_name)

    def get_all_adapters(self) -> Dict[str, DEXAdapter]:
        """Return all registered adapters."""
        return dict(self._adapters)

    async def discover_all_pools(self) -> List[Dict[str, Any]]:
        """Run pool discovery on all adapters and return combined pool list."""
        if not self._initialized:
            await self.initialize()

        all_pools = []
        for name, adapter in self._adapters.items():
            try:
                pools = await adapter.get_all_pools()
                all_pools.extend(pools)
                logger.info(f"[{name}] Discovered {len(pools)} pools")
            except Exception as e:
                logger.error(f"[{name}] Pool discovery failed: {e}")
                continue

        logger.info(f"Total pools discovered across all DEXs: {len(all_pools)}")
        return all_pools

    def get_amount_out(
        self,
        dex_name: str,
        token_in: str,
        token_out: str,
        amount_in: int,
        pool_address: str,
    ) -> int:
        """Synchronous wrapper for get_amount_out (for simulation math)."""
        adapter = self._adapters.get(dex_name)
        if not adapter:
            return 0
        return adapter.calculate_amount_out(
            amount_in=amount_in,
            reserve_in=0,
            reserve_out=0,
            fee=adapter.get_fee(pool_address),
        )

    @property
    def adapter_names(self) -> List[str]:
        return list(self._adapters.keys())
