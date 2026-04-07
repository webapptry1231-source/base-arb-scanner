import time
import logging
from typing import Dict, Any, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class StatsTracker:
    """Tracks scanner statistics for analysis and Phase 2 gate."""

    def __init__(self):
        self._start_time: float = time.time()
        self._total_scans: int = 0
        self._total_opportunities: int = 0
        self._total_simulations: int = 0
        self._viable_simulations: int = 0
        self._total_profit_usd: float = 0.0
        self._max_profit_usd: float = 0.0
        self._profits_by_route: Dict[str, list] = defaultdict(list)
        self._profits_by_dex: Dict[str, list] = defaultdict(list)
        self._block_opportunities: Dict[int, int] = defaultdict(int)

    def record_scan(self):
        """Record a completed scan cycle."""
        self._total_scans += 1

    def record_opportunity(self, result: Dict[str, Any]):
        """Record a profitable opportunity."""
        self._total_opportunities += 1
        profit = result.get("net_profit_usd", 0)
        self._total_profit_usd += profit
        self._max_profit_usd = max(self._max_profit_usd, profit)

        route_key = "-".join(result.get("path", []))
        self._profits_by_route[route_key].append(profit)

        for dex in result.get("dexes", []):
            self._profits_by_dex[dex].append(profit)

        block = result.get("block_number", 0)
        self._block_opportunities[block] += 1

    def record_simulation(self, viable: bool = False):
        """Record any simulation (viable or not)."""
        self._total_simulations += 1
        if viable:
            self._viable_simulations += 1

    def get_scan_rate(self) -> float:
        """Get scans per second."""
        elapsed = time.time() - self._start_time
        return self._total_scans / elapsed if elapsed > 0 else 0

    def get_avg_profit(self) -> float:
        """Get average profit per opportunity."""
        if self._total_opportunities == 0:
            return 0.0
        return self._total_profit_usd / self._total_opportunities

    def get_summary(self) -> Dict[str, Any]:
        """Get a full summary of all tracked statistics."""
        return {
            "total_scans": self._total_scans,
            "total_opportunities": self._total_opportunities,
            "total_simulations": self._total_simulations,
            "viable_simulations": self._viable_simulations,
            "scan_rate": self.get_scan_rate(),
            "avg_profit_usd": self.get_avg_profit(),
            "max_profit_usd": self._max_profit_usd,
            "total_profit_usd": self._total_profit_usd,
            "uptime_seconds": time.time() - self._start_time,
            "top_routes": self._get_top_routes(5),
            "top_dexes": self._get_top_dexes(5),
        }

    def _get_top_routes(self, n: int = 5) -> list:
        """Get top N most profitable routes."""
        sorted_routes = sorted(
            self._profits_by_route.items(),
            key=lambda x: sum(x[1]),
            reverse=True,
        )
        return [
            {"route": route, "count": len(profits), "total_profit": sum(profits)}
            for route, profits in sorted_routes[:n]
        ]

    def _get_top_dexes(self, n: int = 5) -> list:
        """Get top N most profitable DEXes."""
        sorted_dexes = sorted(
            self._profits_by_dex.items(),
            key=lambda x: sum(x[1]),
            reverse=True,
        )
        return [
            {"dex": dex, "count": len(profits), "total_profit": sum(profits)}
            for dex, profits in sorted_dexes[:n]
        ]

    def check_phase2_gate(self) -> Dict[str, Any]:
        """Check if Phase 2 execution gate is met.

        Gate: 50+ confirmed profitable simulations with avg net profit > $0.80
        over at least 72 hours of uninterrupted scanning.
        """
        uptime_hours = (time.time() - self._start_time) / 3600

        gate_met = (
            self._viable_simulations >= 50
            and self.get_avg_profit() >= 0.80
            and uptime_hours >= 72
        )

        return {
            "gate_met": gate_met,
            "viable_simulations": self._viable_simulations,
            "avg_profit_usd": self.get_avg_profit(),
            "uptime_hours": uptime_hours,
            "requirements": {
                "viable_simulations": f"{self._viable_simulations}/50",
                "avg_profit": f"${self.get_avg_profit():.2f}/$0.80",
                "uptime": f"{uptime_hours:.1f}h/72h",
            },
        }
