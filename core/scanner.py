import asyncio
import logging
import time
from typing import Dict, List, Optional, Set, Tuple, Any, Callable, Awaitable
from datetime import datetime, timezone

from config import (
    CONFIG, MIN_PROFIT_USD, MAX_HOPS, DISCOVERY_INTERVAL_SEC,
    WETH, USDC, USDT, MAJOR_TOKENS
)
from simulation.slippage_model import compute_optimal_borrow_amount

logger = logging.getLogger(__name__)


class ScannerEngine:
    """Main scanner engine that coordinates all components on every block."""

    def __init__(
        self,
        rpc_manager,
        block_listener,
        pool_registry,
        reserve_fetcher,
        graph_builder,
        opportunity_engine,
        flashloan_checker,
        simulator,
        profit_calculator,
        database,
        dashboard=None,
        telegram_alert=None,
    ):
        self._rpc_manager = rpc_manager
        self._block_listener = block_listener
        self._pool_registry = pool_registry
        self._reserve_fetcher = reserve_fetcher
        self._graph_builder = graph_builder
        self._opportunity_engine = opportunity_engine
        self._flashloan_checker = flashloan_checker
        self._simulator = simulator
        self._profit_calculator = profit_calculator
        self._database = database
        self._dashboard = dashboard
        self._telegram_alert = telegram_alert

        self._running = False
        self._scan_count = 0
        self._opportunities_found = 0
        self._last_discovery_time = 0.0
        self._seen_this_block: Set[str] = set()
        self._block_lock = asyncio.Lock()
        self._start_time: Optional[float] = None

        self._block_listener.on_new_block(self._on_new_block)

    async def start(self):
        """Start the scanner engine."""
        self._running = True
        self._start_time = time.time()
        logger.info("ScannerEngine starting...")

        await self._rpc_manager.start()
        await self._block_listener.start()

        asyncio.create_task(self._periodic_discovery_loop())
        asyncio.create_task(self._stats_loop())

        logger.info("ScannerEngine started and listening for blocks")

    async def stop(self):
        """Stop the scanner engine."""
        self._running = False
        await self._block_listener.stop()
        await self._rpc_manager.stop()
        logger.info("ScannerEngine stopped")

    async def _on_new_block(self, block_header: Dict[str, Any]):
        """Callback triggered on every new block."""
        if not self._running:
            return

        block_number = block_header.get("number")
        if block_number is None:
            return

        async with self._block_lock:
            self._seen_this_block.clear()

        self._scan_count += 1
        logger.debug(f"Processing block #{block_number} (scan #{self._scan_count})")

        try:
            await self._process_block(block_header)
        except Exception as e:
            logger.error(f"Error processing block #{block_number}: {e}", exc_info=True)

        if self._dashboard:
            self._dashboard.update(
                block_number=block_number,
                scan_count=self._scan_count,
                opportunities_found=self._opportunities_found,
                rpc_healthy=self._rpc_manager.healthy_count,
                pools_tracked=self._pool_registry.pool_count,
            )

    async def _process_block(self, block_header: Dict[str, Any]):
        """Process a single block: fetch reserves, build graph, find opportunities, simulate."""
        block_number = block_header.get("number")
        timestamp = block_header.get("timestamp", int(time.time()))

        pools = self._pool_registry.get_active_pools()
        if not pools:
            logger.debug("No pools tracked yet, skipping block")
            return

        reserves = await self._reserve_fetcher.fetch_reserves(pools)

        graph = self._graph_builder.build_graph(pools, reserves)

        candidates = await self._opportunity_engine.find_opportunities(
            graph, reserves, max_hops=MAX_HOPS
        )

        for candidate in candidates:
            route_key = self._make_route_key(candidate)
            async with self._block_lock:
                if route_key in self._seen_this_block:
                    continue
                self._seen_this_block.add(route_key)

            result = await self._evaluate_candidate(candidate, reserves, block_number, timestamp)

            if result and result.get("viable"):
                self._opportunities_found += 1
                await self._log_opportunity(result)

    async def _evaluate_candidate(
        self, candidate: Dict, reserves: Dict, block_number: int, timestamp: int
    ) -> Optional[Dict]:
        """Evaluate a candidate opportunity: flash-loan check, simulation, profit calc."""
        token_in = candidate.get("token_in") or candidate.get("path", [None])[0]
        if not token_in:
            return None

        steps = candidate.get("steps", [])
        if not steps:
            return None

        first_pool_addr = steps[0].get("pool", "")
        pool_meta = self._pool_registry.get_pool(first_pool_addr) or {}
        pool_tvl = pool_meta.get("tvl_usd", 10_000)

        if candidate.get("borrow_amount", 0) <= 0:
            candidate["borrow_amount"] = compute_optimal_borrow_amount(pool_tvl, token_in)

        fl_source = await self._flashloan_checker(token_in, candidate["borrow_amount"])
        if not fl_source:
            return None

        candidate["fl_source"] = fl_source

        simulation = await self._simulator.simulate_flashloan_arb(
            candidate, reserves, block_number
        )

        if not simulation or not simulation.get("viable"):
            return None

        stress_pass = await self._simulator.stress_test(
            candidate, reserves, block_number
        )
        if not stress_pass:
            return None

        simulation["block_number"] = block_number
        simulation["timestamp"] = timestamp
        simulation["candidate"] = candidate
        simulation["stress_test_pass"] = True
        simulation["simulation_pass"] = True

        return simulation

    async def _log_opportunity(self, result: Dict):
        """Log a confirmed profitable opportunity."""
        await self._database.log_opportunity(result)

        if self._telegram_alert and result["net_profit_usd"] >= CONFIG["telegram_alert_threshold_usd"]:
            try:
                await self._telegram_alert.send(result)
            except Exception as e:
                logger.error(f"Telegram alert failed: {e}")

        logger.info(
            f"OPPORTUNITY FOUND | Block #{result['block_number']} | "
            f"Net profit: ${result['net_profit_usd']:.2f} | "
            f"Path: {' -> '.join(result.get('path', []))} | "
            f"DEXes: {', '.join(result.get('dexes', []))}"
        )

    async def _periodic_discovery_loop(self):
        """Run full pool discovery every DISCOVERY_INTERVAL_SEC seconds."""
        while self._running:
            try:
                await self._run_discovery()
            except Exception as e:
                logger.error(f"Discovery loop error: {e}")
            await asyncio.sleep(DISCOVERY_INTERVAL_SEC)

    async def _run_discovery(self):
        """Run full pool discovery across all DEXs."""
        logger.info("Running full pool discovery...")
        w3 = await self._rpc_manager.get_w3()
        new_pools = await self._pool_registry.discover_pools(w3)
        logger.info(f"Discovery complete: {len(new_pools)} new pools found, "
                     f"{self._pool_registry.pool_count} total tracked")
        self._last_discovery_time = time.time()

    async def _stats_loop(self):
        """Periodically log scanner statistics."""
        while self._running:
            await asyncio.sleep(60)
            if self._start_time:
                elapsed = time.time() - self._start_time
                rate = self._scan_count / elapsed if elapsed > 0 else 0
                logger.info(
                    f"Scanner stats | Scans: {self._scan_count} | "
                    f"Rate: {rate:.1f} scans/sec | "
                    f"Opportunities: {self._opportunities_found} | "
                    f"Pools: {self._pool_registry.pool_count} | "
                    f"RPC healthy: {self._rpc_manager.healthy_count}"
                )

    @staticmethod
    def _make_route_key(candidate: Dict) -> str:
        """Create a unique key for a route to deduplicate within a block."""
        path = candidate.get("path", [])
        dexes = candidate.get("dexes", [])
        return f"{'-'.join(path)}|{'-'.join(dexes)}"

    @property
    def scan_count(self) -> int:
        return self._scan_count

    @property
    def opportunities_found(self) -> int:
        return self._opportunities_found

    @property
    def is_running(self) -> bool:
        return self._running
