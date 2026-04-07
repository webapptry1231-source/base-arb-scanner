import logging
from typing import Dict, Any, Optional

from web3 import AsyncWeb3

from config import AAVE_V3_POOL

logger = logging.getLogger(__name__)

ERC20_BALANCE_ABI = [
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

AAVE_V3_POOL_ABI = [
    {
        "inputs": [{"internalType": "address", "name": "asset", "type": "address"}],
        "name": "getReserveData",
        "outputs": [
            {
                "components": [
                    {"internalType": "uint256", "name": "configuration", "type": "uint256"},
                    {"internalType": "uint128", "name": "liquidityIndex", "type": "uint128"},
                    {"internalType": "uint128", "name": "currentLiquidityRate", "type": "uint128"},
                    {"internalType": "uint128", "name": "variableBorrowIndex", "type": "uint128"},
                    {"internalType": "uint128", "name": "currentVariableBorrowRate", "type": "uint128"},
                    {"internalType": "uint128", "name": "currentStableBorrowRate", "type": "uint128"},
                    {"internalType": "uint40", "name": "lastUpdateTimestamp", "type": "uint40"},
                    {"internalType": "uint16", "name": "id", "type": "uint16"},
                    {"internalType": "address", "name": "aTokenAddress", "type": "address"},
                    {"internalType": "address", "name": "stableDebtTokenAddress", "type": "address"},
                    {"internalType": "address", "name": "variableDebtTokenAddress", "type": "address"},
                    {"internalType": "address", "name": "interestRateStrategyAddress", "type": "address"},
                    {"internalType": "uint128", "name": "accruedToTreasury", "type": "uint128"},
                    {"internalType": "uint128", "name": "unbacked", "type": "uint128"},
                    {"internalType": "uint128", "name": "isolationModeTotalDebt", "type": "uint128"},
                ],
                "internalType": "struct DataTypes.ReserveData",
                "name": "",
                "type": "tuple",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    },
]


class AaveV3FlashLoan:
    """Aave V3 flash-loan source (0.05% fee)."""

    def __init__(self, w3: AsyncWeb3, pool_address: str = AAVE_V3_POOL):
        self._w3 = w3
        self._pool_address = pool_address
        self._pool = w3.eth.contract(address=pool_address, abi=AAVE_V3_POOL_ABI)
        self._name = "aave_v3"
        self._fee_rate = 0.0005

    async def check_availability(self, token: str, amount: int) -> bool:
        """Check if Aave V3 has sufficient liquidity for a flash loan.

        BUG 8 FIX: Use getReserveData to get aTokenAddress (index 7),
        then ERC20 balanceOf on the aToken to get available liquidity.
        Also fixed ABI: interestRateStrategyAddress is "address" not "uint8".
        """
        try:
            reserve_data = await self._pool.functions.getReserveData(token).call()
            atoken_addr = reserve_data[8]
            erc20 = self._w3.eth.contract(address=token, abi=ERC20_BALANCE_ABI)
            available = await erc20.functions.balanceOf(atoken_addr).call()
            return int(available) >= amount
        except Exception as e:
            logger.debug(f"[aave_v3] Failed to check liquidity for {token}: {e}")
            return False

    async def get_available_liquidity(self, token: str) -> int:
        """Get available liquidity for a token."""
        try:
            reserve_data = await self._pool.functions.getReserveData(token).call()
            atoken_addr = reserve_data[8]
            erc20 = self._w3.eth.contract(address=token, abi=ERC20_BALANCE_ABI)
            available = await erc20.functions.balanceOf(atoken_addr).call()
            return int(available)
        except Exception as e:
            logger.debug(f"[aave_v3] Failed to get liquidity for {token}: {e}")
            return 0

    def build_flashloan_calldata(
        self,
        tokens: list,
        amounts: list,
        modes: list,
        on_behalf_of: str,
        referral_code: int = 0,
    ) -> bytes:
        """Build calldata for Aave V3 flash loan (flashLoanSimple)."""
        return self._pool.encode_abi(
            fn_name="flashLoanSimple",
            args=[tokens[0], amounts[0], modes[0] if modes else b"", referral_code],
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def fee_rate(self) -> float:
        return self._fee_rate

    @property
    def address(self) -> str:
        return self._pool_address
