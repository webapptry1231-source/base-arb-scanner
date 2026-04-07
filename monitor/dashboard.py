import logging
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout

logger = logging.getLogger(__name__)


class Dashboard:
    """Rich console dashboard showing live scanner status (free-tier enhanced)."""

    def __init__(self):
        self._console = Console()
        self._block_number: int = 0
        self._scan_count: int = 0
        self._opportunities_found: int = 0
        self._rpc_healthy: int = 0
        self._pools_tracked: int = 0
        self._scan_rate: float = 0.0
        self._rpc_provider: str = "dRPC"
        self._rpc_latency_ms: float = 0.0
        self._estimated_cu: float = 0.0
        self._rotations: int = 0
        self._free_tier_throttled: bool = False
        self._running = False

    def update(
        self,
        block_number: int = 0,
        scan_count: int = 0,
        opportunities_found: int = 0,
        rpc_healthy: int = 0,
        pools_tracked: int = 0,
        scan_rate: float = 0.0,
        rpc_provider: str = "",
        rpc_latency_ms: float = 0.0,
        estimated_cu: float = 0.0,
        rotations: int = 0,
        free_tier_throttled: bool = False,
    ):
        """Update dashboard with latest values."""
        self._block_number = block_number or self._block_number
        self._scan_count = scan_count or self._scan_count
        self._opportunities_found = opportunities_found or self._opportunities_found
        self._rpc_healthy = rpc_healthy or self._rpc_healthy
        self._pools_tracked = pools_tracked or self._pools_tracked
        self._scan_rate = scan_rate or self._scan_rate
        if rpc_provider:
            self._rpc_provider = rpc_provider
        if rpc_latency_ms > 0:
            self._rpc_latency_ms = rpc_latency_ms
        if estimated_cu > 0:
            self._estimated_cu = estimated_cu
        if rotations > 0:
            self._rotations = rotations
        self._free_tier_throttled = free_tier_throttled

    def _build_table(self) -> Table:
        """Build the main status table."""
        table = Table(title="BaseArbScanner - Free-Tier Dashboard", show_header=False, box=None)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Block Number", f"#{self._block_number}")
        table.add_row("Total Scans", str(self._scan_count))
        table.add_row("Scan Rate", f"{self._scan_rate:.1f} scans/sec")
        table.add_row("Opportunities Found", str(self._opportunities_found))
        table.add_row("Pools Tracked", str(self._pools_tracked))
        table.add_row("RPC Endpoints Healthy", f"{self._rpc_healthy}/4")
        table.add_row("Active RPC", self._rpc_provider)
        table.add_row("RPC Latency", f"{self._rpc_latency_ms:.1f}ms")
        table.add_row("Est. CU Used", f"{self._estimated_cu:.0f}")
        table.add_row("Rotations", str(self._rotations))
        throttled_str = "YES" if self._free_tier_throttled else "no"
        table.add_row("Throttled", throttled_str)

        return table

    def render(self) -> Panel:
        """Render the full dashboard."""
        table = self._build_table()
        return Panel(table, title="BaseArbScanner (FREE TIER)", border_style="blue")

    def start_live(self):
        """Start the live dashboard display."""
        self._running = True
        self._live = Live(self.render(), console=self._console, refresh_per_second=2)
        self._live.start()

    def update_live(self):
        """Update the live display."""
        if self._running:
            self._live.update(self.render())

    def stop_live(self):
        """Stop the live display."""
        self._running = False
        if hasattr(self, "_live"):
            self._live.stop()

    def print_opportunity(self, result: dict):
        """Print a formatted free-tier opportunity alert."""
        self._console.print(
            Panel(
                f"[bold green]Net Profit: ${result.get('net_profit_usd', 0):.2f}[/bold green]\n"
                f"Block: #{result.get('block_number', 'N/A')} | "
                f"RPC: {result.get('rpc_provider', 'N/A')} | "
                f"Latency: {result.get('rpc_latency_ms', 0):.0f}ms | "
                f"CU: ~{result.get('estimated_cu_used', 0):.0f}\n"
                f"Route: {' -> '.join(result.get('path', []))}\n"
                f"DEXes: {', '.join(result.get('dexes', []))}\n"
                f"Borrow: ${result.get('borrow_amount_usd', 0):.2f}\n"
                f"NET (after 25% buffer): ${result.get('net_after_25pct_buffer', 0):.2f}\n"
                f"TVL: ${result.get('tvl_usd', 0):.0f} | "
                f"Impact: {result.get('price_impact', 0):.2f}%\n"
                f"Sim: Atomic + 10 stress tests\n"
                f"Flags: {result.get('false_positive_flags', [])}\n"
                f"Log ID: {result.get('log_uuid', 'N/A')}",
                title="ARBITRAGE OPPORTUNITY (FREE TIER)",
                border_style="green",
            )
        )
