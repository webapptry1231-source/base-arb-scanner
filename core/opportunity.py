import math
import logging
from typing import Dict, List, Optional, Set, Tuple, Any

import networkx as nx

from config import MAX_HOPS, MAJOR_TOKENS

logger = logging.getLogger(__name__)


class OpportunityEngine:
    """Finds arbitrage opportunities using multiple algorithms."""

    def __init__(self, max_hops: int = MAX_HOPS):
        self._max_hops = max_hops
        self._last_opportunities: List[Dict] = []

    async def find_opportunities(
        self,
        graph: nx.MultiDiGraph,
        reserves: Dict,
        max_hops: Optional[int] = None,
    ) -> List[Dict]:
        """Run all opportunity detection algorithms and return combined candidates."""
        max_hops = max_hops or self._max_hops
        opportunities = []

        opportunities.extend(self._find_cross_exchange_opps(graph, reserves))
        opportunities.extend(self._find_bellman_ford_opps(graph, max_hops))
        opportunities.extend(self._find_dfs_opps(graph, reserves, max_hops))

        opportunities = self._deduplicate(opportunities)

        self._last_opportunities = opportunities
        logger.debug(f"Found {len(opportunities)} candidate opportunities this block")
        return opportunities

    def _find_cross_exchange_opps(self, graph: nx.MultiDiGraph, reserves: Dict) -> List[Dict]:
        """Algorithm A: 2-DEX cross-exchange comparison (fast, every block).

        For every known token pair that exists on multiple DEXes,
        compare buy/sell prices to find discrepancies.
        """
        opportunities = []
        token_pairs: Dict[Tuple[str, str], List[Dict]] = {}

        for u, v, data in graph.edges(data=True):
            pair_key = tuple(sorted([u, v]))
            if pair_key not in token_pairs:
                token_pairs[pair_key] = []
            token_pairs[pair_key].append({
                "token_in": u,
                "token_out": v,
                "pool": data.get("pool", ""),
                "dex": data.get("dex", ""),
                "rate": data.get("rate", 0),
                "fee": data.get("fee", 0),
            })

        for pair_key, edges in token_pairs.items():
            if len(edges) < 2:
                continue

            for i, buy_edge in enumerate(edges):
                for j, sell_edge in enumerate(edges):
                    if i == j:
                        continue
                    if buy_edge["token_in"] != sell_edge["token_out"]:
                        continue

                    buy_rate = buy_edge["rate"]
                    sell_rate = sell_edge["rate"]

                    if buy_rate > 0 and sell_rate > 0:
                        effective_rate = buy_rate * sell_rate
                        if effective_rate > 1.001:
                            opportunities.append({
                                "type": "cross_exchange",
                                "path": [buy_edge["token_in"], buy_edge["token_out"], buy_edge["token_in"]],
                                "dexes": [buy_edge["dex"], sell_edge["dex"]],
                                "pools": [buy_edge["pool"], sell_edge["pool"]],
                                "token_in": buy_edge["token_in"],
                                "effective_rate": effective_rate,
                                "steps": [
                                    {
                                        "dex": buy_edge["dex"],
                                        "pool": buy_edge["pool"],
                                        "token_in": buy_edge["token_in"],
                                        "token_out": buy_edge["token_out"],
                                    },
                                    {
                                        "dex": sell_edge["dex"],
                                        "pool": sell_edge["pool"],
                                        "token_in": sell_edge["token_in"],
                                        "token_out": sell_edge["token_out"],
                                    },
                                ],
                            })

        return opportunities

    def _find_bellman_ford_opps(self, graph: nx.MultiDiGraph, max_hops: int) -> List[Dict]:
        """Algorithm B: Bellman-Ford negative-cycle detection for triangular and multi-hop arbs."""
        opportunities = []
        start_tokens = set(graph.nodes) & MAJOR_TOKENS
        if not start_tokens:
            start_tokens = set(graph.nodes)

        for start in start_tokens:
            try:
                cycle = nx.find_negative_cycle(graph, start, weight="weight")
            except (nx.NetworkXNoCycle, nx.NetworkXError):
                continue
            except Exception:
                continue

            if len(cycle) < 3 or len(cycle) - 1 > max_hops:
                continue

            cycle_edges = []
            for i in range(len(cycle) - 1):
                u, v = cycle[i], cycle[i + 1]
                if graph.has_edge(u, v):
                    edge_data = list(graph.get_edge_data(u, v).values())[0]
                    cycle_edges.append(edge_data)

            if not cycle_edges:
                continue

            path = cycle[:-1]
            dexes = [e.get("dex", "unknown") for e in cycle_edges]
            pools = [e.get("pool", "") for e in cycle_edges]

            product_rate = 1.0
            for e in cycle_edges:
                product_rate *= e.get("rate", 0)

            if product_rate > 1.001:
                steps = []
                for i, e in enumerate(cycle_edges):
                    steps.append({
                        "dex": e.get("dex", "unknown"),
                        "pool": e.get("pool", ""),
                        "token_in": e.get("token_in", cycle[i]),
                        "token_out": e.get("token_out", cycle[i + 1]),
                    })

                opportunities.append({
                    "type": "bellman_ford",
                    "path": path,
                    "dexes": dexes,
                    "pools": pools,
                    "token_in": path[0],
                    "effective_rate": product_rate,
                    "steps": steps,
                })

        return opportunities

    def _find_dfs_opps(self, graph: nx.MultiDiGraph, reserves: Dict, max_hops: int) -> List[Dict]:
        """Depth-limited DFS as supplementary path finder."""
        opportunities = []
        start_tokens = set(graph.nodes) & MAJOR_TOKENS
        if not start_tokens:
            start_tokens = set(graph.nodes)

        for start in start_tokens:
            visited_paths = set()
            stack = [(start, [start], 1.0, [])]

            while stack:
                current, path, cumulative_rate, steps = stack.pop()

                if len(path) > max_hops + 1:
                    continue

                for neighbor, key, edge_data in graph.out_edges(current, keys=True, data=True):
                    if neighbor in path[:-1]:
                        continue

                    rate = edge_data.get("rate", 0)
                    if rate <= 0:
                        continue

                    new_rate = cumulative_rate * rate
                    new_path = path + [neighbor]
                    new_steps = steps + [{
                        "dex": edge_data.get("dex", "unknown"),
                        "pool": edge_data.get("pool", ""),
                        "token_in": current,
                        "token_out": neighbor,
                    }]

                    if neighbor == start and len(new_path) >= 3:
                        path_key = tuple(new_path[:-1])
                        if path_key not in visited_paths:
                            visited_paths.add(path_key)

                            if new_rate > 1.001:
                                opportunities.append({
                                    "type": "dfs",
                                    "path": new_path[:-1],
                                    "dexes": [s["dex"] for s in new_steps],
                                    "pools": [s["pool"] for s in new_steps],
                                    "token_in": start,
                                    "effective_rate": new_rate,
                                    "steps": new_steps,
                                })
                    elif len(new_path) <= max_hops:
                        stack.append((neighbor, new_path, new_rate, new_steps))

        return opportunities

    def _deduplicate(self, opportunities: List[Dict]) -> List[Dict]:
        """Remove duplicate opportunities (same path + same dexes)."""
        seen: Set[str] = set()
        unique = []

        for opp in opportunities:
            key = (
                tuple(opp.get("path", [])),
                tuple(opp.get("dexes", [])),
            )
            if key not in seen:
                seen.add(key)
                unique.append(opp)

        return unique

    @property
    def last_opportunities(self) -> List[Dict]:
        return list(self._last_opportunities)
