import logging
from typing import Dict, List, Any, Optional

from web3 import AsyncWeb3
from multicall import Call, Multicall

from config import MULTICALL_BATCH

logger = logging.getLogger(__name__)

ERC20_ABI_BALANCE = [
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

V2_POOL_ABI_RESERVES = [
    {
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"internalType": "uint112", "name": "reserve0", "type": "uint112"},
            {"internalType": "uint112", "name": "reserve1", "type": "uint112"},
            {"internalType": "uint32", "name": "blockTimestampLast", "type": "uint32"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
]

V3_POOL_ABI_SLOT0 = [
    {
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
            {"internalType": "int24", "name": "tick", "type": "int24"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "liquidity",
        "outputs": [{"internalType": "uint128", "name": "", "type": "uint128"}],
        "stateMutability": "view",
        "type": "function",
    },
]


class ReserveFetcher:
    """Batch-fetches reserves for all tracked pools using Multicall3."""

    def __init__(self, w3: AsyncWeb3, multicall_address: Optional[str] = None):
        self._w3 = w3
        self._multicall_address = multicall_address

    async def fetch_reserves(
        self, pools: List[Dict[str, Any]], batch_size: int = MULTICALL_BATCH
    ) -> Dict[str, Dict[str, Any]]:
        """Fetch reserves for all pools in batches.

        Returns dict mapping pool_address -> {reserve0, reserve1, liquidity, sqrtPriceX96}
        """
        reserves = {}

        for i in range(0, len(pools), batch_size):
            batch = pools[i:i + batch_size]
            batch_results = await self._fetch_batch(batch)
            reserves.update(batch_results)

        logger.debug(f"Fetched reserves for {len(reserves)} pools")
        return reserves

    async def _fetch_batch(self, pools: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Fetch reserves for a single batch of pools using Multicall3."""
        results = {}
        calls = []
        pool_meta = []

        for pool in pools:
            pool_addr = pool.get("address", "")
            pool_type = pool.get("type", "v2")

            if pool_type == "v3":
                calls.append(Call(pool_addr, ["slot0()(uint160,int24)"], ["sqrtPriceX96", "tick"]))
                calls.append(Call(pool_addr, ["liquidity()(uint128)"], ["liquidity"]))
                pool_meta.append((pool_addr, "v3", len(calls) - 2))
                pool_meta.append((pool_addr, "v3", len(calls) - 1))
            else:
                calls.append(Call(pool_addr, ["getReserves()(uint112,uint112,uint32)"], ["reserve0", "reserve1", "blockTimestampLast"]))
                pool_meta.append((pool_addr, "v2", len(calls) - 1))

        if not calls:
            return results

        try:
            multicall = Multicall(calls=calls, _w3=self._w3, require_success=False)
            batch_results = await multicall.coroutine()

            v3_accum: Dict[str, Dict[str, Any]] = {}
            for idx, (addr, ptype, call_idx) in enumerate(pool_meta):
                if ptype == "v3":
                    result = batch_results[call_idx] if call_idx < len(batch_results) else {}
                    if addr not in v3_accum:
                        v3_accum[addr] = {}
                    v3_accum[addr].update(result)
                else:
                    result = batch_results[call_idx] if call_idx < len(batch_results) else {}
                    if result:
                        results[addr] = {
                            "reserve0": int(result.get("reserve0", 0)),
                            "reserve1": int(result.get("reserve1", 0)),
                            "blockTimestampLast": int(result.get("blockTimestampLast", 0)),
                        }

            for addr, data in v3_accum.items():
                if "sqrtPriceX96" in data and "liquidity" in data:
                    results[addr] = {
                        "sqrtPriceX96": int(data["sqrtPriceX96"]),
                        "tick": int(data.get("tick", 0)),
                        "liquidity": int(data["liquidity"]),
                    }
        except Exception as e:
            logger.debug(f"Multicall3 batch fetch failed: {e}")

        return results
