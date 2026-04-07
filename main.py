import asyncio
import signal
import sys
import logging
from typing import Optional

from config import CONFIG
from data.logger import setup_logging
from core.rpc_manager import RPCManager
from core.block_listener import BlockListener, safe_get_block
from core.scanner import ScannerEngine
from core.opportunity import OpportunityEngine
from discovery.pool_registry import PoolRegistry
from price.graph_builder import GraphBuilder
from price.reserve_fetcher import ReserveFetcher
from flashloan.balancer_fl import BalancerFlashLoan
from flashloan.aave_v3_fl import AaveV3FlashLoan
from simulation.simulator import Simulator
from simulation.profit_calculator import ProfitCalculator
from data.database import Database
from monitor.dashboard import Dashboard
from monitor.stats_tracker import StatsTracker

logger = logging.getLogger(__name__)


async def make_flashloan_checker(balancer_fl, aave_fl):
    """Factory that returns a clean async flashloan checker callable.

    Returns an async function: async def check(token, amount) -> Optional[dict]
    """
    async def check(token: str, amount: int) -> Optional[dict]:
        if balancer_fl and await balancer_fl.check_availability(token, amount):
            return {
                "name": balancer_fl.name,
                "address": balancer_fl.address,
                "fee_rate": balancer_fl.fee_rate,
            }
        if aave_fl and await aave_fl.check_availability(token, amount):
            return {
                "name": aave_fl.name,
                "address": aave_fl.address,
                "fee_rate": aave_fl.fee_rate,
            }
        return None

    return check


class BaseArbScanner:
    """Main orchestrator for the Base chain flash-loan arbitrage scanner (free-tier v1.2)."""

    def __init__(self):
        self._setup_logging()
        self._rpc_manager = RPCManager()
        self._block_listener = BlockListener(self._rpc_manager)
        self._pool_registry = PoolRegistry()
        self._graph_builder = GraphBuilder()
        self._reserve_fetcher = None
        self._opportunity_engine = OpportunityEngine()
        self._balancer_fl = None
        self._aave_fl = None
        self._simulator = Simulator()
        self._profit_calculator = None
        self._database = Database()
        self._dashboard = Dashboard()
        self._stats_tracker = StatsTracker()
        self._scanner = None
        self._flashloan_checker = None

    def _setup_logging(self):
        """Configure logging."""
        setup_logging(log_level="INFO")

    async def initialize(self):
        """Initialize all components."""
        logger.info("Initializing BaseArbScanner (free-tier v1.2)...")

        await self._database.initialize()

        w3 = await self._rpc_manager.get_w3()
        self._reserve_fetcher = ReserveFetcher(w3)

        self._balancer_fl = BalancerFlashLoan(w3)
        self._aave_fl = AaveV3FlashLoan(w3)

        try:
            block = await safe_get_block(w3, "latest")
            base_fee = block.get("baseFeePerGas", 0)
            gas_price_gwei = (base_fee / 1e9) if base_fee else 0.1
            eth_price_usd = 3000.0
            self._simulator = Simulator(eth_price_usd=eth_price_usd)
            self._profit_calculator = ProfitCalculator(eth_price_usd=eth_price_usd)
        except Exception as e:
            logger.warning(f"Failed to fetch gas price: {e}")
            self._simulator = Simulator()
            self._profit_calculator = ProfitCalculator()

        self._flashloan_checker = await make_flashloan_checker(self._balancer_fl, self._aave_fl)

        self._scanner = ScannerEngine(
            rpc_manager=self._rpc_manager,
            block_listener=self._block_listener,
            pool_registry=self._pool_registry,
            reserve_fetcher=self._reserve_fetcher,
            graph_builder=self._graph_builder,
            opportunity_engine=self._opportunity_engine,
            flashloan_checker=self._flashloan_checker,
            simulator=self._simulator,
            profit_calculator=self._profit_calculator,
            database=self._database,
            dashboard=self._dashboard,
            stats_tracker=self._stats_tracker,
        )

        logger.info("All components initialized")

    async def start(self):
        """Start the scanner."""
        logger.info("Starting BaseArbScanner (free-tier v1.2)...")
        await self.initialize()
        await self._scanner.start()

    async def stop(self):
        """Stop the scanner gracefully."""
        logger.info("Stopping BaseArbScanner...")
        if self._scanner:
            await self._scanner.stop()
        self._database.close()
        logger.info("BaseArbScanner stopped")

    async def run(self):
        """Run the scanner until interrupted."""
        await self.start()

        stop_event = asyncio.Event()

        def handle_signal(sig, frame):
            logger.info(f"Received signal {sig}, shutting down...")
            stop_event.set()

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        await stop_event.wait()
        await self.stop()


async def main():
    """Entry point."""
    scanner = BaseArbScanner()
    await scanner.run()


if __name__ == "__main__":
    asyncio.run(main())
