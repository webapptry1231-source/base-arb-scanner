import asyncio
import time
import logging
from typing import Optional, List
from web3 import AsyncWeb3
from web3.providers.async_rpc import AsyncHTTPProvider
from config import CONFIG, HEALTH_CHECK_INTERVAL_SEC

logger = logging.getLogger(__name__)


class RPCManager:
    """Manages multiple RPC endpoints with health checks, rotation, and exponential backoff."""

    def __init__(self):
        self._endpoints: List[str] = [CONFIG["rpc_primary"]] + CONFIG["rpc_fallback"]
        self._ws_endpoint: str = CONFIG["rpc_ws"]
        self._endpoint_failures: dict = {ep: 0 for ep in self._endpoints}
        self._endpoint_backoff_until: dict = {ep: 0.0 for ep in self._endpoints}
        self._current_index: int = 0
        self._w3: Optional[AsyncWeb3] = None
        self._ws_w3: Optional[AsyncWeb3] = None
        self._lock = asyncio.Lock()
        self._health_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        """Start the RPC manager and health check loop."""
        self._running = True
        await self._init_primary_connection()
        self._health_task = asyncio.create_task(self._health_check_loop())
        logger.info(f"RPCManager started with {len(self._endpoints)} endpoints")

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
        for endpoint in self._endpoints:
            if self._is_endpoint_available(endpoint):
                try:
                    self._w3 = AsyncWeb3(AsyncHTTPProvider(endpoint))
                    if await self._test_connection(self._w3):
                        logger.info(f"Connected to primary RPC: {endpoint}")
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

    async def get_w3(self) -> AsyncWeb3:
        """Get a working AsyncWeb3 instance, rotating through endpoints if needed."""
        async with self._lock:
            if self._w3 and await self._test_connection(self._w3):
                return self._w3

            for i in range(len(self._endpoints)):
                idx = (self._current_index + i) % len(self._endpoints)
                endpoint = self._endpoints[idx]

                if not self._is_endpoint_available(endpoint):
                    continue

                try:
                    w3 = AsyncWeb3(AsyncHTTPProvider(endpoint))
                    if await self._test_connection(w3):
                        self._current_index = idx
                        self._w3 = w3
                        self._record_success(endpoint)
                        logger.info(f"Switched to RPC endpoint: {endpoint}")
                        return w3
                except Exception as e:
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

        try:
            from web3.providers.websocket import AsyncWebsocketProvider
            self._ws_w3 = AsyncWeb3(AsyncWebsocketProvider(self._ws_endpoint))
            logger.info(f"Connected to WebSocket RPC: {self._ws_endpoint}")
            return self._ws_w3
        except Exception as e:
            logger.warning(f"WebSocket connection failed: {e}. Falling back to HTTP polling.")
            return await self.get_w3()

    async def _health_check_loop(self):
        """Periodically check health of all endpoints."""
        while self._running:
            try:
                await self._check_all_endpoints()
            except Exception as e:
                logger.error(f"Health check error: {e}")
            await asyncio.sleep(HEALTH_CHECK_INTERVAL_SEC)

    async def _check_all_endpoints(self):
        """Check health of all registered endpoints."""
        for endpoint in self._endpoints:
            try:
                w3 = AsyncWeb3(AsyncHTTPProvider(endpoint))
                block_number = await w3.eth.block_number
                if block_number > 0:
                    self._record_success(endpoint)
                    logger.debug(f"Endpoint healthy: {endpoint} (block {block_number})")
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
