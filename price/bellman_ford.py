import logging
from typing import Dict, List, Any, Optional

import networkx as nx

from config import MAJOR_TOKENS, MAX_HOPS

logger = logging.getLogger(__name__)


def find_negative_cycles(G: nx.MultiDiGraph, start_tokens: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Find negative cycles in the price graph using Bellman-Ford.

    Returns list of opportunities with cycle path and metadata.
    """
    opportunities = []

    if start_tokens is None:
        start_tokens = list(set(G.nodes) & MAJOR_TOKENS)
        if not start_tokens:
            start_tokens = list(G.nodes)[:10]

    for start in start_tokens:
        if start not in G:
            continue

        try:
            cycle = nx.find_negative_cycle(G, start, weight="weight")
        except (nx.NetworkXNoCycle, nx.NetworkXError):
            continue
        except Exception as e:
            logger.debug(f"Bellman-Ford error for {start}: {e}")
            continue

        if len(cycle) < 3:
            continue

        cycle_edges = []
        for i in range(len(cycle) - 1):
            u, v = cycle[i], cycle[i + 1]
            if G.has_edge(u, v):
                edge_data = list(G.get_edge_data(u, v).values())[0]
                cycle_edges.append(edge_data)

        if not cycle_edges:
            continue

        product_rate = 1.0
        for e in cycle_edges:
            product_rate *= e.get("rate", 0)

        if product_rate > 1.001:
            opportunities.append({
                "type": "bellman_ford",
                "path": cycle[:-1],
                "dexes": [e.get("dex", "unknown") for e in cycle_edges],
                "pools": [e.get("pool", "") for e in cycle_edges],
                "token_in": cycle[0],
                "effective_rate": product_rate,
                "steps": [
                    {
                        "dex": e.get("dex", "unknown"),
                        "pool": e.get("pool", ""),
                        "token_in": e.get("token_in", cycle[i]),
                        "token_out": e.get("token_out", cycle[i + 1]),
                    }
                    for i, e in enumerate(cycle_edges)
                ],
            })

    logger.debug(f"Bellman-Ford found {len(opportunities)} negative cycles")
    return opportunities
