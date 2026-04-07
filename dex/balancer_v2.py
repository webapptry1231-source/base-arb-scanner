import logging
from typing import List, Dict, Any, Optional

from web3 import AsyncWeb3

from dex.base_adapter import DEXAdapter
from config import BALANCER_VAULT

logger = logging.getLogger(__name__)

BALANCER_VAULT_ABI = [
    {
        "inputs": [{"internalType": "bytes32", "name": "poolId", "type": "bytes32"}],
        "name": "getPoolTokens",
        "outputs": [
            {"internalType": "contract IERC20[]", "name": "tokens", "type": "address[]"},
            {"internalType": "uint256[]", "name": "balances", "type": "uint256[]"},
            {"internalType": "uint256", "name": "lastChangeBlock", "type": "uint256"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "poolId", "type": "bytes32"}],
        "name": "getPool",
        "outputs": [
            {"internalType": "address", "name": "", "type": "address"},
            {"internalType": "uint256", "name": "", "type": "uint256"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "getPoolIds",
        "outputs": [{"internalType": "bytes32[]", "name": "", "type": "bytes32[]"}],
        "stateMutability": "view",
        "type": "function",
    },
]

BALANCER_POOL_ABI = [
    {
        "inputs": [],
        "name": "getPoolId",
        "outputs": [{"internalType": "bytes32", "name": "", "type": "bytes32"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "getNormalizedWeights",
        "outputs": [{"internalType": "uint256[]", "name": "", "type": "uint256[]"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "getSwapFeePercentage",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]


class BalancerV2Adapter(DEXAdapter):
    """Balancer V2 weighted pool adapter on Base."""

    def __init__(self, w3: AsyncWeb3, vault_address: str = BALANCER_VAULT, multicall=None):
        super().__init__(w3, multicall)
        self._vault_address = vault_address
        self._vault = w3.eth.contract(address=vault_address, abi=BALANCER_VAULT_ABI)
        self._pool_data: Dict[str, Dict] = {}

    async def get_amount_out(
        self,
        token_in: str,
        token_out: str,
        amount_in: int,
        pool_address: str,
    ) -> int:
        """Calculate output amount using Balancer V2 weighted pool math."""
        pool_info = self._pool_data.get(pool_address.lower())
        if not pool_info:
            return 0

        balances = pool_info["balances"]
        weights = pool_info["weights"]
        tokens = pool_info["tokens"]
        fee = pool_info["fee"]

        token_in_idx = None
        token_out_idx = None
        for i, t in enumerate(tokens):
            if t.lower() == token_in.lower():
                token_in_idx = i
            if t.lower() == token_out.lower():
                token_out_idx = i

        if token_in_idx is None or token_out_idx is None:
            return 0

        balance_in = balances[token_in_idx]
        balance_out = balances[token_out_idx]
        weight_in = weights[token_in_idx]
        weight_out = weights[token_out_idx]

        amount_out = self._calc_balancer_out_given_in(
            amount_in=amount_in,
            balance_in=balance_in,
            balance_out=balance_out,
            weight_in=weight_in,
            weight_out=weight_out,
            fee=fee,
        )
        return amount_out

    @staticmethod
    def _calc_balancer_out_given_in(
        amount_in: int,
        balance_in: int,
        balance_out: int,
        weight_in: int,
        weight_out: int,
        fee: float,
    ) -> int:
        """Balancer V2 weighted pool swap formula.

        amount_out = balance_out * (1 - (balance_in / (balance_in + amount_in * (1 - fee)))^(weight_in / weight_out))
        """
        if balance_in <= 0 or balance_out <= 0 or weight_in <= 0 or weight_out <= 0:
            return 0

        amount_in_with_fee = amount_in * (1 - fee)

        denominator = balance_in + amount_in_with_fee
        if denominator <= 0:
            return 0

        ratio = balance_in / denominator
        exponent = weight_in / weight_out

        try:
            factor = ratio ** exponent
            amount_out = int(balance_out * (1 - factor))
        except (OverflowError, ZeroDivisionError):
            return 0

        return max(amount_out, 0)

    async def get_all_pools(self) -> List[Dict[str, Any]]:
        """Discover all Balancer V2 pools via vault getPoolIds."""
        pools = []
        try:
            pool_ids = await self._vault.functions.getPoolIds().call()
            logger.info(f"[balancer_v2] Found {len(pool_ids)} pool IDs from vault")
        except Exception as e:
            logger.error(f"[balancer_v2] Failed to get pool IDs: {e}")
            return []

        for pool_id in pool_ids:
            try:
                pool_info = await self._vault.functions.getPool(pool_id).call()
                pool_address = pool_info[0]

                pool_contract = self._w3.eth.contract(
                    address=pool_address, abi=BALANCER_POOL_ABI
                )

                tokens_result = await self._vault.functions.getPoolTokens(pool_id).call()
                tokens = tokens_result[0]
                balances = tokens_result[1]

                try:
                    weights = await pool_contract.functions.getNormalizedWeights().call()
                except Exception:
                    n_tokens = len(tokens)
                    weights = [int(1e18) // n_tokens for _ in range(n_tokens)]

                try:
                    fee_raw = await pool_contract.functions.getSwapFeePercentage().call()
                    fee = fee_raw / 1e18
                except Exception:
                    fee = 0.002

                pool_data = {
                    "address": pool_address,
                    "pool_id": pool_id.hex() if isinstance(pool_id, bytes) else pool_id,
                    "tokens": tokens,
                    "balances": [int(b) for b in balances],
                    "weights": [int(w) for w in weights],
                    "fee": fee,
                    "dex": "balancer_v2",
                    "type": "weighted",
                }
                self._pool_data[pool_address.lower()] = pool_data
                pools.append(pool_data)

            except Exception as e:
                logger.debug(f"[balancer_v2] Failed to fetch pool {pool_id}: {e}")
                continue

        self._pools = pools
        return pools

    def get_fee(self, pool_address: str) -> float:
        """Return the swap fee for a Balancer pool."""
        pool_info = self._pool_data.get(pool_address.lower())
        if pool_info:
            return pool_info["fee"]
        return 0.002

    def get_pool_type(self) -> str:
        return "balancer_v2"
