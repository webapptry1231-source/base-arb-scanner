import logging
from typing import List, Dict, Any, Optional

import aiohttp

from config import CONFIG

logger = logging.getLogger(__name__)

GRAPH_API_KEY = CONFIG.get("graph_api_key", "")

SUBGRAPH_URLS = {
    "uniswap_v3": f"https://gateway.thegraph.com/api/{GRAPH_API_KEY}/subgraphs/id/HUZDsRpEVP2AvzDCyzDHtdc64dyDxx8FQjzsmqSg4H3B" if GRAPH_API_KEY else "",
    "balancer_v2": f"https://gateway.thegraph.com/api/{GRAPH_API_KEY}/subgraphs/id/H9oPAbXnobBRq1cB3HDmbZ1E8MWQyJYQjT1QDJMrdbNp" if GRAPH_API_KEY else "",
}


async def query_subgraph(query: str, subgraph_url: str, timeout: int = 30) -> Dict[str, Any]:
    """Execute a GraphQL query against a subgraph endpoint."""
    if not subgraph_url:
        logger.warning("Subgraph URL not configured (missing GRAPH_API_KEY?)")
        return {}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                subgraph_url,
                json={"query": query},
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("data", {})
                else:
                    logger.error(f"Subgraph query failed with status {response.status}")
                    return {}
    except Exception as e:
        logger.error(f"Subgraph query error: {e}")
        return {}


async def fetch_uniswap_v3_pools_from_subgraph(
    subgraph_url: str = SUBGRAPH_URLS["uniswap_v3"],
    first: int = 1000,
) -> List[Dict[str, Any]]:
    """Fetch Uniswap V3 pools from The Graph subgraph."""
    if not subgraph_url:
        logger.info("[subgraph] Skipping Uniswap V3 subgraph fetch — no API key configured")
        return []

    query = f"""
    {{
        pools(first: {first}, where: {{totalValueLockedUSD_gt: "1000"}}) {{
            id
            token0 {{
                id
                symbol
            }}
            token1 {{
                id
                symbol
            }}
            feeTier
            totalValueLockedUSD
            sqrtPrice
            liquidity
        }}
    }}
    """

    result = await query_subgraph(query, subgraph_url)
    pools = result.get("pools", [])

    formatted = []
    for p in pools:
        formatted.append({
            "address": p["id"],
            "token0": p["token0"]["id"],
            "token1": p["token1"]["id"],
            "fee": int(p["feeTier"]) / 1_000_000,
            "tvl_usd": float(p.get("totalValueLockedUSD", 0)),
            "sqrt_price": p.get("sqrtPrice", "0"),
            "liquidity": int(p.get("liquidity", 0)),
            "dex": "uniswap_v3",
            "type": "v3",
        })

    logger.info(f"[subgraph] Fetched {len(formatted)} Uniswap V3 pools")
    return formatted


async def fetch_balancer_pools_from_subgraph(
    subgraph_url: str = SUBGRAPH_URLS["balancer_v2"],
    first: int = 1000,
) -> List[Dict[str, Any]]:
    """Fetch Balancer V2 pools from The Graph subgraph."""
    if not subgraph_url:
        logger.info("[subgraph] Skipping Balancer V2 subgraph fetch — no API key configured")
        return []

    query = f"""
    {{
        pools(first: {first}, where: {{totalLiquidity_gt: "10000"}}) {{
            id
            address
            tokens {{
                address
                symbol
                balance
                weight
            }}
            swapFee
            totalLiquidity
        }}
    }}
    """

    result = await query_subgraph(query, subgraph_url)
    pools = result.get("pools", [])

    formatted = []
    for p in pools:
        tokens = [t["address"] for t in p.get("tokens", [])]
        balances = [int(float(t.get("balance", 0)) * 1e18) for t in p.get("tokens", [])]
        weights = [int(float(t.get("weight", 0)) * 1e18) for t in p.get("tokens", [])]

        formatted.append({
            "address": p.get("address", p["id"]),
            "pool_id": p["id"],
            "tokens": tokens,
            "balances": balances,
            "weights": weights,
            "fee": float(p.get("swapFee", 0)),
            "tvl_usd": float(p.get("totalLiquidity", 0)),
            "dex": "balancer_v2",
            "type": "weighted",
        })

    logger.info(f"[subgraph] Fetched {len(formatted)} Balancer V2 pools")
    return formatted
