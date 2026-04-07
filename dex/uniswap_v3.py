import math
import logging
from typing import List, Dict, Any, Optional

from web3 import AsyncWeb3

from dex.base_adapter import DEXAdapter
from config import UNISWAP_V3_FACTORY, WETH, USDC, USDT

logger = logging.getLogger(__name__)

Q96 = 2**96
Q192 = Q96 ** 2

UNISWAP_V3_POOL_ABI = [
    {
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
            {"internalType": "int24", "name": "tick", "type": "int24"},
            {"internalType": "uint16", "name": "observationIndex", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"},
            {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"},
            {"internalType": "bool", "name": "unlocked", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "liquidity",
        "outputs": [{"internalType": "uint128", "name": "", "type": "uint128"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "token0",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "token1",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "fee",
        "outputs": [{"internalType": "uint24", "name": "", "type": "uint24"}],
        "stateMutability": "view",
        "type": "function",
    },
]

UNISWAP_V3_FACTORY_ABI = [
    {
        "inputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "name": "allPools",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "poolCount",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]


class UniswapV3Adapter(DEXAdapter):
    """Handles Uniswap V3, Sushi V3, Pancake V3 on Base (sqrtPriceX96 math)."""

    def __init__(self, w3: AsyncWeb3, factory_address: str = UNISWAP_V3_FACTORY, dex_name: str = "uniswap_v3", multicall=None):
        super().__init__(w3, multicall)
        self._factory_address = factory_address
        self._dex_name = dex_name
        self._factory = w3.eth.contract(address=factory_address, abi=UNISWAP_V3_FACTORY_ABI)
        self._pool_contracts: Dict[str, Any] = {}

    async def get_amount_out(
        self,
        token_in: str,
        token_out: str,
        amount_in: int,
        pool_address: str,
    ) -> int:
        """Calculate output amount using V3 sqrtPriceX96 and liquidity math."""
        if pool_address not in self._pool_contracts:
            self._pool_contracts[pool_address] = self._w3.eth.contract(
                address=pool_address, abi=UNISWAP_V3_POOL_ABI
            )

        pool = self._pool_contracts[pool_address]
        slot0 = await pool.functions.slot0().call()
        sqrt_price_x96 = slot0[0]
        liquidity = await pool.functions.liquidity().call()
        pool_fee_raw = await pool.functions.fee().call()
        fee = pool_fee_raw / 1_000_000

        token0 = await pool.functions.token0().call()
        zero_for_one = token_in.lower() == token0.lower()

        amount_out = self._calc_amount_out_v3(
            amount_in=amount_in,
            sqrt_price_x96=sqrt_price_x96,
            liquidity=liquidity,
            fee=fee,
            zero_for_one=zero_for_one,
        )
        return amount_out

    def _calc_amount_out_v3(
        self,
        amount_in: int,
        sqrt_price_x96: int,
        liquidity: int,
        fee: float,
        zero_for_one: bool,
    ) -> int:
        """Simplified V3 single-tick amount out calculation.

        Uses current sqrtPriceX96 and liquidity to compute swap output.
        Full implementation would require tick-by-tick traversal.
        """
        if liquidity == 0 or sqrt_price_x96 == 0:
            return 0

        amount_in_after_fee = int(amount_in * (1 - fee))

        if zero_for_one:
            price = sqrt_price_x96 / Q96
            price_squared = (sqrt_price_x96 ** 2) / Q192

            delta = amount_in_after_fee * price
            amount_out = int((liquidity * delta) / (liquidity * price_squared + delta))
        else:
            price = Q96 / sqrt_price_x96
            price_squared = Q192 / (sqrt_price_x96 ** 2)

            delta = amount_in_after_fee * price
            amount_out = int((liquidity * delta) / (liquidity * price_squared + delta))

        return max(amount_out, 0)

    async def get_all_pools(self) -> List[Dict[str, Any]]:
        """Discover all pools via factory poolCount + allPools iteration."""
        try:
            pool_count = await self._factory.functions.poolCount().call()
            pool_count = int(pool_count)
            logger.info(f"[{self._dex_name}] Found {pool_count} pools from factory")
        except Exception as e:
            logger.error(f"[{self._dex_name}] Failed to get pool count: {e}")
            return []

        pools = []
        for i in range(pool_count):
            try:
                pool_address = await self._factory.functions.allPools(i).call()
                pool_contract = self._w3.eth.contract(
                    address=pool_address, abi=UNISWAP_V3_POOL_ABI
                )

                token0 = await pool_contract.functions.token0().call()
                token1 = await pool_contract.functions.token1().call()
                fee_raw = await pool_contract.functions.fee().call()

                pools.append({
                    "address": pool_address,
                    "token0": token0,
                    "token1": token1,
                    "fee": fee_raw / 1_000_000,
                    "fee_raw": fee_raw,
                    "dex": self._dex_name,
                    "type": "v3",
                })
            except Exception as e:
                logger.debug(f"[{self._dex_name}] Failed to fetch pool {i}: {e}")
                continue

        self._pools = pools
        return pools

    def get_fee(self, pool_address: str) -> float:
        """Return the fee for a pool (cached from discovery)."""
        for pool in self._pools:
            if pool["address"].lower() == pool_address.lower():
                return pool["fee"]
        return 0.003

    def get_pool_type(self) -> str:
        return self._dex_name
