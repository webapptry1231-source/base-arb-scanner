import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class AnvilForkSimulator:
    """Simulates transactions on a local Anvil fork of Base mainnet."""

    def __init__(self, rpc_url: str, port: int = 8545):
        self._rpc_url = rpc_url
        self._port = port
        self._anvil_process = None
        self._fork_w3 = None

    async def start_fork(self, block_number: Optional[int] = None):
        """Start an Anvil fork at the given block number."""
        import subprocess

        cmd = [
            "anvil",
            "--fork-url", self._rpc_url,
            "--port", str(self._port),
        ]
        if block_number:
            cmd.extend(["--fork-block-number", str(block_number)])

        try:
            self._anvil_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            logger.info(f"Anvil fork started on port {self._port}")
        except FileNotFoundError:
            logger.error("Anvil not found. Install Foundry: curl -L https://foundry.paradigm.xyz | bash")
            raise

    async def stop_fork(self):
        """Stop the Anvil fork process."""
        if self._anvil_process:
            self._anvil_process.terminate()
            self._anvil_process.wait()
            logger.info("Anvil fork stopped")

    async def simulate_transaction(self, tx_params: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate a transaction on the fork and return result."""
        if not self._fork_w3:
            from web3 import AsyncWeb3
            self._fork_w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(f"http://127.0.0.1:{self._port}"))

        try:
            result = await self._fork_w3.eth.call(tx_params)
            return {"success": True, "output": result.hex()}
        except Exception as e:
            return {"success": False, "error": str(e)}
