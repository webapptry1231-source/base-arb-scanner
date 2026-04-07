import logging
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout

logger = logging.getLogger(__name__)


class Dashboard:
    """Rich console dashboard showing live scanner status."""

    def __init__(self):
        self._console = Console()
        self._block_number: int = 0
        self._scan_count: int = 0
        self._opportunities_found: int = 0
        self._rpc_healthy: int = 0
        self._pools_tracked: int = 0
        self._scan_rate: float = 0.0
        self._running = False

    def update(
        self,
        block_number: int = 0,
        scan_count: int = 0,
        opportunities_found: int = 0,
        rpc_healthy: int = 0,
        pools_tracked: int = 0,
        scan_rate: float = 0.0,
    ):
        """Update dashboard with latest values."""
        self._block_number = block_number or self._block_number
        self._scan_count = scan_count or self._scan_count
        self._opportunities_found = opportunities_found or self._opportunities_found
        self._rpc_healthy = rpc_healthy or self._rpc_healthy
        self._pools_tracked = pools_tracked or self._pools_tracked
        self._scan_rate = scan_rate or self._scan_rate

    def _build_table(self) -> Table:
        """Build the main status table."""
        table = Table(title="BaseArbScanner - Live Dashboard", show_header=False, box=None)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Block Number", f"#{self._block_number}")
        table.add_row("Total Scans", str(self._scan_count))
        table.add_row("Scan Rate", f"{self._scan_rate:.1f} scans/sec")
        table.add_row("Opportunities Found", str(self._opportunities_found))
        table.add_row("Pools Tracked", str(self._pools_tracked))
        table.add_row("RPC Endpoints Healthy", f"{self._rpc_healthy}/3")

        return table

    def render(self) -> Panel:
        """Render the full dashboard."""
        table = self._build_table()
        return Panel(table, title="BaseArbScanner", border_style="blue")

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
        """Print a formatted opportunity alert."""
        self._console.print(
            Panel(
                f"[bold green]Net Profit: ${result['net_profit_usd']:.2f}[/bold green]\n"
                f"Block: #{result.get('block_number', 'N/A')}\n"
                f"Path: {' -> '.join(result.get('path', []))}\n"
                f"DEXes: {', '.join(result.get('dexes', []))}\n"
                f"Gas: {result.get('gas_used', 0):,} units (${result.get('gas_cost_usd', 0):.4f})\n"
                f"FL Source: {result.get('fl_source', {}).get('name', 'N/A')}",
                title="💰 ARBITRAGE OPPORTUNITY",
                border_style="green",
            )
        )
