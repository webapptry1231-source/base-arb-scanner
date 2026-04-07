import os
import csv
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from config import CSV_EXPORT_PATH

logger = logging.getLogger(__name__)


class CSVExporter:
    """Exports opportunity data to CSV for spreadsheet analysis."""

    def __init__(self, export_path: str = CSV_EXPORT_PATH):
        self._export_path = export_path
        self._headers = [
            "timestamp",
            "block_number",
            "route_type",
            "path",
            "dexes",
            "pools",
            "borrow_amount",
            "borrow_token",
            "fl_source",
            "fl_fee_usd",
            "gross_profit_usd",
            "swap_fees_usd",
            "gas_used",
            "gas_cost_usd",
            "net_profit_usd",
            "slippage_applied",
            "survived_blocks",
            "simulation_pass",
            "stress_test_pass",
        ]

    def export_opportunities(self, opportunities: List[Dict[str, Any]]):
        """Write a list of opportunity dicts to CSV."""
        if not opportunities:
            logger.debug("No opportunities to export")
            return

        os.makedirs(os.path.dirname(self._export_path), exist_ok=True)

        file_exists = os.path.exists(self._export_path)

        with open(self._export_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self._headers, extrasaction="ignore")
            if not file_exists:
                writer.writeheader()

            for opp in opportunities:
                row = {
                    "timestamp": opp.get("timestamp", ""),
                    "block_number": opp.get("block_number", 0),
                    "route_type": opp.get("route_type", ""),
                    "path": opp.get("path", ""),
                    "dexes": opp.get("dexes", ""),
                    "pools": opp.get("pools", ""),
                    "borrow_amount": opp.get("borrow_amount", 0),
                    "borrow_token": opp.get("borrow_token", ""),
                    "fl_source": opp.get("fl_source", ""),
                    "fl_fee_usd": opp.get("fl_fee_usd", 0),
                    "gross_profit_usd": opp.get("gross_profit_usd", 0),
                    "swap_fees_usd": opp.get("swap_fees_usd", 0),
                    "gas_used": opp.get("gas_used", 0),
                    "gas_cost_usd": opp.get("gas_cost_usd", 0),
                    "net_profit_usd": opp.get("net_profit_usd", 0),
                    "slippage_applied": opp.get("slippage_applied", 0),
                    "survived_blocks": opp.get("survived_blocks", 0),
                    "simulation_pass": opp.get("simulation_pass", 0),
                    "stress_test_pass": opp.get("stress_test_pass", 0),
                }
                writer.writerow(row)

        logger.info(f"Exported {len(opportunities)} opportunities to {self._export_path}")

    def export_simulation_results(self, results: List[Dict[str, Any]], path: Optional[str] = None):
        """Export all simulation results (including failed ones) to CSV."""
        export_path = path or self._export_path.replace(".csv", "_all_simulations.csv")
        os.makedirs(os.path.dirname(export_path), exist_ok=True)

        headers = ["timestamp", "block_number", "route_type", "path", "dexes",
                    "borrow_amount", "borrow_token", "net_profit_usd", "viable"]

        with open(export_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
            writer.writeheader()

            for result in results:
                writer.writerow({
                    "timestamp": result.get("timestamp", ""),
                    "block_number": result.get("block_number", 0),
                    "route_type": result.get("route_type", ""),
                    "path": result.get("path", ""),
                    "dexes": result.get("dexes", ""),
                    "borrow_amount": result.get("borrow_amount", 0),
                    "borrow_token": result.get("borrow_token", ""),
                    "net_profit_usd": result.get("net_profit_usd", 0),
                    "viable": result.get("viable", False),
                })

        logger.info(f"Exported {len(results)} simulation results to {export_path}")
