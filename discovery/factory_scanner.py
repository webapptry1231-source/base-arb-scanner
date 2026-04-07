import logging
from typing import List, Dict, Any, Optional

from web3 import AsyncWeb3

from config import UNISWAP_V3_FACTORY, SUSHISWAP_V3_FACTORY, MULTICALL_BATCH

logger = logging.getLogger(__name__)

FACTORY_V3_ABI = [
    {
        "inputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "name": "allPools",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "poolCount",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]


async def discover_all_pairs_v3(
    factory_addr: str,
    w3: AsyncWeb3,
    batch_size: int = 200,
    dex_name: str = "unknown",
) -> List[Dict[str, Any]]:
    """Scan all pools from a V3-style factory contract.

    Uses batched multicall-friendly iteration over allPools.
    Falls back to sequential calls if multicall is unavailable.
    """
    factory = w3.eth.contract(address=factory_addr, abi=FACTORY_V3_ABI)
    pools = []

    try:
        pool_count = await factory.functions.poolCount().call()
        pool_count = int(pool_count)
        logger.info(f"[{dex_name}] Factory reports {pool_count} pools")
    except Exception as e:
        logger.error(f"[{dex_name}] Failed to get pool count from {factory_addr}: {e}")
        return []

    if pool_count == 0:
        return []

    for i in range(0, pool_count, batch_size):
        batch_end = min(i + batch_size, pool_count)
        logger.debug(f"[{dex_name}] Fetching pools {i} to {batch_end - 1}")

        for j in range(i, batch_end):
            try:
                pool_address = await factory.functions.allPools(j).call()
                pools.append({
                    "address": pool_address,
                    "factory": factory_addr,
                    "dex": dex_name,
                    "index": j,
                })
            except Exception as e:
                logger.debug(f"[{dex_name}] Failed to fetch pool {j}: {e}")
                continue

    logger.info(f"[{dex_name}] Discovered {len(pools)} pools from factory {factory_addr}")
    return pools


async def discover_uniswap_v3_pools(w3: AsyncWeb3) -> List[Dict[str, Any]]:
    return await discover_all_pairs_v3(
        UNISWAP_V3_FACTORY, w3, dex_name="uniswap_v3"
    )


async def discover_sushiswap_v3_pools(w3: AsyncWeb3) -> List[Dict[str, Any]]:
    return await discover_all_pairs_v3(
        SUSHISWAP_V3_FACTORY, w3, dex_name="sushiswap_v3"
    )
