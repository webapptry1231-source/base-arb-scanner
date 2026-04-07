import asyncio
import logging
import time
import uuid
from typing import Dict, List, Optional, Set, Tuple, Any, Callable, Awaitable
from datetime import datetime, timezone

from config import (
    CONFIG, MIN_PROFIT_USD, MAX_HOPS, DISCOVERY_INTERVAL_SEC,
    WETH, USDC, USDT, MAJOR_TOKENS, RPC_MAX_CALLS_SEC
)
from simulation.slippage_model import compute_optimal_borrow_amount

logger = logging.getLogger(__name__)


class ScannerEngine:
    """Main scanner engine that coordinates all components on every block (free-tier v1.2)."""

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
        stats_tracker=None,
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
        self._stats_tracker = stats_tracker

        self._running = False
        self._scan_count = 0
        self._opportunities_found = 0
        self._last_discovery_time = 0.0
        self._seen_this_block: Set[str] = set()
        self._block_lock = asyncio.Lock()
        self._start_time: Optional[float] = None
        self._free_tier_mode = CONFIG.get("free_tier_mode", True)
        self._current_rps = 0
        self._last_rps_reset = time.time()

        self._block_listener.on_new_block(self._on_new_block)

    async def start(self):
        """Start the scanner engine."""
        self._running = True
        self._start_time = time.time()
        logger.info("ScannerEngine starting (free-tier mode)...")

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
        self._update_rps_counter()

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
                scan_rate=self._stats_tracker.get_scan_rate() if self._stats_tracker else 0,
                rpc_provider=self._rpc_manager.current_endpoint,
                rpc_latency_ms=self._rpc_manager.avg_latency_ms,
                estimated_cu=self._rpc_manager.estimated_cu_used,
                rotations=self._rpc_manager.rotation_count,
                free_tier_throttled=self._current_rps > RPC_MAX_CALLS_SEC,
            )

    async def _process_block(self, block_header: Dict[str, Any]):
        """Process a single block: fetch reserves, build graph, find opportunities, simulate."""
        if self._free_tier_mode and self._current_rps > RPC_MAX_CALLS_SEC - 2:
            await asyncio.sleep(0.5)

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
            elif result:
                if self._stats_tracker:
                    self._stats_tracker.record_discard()

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

        net_profit = simulation.get("net_profit_usd", 0)
        net_after_buffer = net_profit * 0.75

        rpc_provider = self._rpc_manager.current_endpoint
        if "drpc" in rpc_provider.lower():
            provider_name = "dRPC"
        elif "alchemy" in rpc_provider.lower():
            provider_name = "Alchemy"
        elif "ankr" in rpc_provider.lower():
            provider_name = "Ankr"
        elif "1rpc" in rpc_provider.lower():
            provider_name = "1RPC"
        else:
            provider_name = "Unknown"

        simulation["block_number"] = block_number
        simulation["timestamp"] = timestamp
        simulation["candidate"] = candidate
        simulation["stress_test_pass"] = True
        simulation["simulation_pass"] = True
        simulation["rpc_provider"] = provider_name
        simulation["rpc_latency_ms"] = self._rpc_manager.avg_latency_ms
        simulation["estimated_cu_used"] = self._rpc_manager.estimated_cu_used
        simulation["net_after_25pct_buffer"] = net_after_buffer
        simulation["false_positive_flags"] = []
        simulation["free_tier_throttled"] = self._current_rps > RPC_MAX_CALLS_SEC
        simulation["log_uuid"] = str(uuid.uuid4())
        simulation["tvl_usd"] = pool_tvl
        simulation["price_impact"] = candidate.get("price_impact", 0)
        simulation["borrow_amount_usd"] = candidate.get("borrow_amount_usd", 0)

        return simulation

    async def _log_opportunity(self, result: Dict):
        """Log a confirmed profitable opportunity with full free-tier schema."""
        await self._database.log_opportunity(result)

        if self._stats_tracker:
            self._stats_tracker.record_opportunity(result)

        if self._dashboard:
            self._dashboard.print_opportunity(result)

        if self._telegram_alert and result.get("net_profit_usd", 0) >= CONFIG["telegram_alert_threshold_usd"]:
            try:
                await self._telegram_alert.send(result)
            except Exception as e:
                logger.error(f"Telegram alert failed: {e}")

        logger.info(
            f"OPPORTUNITY FOUND | Block #{result['block_number']} | "
            f"RPC: {result.get('rpc_provider', 'N/A')} | "
            f"Latency: {result.get('rpc_latency_ms', 0):.1f}ms | "
            f"CU: ~{result.get('estimated_cu_used', 0):.0f} | "
            f"Net profit: ${result['net_profit_usd']:.2f} | "
            f"After buffer: ${result.get('net_after_25pct_buffer', 0):.2f} | "
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
            if self._start_time and self._stats_tracker:
                elapsed = time.time() - self._start_time
                rate = self._scan_count / elapsed if elapsed > 0 else 0
                summary = self._stats_tracker.get_summary()
                logger.info(
                    f"Scanner stats | Scans: {self._scan_count} | "
                    f"Rate: {rate:.1f} scans/sec | "
                    f"Opportunities: {self._opportunities_found} | "
                    f"Pools: {self._pool_registry.pool_count} | "
                    f"RPC healthy: {self._rpc_manager.healthy_count} | "
                    f"Avg latency: {summary['avg_latency_ms']:.1f}ms | "
                    f"Rotations: {summary['rpc_rotations']} | "
                    f"CU burn: {summary['cu_burn_estimate']:.0f}"
                )

    def _update_rps_counter(self):
        """Track current requests per second for free-tier throttling."""
        now = time.time()
        if now - self._last_rps_reset >= 1.0:
            self._current_rps = 0
            self._last_rps_reset = now
        self._current_rps += 1

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
