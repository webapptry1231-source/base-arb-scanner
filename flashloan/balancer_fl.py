import logging
from typing import Dict, Any, Optional

from web3 import AsyncWeb3

from config import BALANCER_VAULT

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


class BalancerFlashLoan:
    """Balancer V2 flash-loan source (0% fee)."""

    def __init__(self, w3: AsyncWeb3, vault_address: str = BALANCER_VAULT):
        self._w3 = w3
        self._vault_address = vault_address
        self._name = "balancer"
        self._fee_rate = 0.0

    async def check_availability(self, token: str, amount: int) -> bool:
        """Check if the vault has sufficient liquidity for a flash loan.

        BUG 7 FIX: Use ERC20 balanceOf on the vault address instead of
        the non-existent getInternalBalance(address) single-arg variant.
        """
        try:
            erc20 = self._w3.eth.contract(address=token, abi=ERC20_BALANCE_ABI)
            balance = await erc20.functions.balanceOf(BALANCER_VAULT).call()
            return int(balance) >= amount
        except Exception as e:
            logger.debug(f"[balancer] Failed to check liquidity for {token}: {e}")
            return True

    async def get_available_liquidity(self, token: str) -> int:
        """Get available liquidity for a token."""
        try:
            erc20 = self._w3.eth.contract(address=token, abi=ERC20_BALANCE_ABI)
            balance = await erc20.functions.balanceOf(BALANCER_VAULT).call()
            return int(balance)
        except Exception as e:
            logger.debug(f"[balancer] Failed to get liquidity for {token}: {e}")
            return 0

    def build_flashloan_calldata(
        self,
        tokens: list,
        amounts: list,
        recipient: str,
        user_data: bytes = b"",
    ) -> bytes:
        """Build calldata for Balancer V2 flash loan."""
        vault_contract = self._w3.eth.contract(
            address=self._vault_address,
            abi=[{
                "inputs": [
                    {"internalType": "address", "name": "recipient", "type": "address"},
                    {"internalType": "address[]", "name": "tokens", "type": "address[]"},
                    {"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"},
                    {"internalType": "bytes", "name": "userData", "type": "bytes"},
                ],
                "name": "flashLoan",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function",
            }],
        )
        return vault_contract.encode_abi(
            fn_name="flashLoan",
            args=[recipient, tokens, amounts, user_data],
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def fee_rate(self) -> float:
        return self._fee_rate

    @property
    def address(self) -> str:
        return self._vault_address
