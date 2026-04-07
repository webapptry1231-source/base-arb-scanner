import asyncio
import time
import logging
from typing import Optional, List, Dict, Any
from web3 import AsyncWeb3
from web3.providers.async_rpc import AsyncHTTPProvider
from config import CONFIG, HEALTH_CHECK_INTERVAL_SEC, RPC_MAX_CALLS_SEC

logger = logging.getLogger(__name__)

CALL_COST_ESTIMATES = {
    "eth_blockNumber": 1,
    "eth_getBlockByNumber": 2,
    "eth_call": 3,
    "eth_getLogs": 5,
    "default": 2,
}


class RPCManager:
    """Free-tier RPC manager with rotation, latency tracking, CU estimation, and auto-throttle.

    Rotation triggers: 429 / timeout / latency >120ms
    Health ping every 15 seconds
    Estimates CU usage per call and auto-throttles batch size / poll interval
    Logs every rotation + latency + estimated CU burn
    """

    def __init__(self):
        self._endpoints: List[str] = [CONFIG["rpc_primary"]] + CONFIG["rpc_fallbacks"]
        self._ws_endpoints: List[str] = [CONFIG["rpc_ws_primary"]] + CONFIG["rpc_ws_fallbacks"]
        self._endpoint_failures: Dict[str, int] = {ep: 0 for ep in self._endpoints}
        self._endpoint_backoff_until: Dict[str, float] = {ep: 0.0 for ep in self._endpoints}
        self._current_index: int = 0
        self._ws_current_index: int = 0
        self._w3: Optional[AsyncWeb3] = None
        self._ws_w3: Optional[AsyncWeb3] = None
        self._lock = asyncio.Lock()
        self._health_task: Optional[asyncio.Task] = None
        self._running = False

        self._latency_history: List[float] = []
        self._cu_estimate_total: float = 0.0
        self._calls_this_second: int = 0
        self._last_call_reset: float = time.time()
        self._rotation_count: int = 0
        self._last_latency: float = 0.0

        self._latency_threshold_ms = 120.0

    async def start(self):
        """Start the RPC manager and health check loop."""
        self._running = True
        await self._init_primary_connection()
        self._health_task = asyncio.create_task(self._health_check_loop())
        logger.info(f"RPCManager started with {len(self._endpoints)} endpoints (free-tier mode)")

    async def stop(self):
        """Stop the RPC manager and health check loop."""
        self._running = False
        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
        logger.info("RPCManager stopped")

    async def _init_primary_connection(self):
        """Initialize AsyncWeb3 connection to the first healthy endpoint."""
        for i, endpoint in enumerate(self._endpoints):
            if not self._is_endpoint_available(endpoint):
                continue
            start = time.time()
            try:
                w3 = AsyncWeb3(AsyncHTTPProvider(endpoint))
                await w3.eth.block_number
                latency = (time.time() - start) * 1000
                self._latency_history.append(latency)
                self._last_latency = latency
                self._current_index = i
                self._w3 = w3
                self._record_success(endpoint)
                logger.info(f"Connected to RPC: {endpoint} | latency {latency:.1f}ms")
                return
            except Exception as e:
                logger.warning(f"Failed to connect to {endpoint}: {e}")
                self._record_failure(endpoint)
        raise ConnectionError("No healthy RPC endpoints available")

    async def _test_connection(self, w3: AsyncWeb3) -> bool:
        """Test if an AsyncWeb3 connection is working."""
        try:
            block_number = await w3.eth.block_number
            return block_number > 0
        except Exception:
            return False

    def _is_endpoint_available(self, endpoint: str) -> bool:
        """Check if an endpoint is available (not in backoff)."""
        if self._endpoint_backoff_until[endpoint] > time.time():
            return False
        if self._endpoint_failures[endpoint] >= 5:
            return False
        return True

    def _record_failure(self, endpoint: str):
        """Record a failure for an endpoint and apply exponential backoff."""
        self._endpoint_failures[endpoint] += 1
        backoff_seconds = min(2 ** self._endpoint_failures[endpoint], 300)
        self._endpoint_backoff_until[endpoint] = time.time() + backoff_seconds
        logger.warning(
            f"Endpoint {endpoint} failed (attempt {self._endpoint_failures[endpoint]}). "
            f"Backoff for {backoff_seconds}s"
        )

    def _record_success(self, endpoint: str):
        """Record a success for an endpoint and reset failure counter."""
        self._endpoint_failures[endpoint] = 0
        self._endpoint_backoff_until[endpoint] = 0.0

    def _estimate_cu_for_call(self, method: str = "default") -> float:
        """Estimate compute units used for an RPC call."""
        cu = CALL_COST_ESTIMATES.get(method, CALL_COST_ESTIMATES["default"])
        self._cu_estimate_total += cu
        return cu

    def _check_rate_limit(self) -> bool:
        """Check if we're exceeding the free-tier rate limit. Returns True if throttled."""
        now = time.time()
        if now - self._last_call_reset >= 1.0:
            self._calls_this_second = 0
            self._last_call_reset = now

        self._calls_this_second += 1
        if self._calls_this_second > RPC_MAX_CALLS_SEC:
            return True
        return False

    async def _rotate_endpoint(self, reason: str = "unknown"):
        """Rotate to the next available endpoint."""
        old_endpoint = self._endpoints[self._current_index]
        for i in range(len(self._endpoints)):
            idx = (self._current_index + 1 + i) % len(self._endpoints)
            endpoint = self._endpoints[idx]
            if self._is_endpoint_available(endpoint):
                start = time.time()
                try:
                    w3 = AsyncWeb3(AsyncHTTPProvider(endpoint))
                    await w3.eth.block_number
                    latency = (time.time() - start) * 1000
                    self._latency_history.append(latency)
                    self._last_latency = latency
                    self._current_index = idx
                    self._w3 = w3
                    self._rotation_count += 1
                    self._record_success(endpoint)
                    logger.info(
                        f"RPC rotated [{reason}]: {old_endpoint} -> {endpoint} | "
                        f"latency {latency:.1f}ms | rotation #{self._rotation_count}"
                    )
                    return
                except Exception:
                    self._record_failure(endpoint)
        logger.error(f"All RPC endpoints down, cannot rotate (reason: {reason})")

    async def get_w3(self) -> AsyncWeb3:
        """Get a working AsyncWeb3 instance, rotating through endpoints if needed."""
        async with self._lock:
            if self._check_rate_limit():
                await asyncio.sleep(0.5)

            if self._w3:
                start = time.time()
                try:
                    await self._w3.eth.block_number
                    latency = (time.time() - start) * 1000
                    self._latency_history.append(latency)
                    self._last_latency = latency
                    self._estimate_cu_for_call("eth_blockNumber")

                    if latency > self._latency_threshold_ms:
                        await self._rotate_endpoint(reason=f"latency {latency:.0f}ms > {self._latency_threshold_ms:.0f}ms")
                    return self._w3
                except Exception:
                    pass

            for i in range(len(self._endpoints)):
                idx = (self._current_index + i) % len(self._endpoints)
                endpoint = self._endpoints[idx]

                if not self._is_endpoint_available(endpoint):
                    continue

                start = time.time()
                try:
                    w3 = AsyncWeb3(AsyncHTTPProvider(endpoint))
                    await w3.eth.block_number
                    latency = (time.time() - start) * 1000
                    self._latency_history.append(latency)
                    self._last_latency = latency
                    self._current_index = idx
                    self._w3 = w3
                    self._record_success(endpoint)
                    self._estimate_cu_for_call("eth_blockNumber")
                    logger.info(f"Switched to RPC endpoint: {endpoint} | latency {latency:.1f}ms")
                    return w3
                except Exception as e:
                    err_str = str(e)
                    if "429" in err_str or "rate limit" in err_str.lower():
                        self._record_failure(endpoint)
                        await self._rotate_endpoint(reason="429 rate limit")
                    else:
                        logger.warning(f"Failed to connect to {endpoint}: {e}")
                        self._record_failure(endpoint)

            raise ConnectionError("All RPC endpoints are unavailable")

    async def get_ws_w3(self) -> AsyncWeb3:
        """Get a WebSocket AsyncWeb3 instance for subscriptions."""
        if self._ws_w3:
            try:
                block_number = await self._ws_w3.eth.block_number
                if block_number > 0:
                    return self._ws_w3
            except Exception:
                pass

        for i, ws_endpoint in enumerate(self._ws_endpoints):
            if not ws_endpoint:
                continue
            try:
                from web3.providers.websocket import WebSocketProvider
                self._ws_w3 = AsyncWeb3(WebSocketProvider(ws_endpoint))
                self._ws_current_index = i
                logger.info(f"Connected to WebSocket RPC: {ws_endpoint}")
                return self._ws_w3
            except Exception as e:
                logger.warning(f"WebSocket connection failed for {ws_endpoint}: {e}")

        logger.warning("All WebSocket endpoints failed. Falling back to HTTP polling.")
        return await self.get_w3()

    async def _health_check_loop(self):
        """Periodically check health of all endpoints (every 15s for free-tier)."""
        while self._running:
            try:
                await self._check_all_endpoints()
            except Exception as e:
                logger.error(f"Health check error: {e}")
            await asyncio.sleep(HEALTH_CHECK_INTERVAL_SEC)

    async def _check_all_endpoints(self):
        """Check health of all registered endpoints and log latency."""
        for endpoint in self._endpoints:
            if not self._is_endpoint_available(endpoint):
                continue
            try:
                start = time.time()
                w3 = AsyncWeb3(AsyncHTTPProvider(endpoint))
                block_number = await w3.eth.block_number
                latency = (time.time() - start) * 1000
                if block_number > 0:
                    self._record_success(endpoint)
                    self._latency_history.append(latency)
                    logger.debug(f"Endpoint healthy: {endpoint} (block {block_number}, {latency:.1f}ms)")
                    if latency > self._latency_threshold_ms and endpoint == self._endpoints[self._current_index]:
                        await self._rotate_endpoint(reason=f"health latency {latency:.0f}ms")
                else:
                    self._record_failure(endpoint)
            except Exception as e:
                logger.debug(f"Endpoint unhealthy: {endpoint} - {e}")
                self._record_failure(endpoint)

    @property
    def healthy_count(self) -> int:
        """Return the number of healthy endpoints."""
        return sum(
            1 for ep in self._endpoints
            if self._is_endpoint_available(ep) and self._endpoint_failures[ep] == 0
        )

    @property
    def current_endpoint(self) -> str:
        """Return the currently active RPC endpoint."""
        return self._endpoints[self._current_index] if self._endpoints else "none"

    @property
    def avg_latency_ms(self) -> float:
        """Return average latency over last 100 measurements."""
        if not self._latency_history:
            return 0.0
        recent = self._latency_history[-100:]
        return sum(recent) / len(recent)

    @property
    def estimated_cu_used(self) -> float:
        """Return total estimated compute units used since start."""
        return self._cu_estimate_total

    @property
    def rotation_count(self) -> int:
        """Return total number of RPC rotations."""
        return self._rotation_count
