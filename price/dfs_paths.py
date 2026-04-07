import logging
from typing import Dict, List, Any, Set, Optional

import networkx as nx

from config import MAJOR_TOKENS, MAX_HOPS

logger = logging.getLogger(__name__)


def find_dfs_paths(
    G: nx.MultiDiGraph,
    max_hops: int = MAX_HOPS,
    start_tokens: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Depth-limited DFS path finder for arbitrage routes.

    Finds all cycles starting and ending at major tokens.
    """
    opportunities = []

    if start_tokens is None:
        start_tokens = list(set(G.nodes) & MAJOR_TOKENS)
        if not start_tokens:
            start_tokens = list(G.nodes)[:10]

    for start in start_tokens:
        visited_paths: Set[tuple] = set()
        stack = [(start, [start], 1.0, [])]

        while stack:
            current, path, cumulative_rate, steps = stack.pop()

            if len(path) > max_hops + 1:
                continue

            for neighbor, key, edge_data in G.out_edges(current, keys=True, data=True):
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

    logger.debug(f"DFS found {len(opportunities)} candidate paths")
    return opportunities
