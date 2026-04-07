import math
import logging
from typing import Dict, List, Any, Optional, Set

import networkx as nx

from config import MAJOR_TOKENS, MAX_HOPS

logger = logging.getLogger(__name__)


class GraphBuilder:
    """Builds and maintains a directed price graph from pool data."""

    def __init__(self):
        self._graph = nx.MultiDiGraph()
        self._last_update: int = 0

    def build_graph(
        self,
        pools: List[Dict[str, Any]],
        reserves: Dict[str, Dict[str, Any]],
    ) -> nx.MultiDiGraph:
        """Build a directed weighted graph where nodes = tokens, edges = DEX routes.

        Uses MultiDiGraph to support multiple parallel edges between the same token pair
        (e.g., UniswapV3 WETH→USDC and Balancer WETH→USDC as separate edges).
        Edge weight = -log(effective rate including swap fee).
        Only updates changed edges (incremental).
        """
        new_graph = nx.MultiDiGraph()

        for pool in pools:
            pool_addr = pool.get("address", "")
            dex = pool.get("dex", "unknown")
            fee = pool.get("fee", 0.003)

            token0 = pool.get("token0", "").lower()
            token1 = pool.get("token1", "").lower()
            if not token0 or not token1:
                continue

            pool_reserves = reserves.get(pool_addr, {})
            reserve0 = pool_reserves.get("reserve0", 0)
            reserve1 = pool_reserves.get("reserve1", 0)

            if reserve0 <= 0 or reserve1 <= 0:
                balances = pool.get("balances", [])
                if len(balances) >= 2:
                    reserve0 = balances[0]
                    reserve1 = balances[1]
                else:
                    continue

            rate_0_to_1 = (reserve1 / reserve0) * (1 - fee)
            rate_1_to_0 = (reserve0 / reserve1) * (1 - fee)

            if rate_0_to_1 > 0:
                new_graph.add_edge(
                    token0, token1,
                    weight=-math.log(rate_0_to_1),
                    rate=rate_0_to_1,
                    pool=pool_addr,
                    dex=dex,
                    fee=fee,
                    token_in=token0,
                    token_out=token1,
                )

            if rate_1_to_0 > 0:
                new_graph.add_edge(
                    token1, token0,
                    weight=-math.log(rate_1_to_0),
                    rate=rate_1_to_0,
                    pool=pool_addr,
                    dex=dex,
                    fee=fee,
                    token_in=token1,
                    token_out=token0,
                )

        self._graph = new_graph
        self._last_update += 1
        logger.debug(f"Graph rebuilt: {self._graph.number_of_nodes()} nodes, {self._graph.number_of_edges()} edges")
        return self._graph

    def update_edge(
        self,
        token_in: str,
        token_out: str,
        rate: float,
        pool: str,
        dex: str,
        fee: float,
    ):
        """Incrementally update a single edge without rebuilding the graph."""
        if rate > 0:
            self._graph.add_edge(
                token_in, token_out,
                weight=-math.log(rate),
                rate=rate,
                pool=pool,
                dex=dex,
                fee=fee,
                token_in=token_in,
                token_out=token_out,
            )

    def remove_edge(self, token_in: str, token_out: str, pool: str):
        """Remove an edge from the graph."""
        if self._graph.has_edge(token_in, token_out):
            for key, edge_data in list(self._graph[token_in][token_out].items()):
                if edge_data.get("pool") == pool:
                    self._graph.remove_edge(token_in, token_out, key)

    @property
    def graph(self) -> nx.MultiDiGraph:
        return self._graph

    @property
    def node_count(self) -> int:
        return self._graph.number_of_nodes()

    @property
    def edge_count(self) -> int:
        return self._graph.number_of_edges()

    def get_neighbors(self, token: str) -> Set[str]:
        """Get all neighboring tokens for a given token."""
        return set(self._graph.successors(token))
