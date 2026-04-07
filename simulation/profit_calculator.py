import logging
from typing import Dict, Any

from simulation.gas_estimator import estimate_gas, estimate_gas_cost_usd
from config import MIN_PROFIT_USD, GAS_SAFETY_BUFFER

logger = logging.getLogger(__name__)


class ProfitCalculator:
    """Calculates net profit for arbitrage opportunities."""

    def __init__(self, eth_price_usd: float = 0.0):
        self._eth_price_usd = eth_price_usd

    def calculate_net_profit(
        self,
        simulation: Dict[str, Any],
        fl_source: Dict[str, Any],
        block_number: int,
        gas_price_gwei: float = 0.1,
    ) -> Dict[str, Any]:
        """Calculate net profit from simulation results.

        net_profit = gross_output - flash_loan_repayment - swap_fees - gas_cost
        """
        gross_profit_wei = simulation.get("gross_profit_wei", 0)
        fl_fee_rate = fl_source.get("fee_rate", 0.0)
        borrow_amount = simulation.get("borrow_amount", 0)

        fl_fee = int(borrow_amount * fl_fee_rate)
        repay_amount = borrow_amount + fl_fee

        gas_units = estimate_gas(simulation.get("route", {}), fl_source.get("name", "balancer"))
        gas_cost_eth = gas_units * (gas_price_gwei / 1e9)
        gas_cost_usd = gas_cost_eth * self._eth_price_usd

        gross_profit_usd = (gross_profit_wei / 1e18) * self._eth_price_usd
        fl_fee_usd = (fl_fee / 1e18) * self._eth_price_usd
        swap_fees_usd = simulation.get("swap_fees_usd", 0)

        net_profit_usd = gross_profit_usd - fl_fee_usd - gas_cost_usd - swap_fees_usd

        return {
            "viable": net_profit_usd >= MIN_PROFIT_USD,
            "net_profit_usd": net_profit_usd,
            "gross_profit_usd": gross_profit_usd,
            "fl_fee_usd": fl_fee_usd,
            "gas_used": gas_units,
            "gas_cost_usd": gas_cost_usd,
            "swap_fees_usd": swap_fees_usd,
            "block_number": block_number,
        }
