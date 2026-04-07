import logging
from typing import List, Dict, Any, Optional, Set

from web3 import AsyncWeb3

from discovery.factory_scanner import discover_all_pairs_v3
from discovery.subgraph_client import fetch_uniswap_v3_pools_from_subgraph, fetch_balancer_pools_from_subgraph
from discovery.pool_filter import apply_quality_gates
from config import (
    UNISWAP_V3_FACTORY,
    SUSHISWAP_V3_FACTORY,
    AERODROME_FACTORY,
    BALANCER_VAULT,
    MAJOR_TOKENS,
    MIN_POOL_TVL_USD,
    SEED_POOLS,
)

logger = logging.getLogger(__name__)


class PoolRegistry:
    """Central registry of all discovered and quality-filtered pools."""

    def __init__(self):
        self._pools: Dict[str, Dict[str, Any]] = {}
        self._pool_addresses: Set[str] = set()
        self._dex_pools: Dict[str, List[Dict[str, Any]]] = {}
        self._load_seed_pools()

    def _load_seed_pools(self):
        """Pre-load known high-TVL pools for immediate scanner availability."""
        for pool in SEED_POOLS:
            addr = pool["address"].lower()
            if addr not in self._pool_addresses:
                self._pool_addresses.add(addr)
                self._pools[addr] = pool
                logger.info(f"Pre-seeded pool: {addr} ({pool.get('dex', 'unknown')})")
        logger.info(f"Loaded {len(SEED_POOLS)} seed pools")

    async def discover_pools(self, w3: AsyncWeb3) -> List[Dict[str, Any]]:
        """Run full pool discovery across all DEXs and return new pools."""
        new_pools = []

        factory_tasks = [
            ("uniswap_v3", UNISWAP_V3_FACTORY),
            ("sushiswap_v3", SUSHISWAP_V3_FACTORY),
        ]

        for dex_name, factory_addr in factory_tasks:
            try:
                pools = await discover_all_pairs_v3(factory_addr, w3, dex_name=dex_name)
                for pool in pools:
                    addr = pool["address"].lower()
                    if addr not in self._pool_addresses:
                        self._pool_addresses.add(addr)
                        self._pools[addr] = pool
                        new_pools.append(pool)
            except Exception as e:
                logger.error(f"[{dex_name}] Factory scan failed: {e}")

        try:
            subgraph_pools = await fetch_uniswap_v3_pools_from_subgraph()
            for pool in subgraph_pools:
                addr = pool["address"].lower()
                if addr not in self._pool_addresses:
                    self._pool_addresses.add(addr)
                    self._pools[addr] = pool
                    new_pools.append(pool)
        except Exception as e:
            logger.error(f"[subgraph] Uniswap V3 subgraph fetch failed: {e}")

        try:
            balancer_pools = await fetch_balancer_pools_from_subgraph()
            for pool in balancer_pools:
                addr = pool["address"].lower()
                if addr not in self._pool_addresses:
                    self._pool_addresses.add(addr)
                    self._pools[addr] = pool
                    new_pools.append(pool)
        except Exception as e:
            logger.error(f"[subgraph] Balancer V2 subgraph fetch failed: {e}")

        filtered = apply_quality_gates(new_pools)
        for pool in filtered:
            addr = pool["address"].lower()
            self._pools[addr] = pool

        logger.info(f"PoolRegistry: {len(new_pools)} new pools, {len(filtered)} passed quality gates")
        return filtered

    def register_pool(self, pool: Dict[str, Any]):
        """Manually register a single pool (e.g. from event watcher)."""
        addr = pool["address"].lower()
        if addr not in self._pool_addresses:
            self._pool_addresses.add(addr)
            self._pools[addr] = pool
            logger.info(f"Registered new pool from event: {addr}")

    def get_active_pools(self) -> List[Dict[str, Any]]:
        """Return all quality-filtered pools currently tracked."""
        return list(self._pools.values())

    def get_pools_by_dex(self, dex_name: str) -> List[Dict[str, Any]]:
        """Return pools for a specific DEX."""
        return [p for p in self._pools.values() if p.get("dex") == dex_name]

    def get_pool(self, address: str) -> Optional[Dict[str, Any]]:
        """Get a pool by address."""
        return self._pools.get(address.lower())

    def update_pool_reserves(self, address: str, reserves: Dict[str, Any]):
        """Update reserves for a specific pool."""
        addr = address.lower()
        if addr in self._pools:
            self._pools[addr].update(reserves)

    def remove_pool(self, address: str):
        """Remove a pool from the registry."""
        addr = address.lower()
        if addr in self._pool_addresses:
            self._pool_addresses.discard(addr)
            self._pools.pop(addr, None)

    @property
    def pool_count(self) -> int:
        return len(self._pools)

    @property
    def pool_addresses(self) -> Set[str]:
        return set(self._pool_addresses)
