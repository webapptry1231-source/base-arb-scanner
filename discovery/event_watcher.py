import asyncio
import logging
from typing import Callable, Dict, List, Any, Optional

from web3 import AsyncWeb3

logger = logging.getLogger(__name__)


class EventWatcher:
    """Watches for PairCreated / PoolCreated events via WebSocket subscription."""

    def __init__(self, w3_provider, factories: Dict[str, Dict[str, Any]]):
        """
        Args:
            w3_provider: AsyncWeb3 instance with WebSocket support
            factories: Dict mapping dex_name -> {"address": str, "abi": list, "event_name": str}
        """
        self._w3 = w3_provider
        self._factories = factories
        self._running = False
        self._callbacks: List[Callable] = []
        self._watch_task: Optional[asyncio.Task] = None

    def on_new_pool(self, callback: Callable):
        """Register a callback for new pool events."""
        self._callbacks.append(callback)

    async def start(self):
        """Start watching for new pool creation events."""
        self._running = True
        self._watch_task = asyncio.create_task(self._watch_loop())
        logger.info(f"EventWatcher started for {len(self._factories)} factories")

    async def stop(self):
        """Stop the event watcher."""
        self._running = False
        if self._watch_task:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass
        logger.info("EventWatcher stopped")

    async def _watch_loop(self):
        """Main event watching loop."""
        event_filters = []
        for dex_name, factory_info in self._factories.items():
            try:
                factory_contract = self._w3.eth.contract(
                    address=factory_info["address"],
                    abi=factory_info["abi"],
                )
                event_filter = factory_contract.events[factory_info["event_name"]].create_filter(
                    from_block="latest"
                )
                event_filters.append((dex_name, event_filter))
                logger.info(f"Created event filter for {dex_name}")
            except Exception as e:
                logger.error(f"Failed to create event filter for {dex_name}: {e}")

        while self._running:
            for dex_name, event_filter in event_filters:
                try:
                    events = event_filter.get_new_entries()
                    for event in events:
                        pool_data = {
                            "dex": dex_name,
                            "pool_address": event["args"].get("pool") or event["args"].get("pair"),
                            "token0": event["args"].get("token0"),
                            "token1": event["args"].get("token1"),
                            "block_number": event["blockNumber"],
                            "tx_hash": event["transactionHash"].hex(),
                        }
                        logger.info(f"New pool detected on {dex_name}: {pool_data['pool_address']}")
                        await self._notify_callbacks(pool_data)
                except Exception as e:
                    logger.debug(f"Error polling events for {dex_name}: {e}")

            await asyncio.sleep(2)

    async def _notify_callbacks(self, pool_data: Dict[str, Any]):
        """Notify all registered callbacks of a new pool."""
        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(pool_data)
                else:
                    callback(pool_data)
            except Exception as e:
                logger.error(f"Event callback error: {e}")
