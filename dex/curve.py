import logging
from typing import List, Dict, Any, Optional

from web3 import AsyncWeb3

from dex.base_adapter import DEXAdapter

logger = logging.getLogger(__name__)

CURVE_POOL_REGISTRY_ABI = [
    {
        "inputs": [{"internalType": "uint256", "name": "arg0", "type": "uint256"}],
        "name": "pool_list",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "pool_count",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

CURVE_POOL_ABI = [
    {
        "inputs": [],
        "name": "A",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "get_balances",
        "outputs": [{"internalType": "uint256[8]", "name": "", "type": "uint256[8]"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "coins",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "fee",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "get_underlying_coins",
        "outputs": [{"internalType": "address[8]", "name": "", "type": "address[8]"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "int128", "name": "i", "type": "int128"}],
        "name": "coins",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "int128", "name": "i", "type": "int128"}],
        "name": "balances",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]


class CurveAdapter(DEXAdapter):
    """Curve Finance StableSwap adapter on Base."""

    def __init__(self, w3: AsyncWeb3, registry_addresses: List[str] = None, multicall=None):
        super().__init__(w3, multicall)
        self._registry_addresses = registry_addresses or []
        self._pool_data: Dict[str, Dict] = {}

    async def get_amount_out(
        self,
        token_in: str,
        token_out: str,
        amount_in: int,
        pool_address: str,
    ) -> int:
        """Calculate output amount using Curve StableSwap invariant."""
        pool_info = self._pool_data.get(pool_address.lower())
        if not pool_info:
            return 0

        balances = pool_info["balances"]
        tokens = pool_info["tokens"]
        fee = pool_info["fee"]
        amp = pool_info.get("amp", 100)

        token_in_idx = None
        token_out_idx = None
        for i, t in enumerate(tokens):
            if t.lower() == token_in.lower():
                token_in_idx = i
            if t.lower() == token_out.lower():
                token_out_idx = i

        if token_in_idx is None or token_out_idx is None:
            return 0

        amount_out = self._calc_stable_swap_out(
            amount_in=amount_in,
            balance_in=balances[token_in_idx],
            balance_out=balances[token_out_idx],
            fee=fee,
            amp=amp,
        )
        return amount_out

    @staticmethod
    def _calc_stable_swap_out(
        amount_in: int,
        balance_in: int,
        balance_out: int,
        fee: float,
        amp: int = 100,
    ) -> int:
        """Simplified StableSwap output calculation.

        For a 2-pool: y' = (x + y + D/A) - amount_in*(1-fee)
        Simplified: use the invariant to compute new y after adding x.
        """
        if balance_in <= 0 or balance_out <= 0:
            return 0

        amount_in_after_fee = int(amount_in * (1 - fee))

        D = balance_in + balance_out
        if D <= 0:
            return 0

        new_balance_in = balance_in + amount_in_after_fee

        try:
            y = (balance_in * balance_out) // new_balance_in
            amount_out = balance_out - y
        except ZeroDivisionError:
            return 0

        return max(int(amount_out), 0)

    async def get_all_pools(self) -> List[Dict[str, Any]]:
        """Discover all Curve pools on Base via registries."""
        pools = []

        for registry_addr in self._registry_addresses:
            try:
                registry = self._w3.eth.contract(
                    address=registry_addr, abi=CURVE_POOL_REGISTRY_ABI
                )
                pool_count = await registry.functions.pool_count().call()
                pool_count = int(pool_count)

                for i in range(pool_count):
                    try:
                        pool_address = await registry.functions.pool_list(i).call()
                        pool_data = await self._fetch_pool_data(pool_address)
                        if pool_data:
                            pools.append(pool_data)
                    except Exception as e:
                        logger.debug(f"[curve] Failed to fetch pool {i} from {registry_addr}: {e}")
                        continue

            except Exception as e:
                logger.warning(f"[curve] Failed to query registry {registry_addr}: {e}")
                continue

        self._pools = pools
        logger.info(f"[curve] Discovered {len(pools)} pools")
        return pools

    async def _fetch_pool_data(self, pool_address: str) -> Optional[Dict[str, Any]]:
        """Fetch detailed data for a single Curve pool."""
        try:
            pool = self._w3.eth.contract(address=pool_address, abi=CURVE_POOL_ABI)

            tokens = []
            for i in range(8):
                try:
                    token = await pool.functions.coins(i).call()
                    if token and token != "0x0000000000000000000000000000000000000000":
                        tokens.append(token)
                except Exception:
                    break

            if not tokens:
                return None

            balances = []
            for i in range(len(tokens)):
                try:
                    bal = await pool.functions.balances(i).call()
                    balances.append(int(bal))
                except Exception:
                    balances.append(0)

            try:
                fee_raw = await pool.functions.fee().call()
                fee = int(fee_raw) / 1e10
            except Exception:
                fee = 0.0004

            try:
                amp = int(await pool.functions.A().call())
            except Exception:
                amp = 100

            pool_data = {
                "address": pool_address,
                "tokens": tokens,
                "balances": balances,
                "fee": fee,
                "amp": amp,
                "dex": "curve",
                "type": "stableswap",
            }
            self._pool_data[pool_address.lower()] = pool_data
            return pool_data

        except Exception as e:
            logger.debug(f"[curve] Failed to fetch pool data for {pool_address}: {e}")
            return None

    def get_fee(self, pool_address: str) -> float:
        """Return the swap fee for a Curve pool."""
        pool_info = self._pool_data.get(pool_address.lower())
        if pool_info:
            return pool_info["fee"]
        return 0.0004

    def get_pool_type(self) -> str:
        return "curve"
