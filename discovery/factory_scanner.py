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
    """Fixed version for Base Uniswap V3-style factories."""
    pools = []
    try:
        # Base factories often don't expose poolCount reliably — use event logs instead
        factory = w3.eth.contract(address=factory_addr, abi=FACTORY_V3_ABI)
        # Get latest 1000 PoolCreated events as fallback
        events = await factory.events.PoolCreated.get_logs(fromBlock="latest-1000")
        logger.info(f"[{dex_name}] Found {len(events)} PoolCreated events")
        
        for event in events:
            pools.append({
                "address": event.args.pool,
                "token0": event.args.token0,
                "token1": event.args.token1,
                "fee": event.args.fee / 1_000_000,
                "dex": dex_name,
                "type": "v3",
            })
    except Exception as e:
        logger.error(f"[{dex_name}] Factory discovery failed: {e}")
    
    return pools


async def discover_uniswap_v3_pools(w3: AsyncWeb3) -> List[Dict[str, Any]]:
    return await discover_all_pairs_v3(
        UNISWAP_V3_FACTORY, w3, dex_name="uniswap_v3"
    )


async def discover_sushiswap_v3_pools(w3: AsyncWeb3) -> List[Dict[str, Any]]:
    return await discover_all_pairs_v3(
        SUSHISWAP_V3_FACTORY, w3, dex_name="sushiswap_v3"
    )
