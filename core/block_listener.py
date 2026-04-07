import asyncio
import logging
from typing import Callable, Optional, Dict, Any
from web3 import AsyncWeb3

from config import CONFIG

logger = logging.getLogger(__name__)


class BlockListener:
    """Listens for new blocks on Base chain via WebSocket or HTTP polling fallback."""

    def __init__(self, rpc_manager):
        self._rpc_manager = rpc_manager
        self._running = False
        self._current_block: Optional[int] = None
        self._callbacks: list = []
        self._listener_task: Optional[asyncio.Task] = None
        self._poll_interval: float = 2.0  # Base chain ~2s blocks

    def on_new_block(self, callback: Callable):
        """Register a callback for new block events."""
        self._callbacks.append(callback)

    async def start(self):
        """Start listening for new blocks."""
        self._running = True
        self._listener_task = asyncio.create_task(self._listen_loop())
        logger.info("BlockListener started")

    async def stop(self):
        """Stop the block listener."""
        self._running = False
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        logger.info("BlockListener stopped")

    async def _listen_loop(self):
        """Main listener loop: try WebSocket first, fall back to HTTP polling."""
        try:
            await self._listen_websocket()
        except Exception as e:
            logger.warning(f"WebSocket listener failed ({e}), falling back to HTTP polling")
            await self._listen_http_polling()

    async def _listen_websocket(self):
        """Listen for new blocks via WebSocket subscription."""
        ws_w3 = await self._rpc_manager.get_ws_w3()

        try:
            async for block_header in ws_w3.eth.subscribe("newHeads"):
                if not self._running:
                    break

                block_number = block_header.get("number")
                if block_number is None:
                    continue

                block_number = int(block_number, 16) if isinstance(block_number, str) else block_number

                if self._current_block is None or block_number > self._current_block:
                    self._current_block = block_number
                    logger.debug(f"New block detected via WS: #{block_number}")
                    await self._notify_callbacks(block_header)
        except Exception as e:
            logger.error(f"WebSocket subscription error: {e}")
            raise

    async def _listen_http_polling(self):
        """Poll for new blocks via HTTP (fallback)."""
        logger.info("Starting HTTP polling for new blocks")

        while self._running:
            try:
                w3 = await self._rpc_manager.get_w3()
                block_number = await w3.eth.block_number

                if self._current_block is None or block_number > self._current_block:
                    self._current_block = block_number
                    logger.debug(f"New block detected via HTTP poll: #{block_number}")

                    block = await w3.eth.get_block(block_number)
                    block_header = {
                        "number": block_number,
                        "hash": block["hash"].hex() if isinstance(block["hash"], bytes) else block["hash"],
                        "timestamp": block["timestamp"],
                    }
                    await self._notify_callbacks(block_header)

            except Exception as e:
                logger.error(f"HTTP polling error: {e}")

            await asyncio.sleep(self._poll_interval)

    async def _notify_callbacks(self, block_header: Dict[str, Any]):
        """Notify all registered callbacks of a new block."""
        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(block_header)
                else:
                    callback(block_header)
            except Exception as e:
                logger.error(f"Block callback error: {e}")

    @property
    def current_block(self) -> Optional[int]:
        """Return the current block number."""
        return self._current_block
