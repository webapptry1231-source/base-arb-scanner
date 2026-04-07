import logging
from typing import Dict, Any, Optional

import aiohttp

logger = logging.getLogger(__name__)


class TenderlySimulator:
    """Fallback simulator using Tenderly API when Anvil is unavailable."""

    def __init__(self, api_key: str = "", account: str = "", project: str = ""):
        self._api_key = api_key
        self._account = account
        self._project = project
        self._base_url = f"https://api.tenderly.co/api/v1/account/{account}/project/{project}"
        self._headers = {
            "Content-Type": "application/json",
            "X-Access-Key": api_key,
        }

    async def simulate_transaction(
        self,
        tx_params: Dict[str, Any],
        network_id: str = "8453",
        block_number: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Simulate a transaction via Tenderly API."""
        if not self._api_key:
            logger.warning("Tenderly API key not configured, skipping simulation")
            return {"success": False, "error": "No Tenderly API key"}

        payload = {
            "network_id": network_id,
            "from": tx_params.get("from", "0x0000000000000000000000000000000000000001"),
            "to": tx_params.get("to"),
            "input": tx_params.get("data", "0x"),
            "gas": tx_params.get("gas", 500000),
            "save": False,
        }

        if block_number:
            payload["block_number"] = block_number

        url = f"{self._base_url}/simulate"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers=self._headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "success": True,
                            "gas_used": data.get("transaction", {}).get("gas_used", 0),
                            "status": data.get("transaction", {}).get("status", False),
                        }
                    else:
                        error_text = await response.text()
                        return {"success": False, "error": error_text}
        except Exception as e:
            logger.error(f"Tenderly simulation error: {e}")
            return {"success": False, "error": str(e)}
