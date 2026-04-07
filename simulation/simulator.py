import copy
import logging
from typing import Dict, Any, Optional

from simulation.amm_math import calc_v2_amount_out, calc_v3_amount_out, calc_balancer_amount_out, calc_curve_amount_out
from simulation.slippage_model import estimate_slippage, estimate_v3_slippage, apply_slippage_to_amount
from simulation.gas_estimator import estimate_gas, estimate_gas_cost_usd
from config import MIN_PROFIT_USD, GAS_SAFETY_BUFFER, MAX_BORROW_PCT

logger = logging.getLogger(__name__)


class Simulator:
    """Full atomic simulation of a flash-loan arbitrage route."""

    def __init__(self, eth_price_usd: float = 0.0):
        self._eth_price_usd = eth_price_usd

    async def simulate_flashloan_arb(
        self,
        candidate: Dict[str, Any],
        reserves: Dict[str, Dict[str, Any]],
        block_number: int,
        gas_price_gwei: float = 0.1,
    ) -> Optional[Dict[str, Any]]:
        """Simulate the entire flash-loan arbitrage route."""
        steps = candidate.get("steps", [])
        if not steps:
            return None

        fl_source = candidate.get("fl_source")
        if not fl_source:
            return None

        fl_fee_rate = fl_source.get("fee_rate", 0.0)
        token_in = candidate.get("token_in", steps[0].get("token_in", ""))

        borrow_amount = candidate.get("borrow_amount", 0)
        if borrow_amount <= 0:
            return None

        fl_fee = int(borrow_amount * fl_fee_rate)
        repay_amount = borrow_amount + fl_fee

        current_amount = borrow_amount
        total_slippage = 0.0
        all_swap_fees = 0

        for i, step in enumerate(steps):
            pool_addr = step.get("pool", "")
            dex = step.get("dex", "")
            pool_reserves = reserves.get(pool_addr, {})

            if not pool_reserves:
                return None

            if "sqrtPriceX96" in pool_reserves:
                liquidity = pool_reserves.get("liquidity", 0)
                step_slippage = estimate_v3_slippage(current_amount, liquidity, step.get("fee", 0.003))
            else:
                step_slippage = estimate_slippage(
                    amount_in=current_amount,
                    reserve_in=pool_reserves.get("reserve0", pool_reserves.get("liquidity", 0)),
                    reserve_out=pool_reserves.get("reserve1", 0),
                    fee=0.003,
                )

            amount_out = self._calc_step_amount_out(
                dex=dex,
                amount_in=current_amount,
                reserves=pool_reserves,
                step=step,
            )

            if amount_out <= 0:
                return None

            slippage_adjusted = apply_slippage_to_amount(amount_out, step_slippage)
            current_amount = slippage_adjusted
            total_slippage += step_slippage
            all_swap_fees += int(current_amount * 0.003)

        gross_profit = current_amount - repay_amount

        gas_units = estimate_gas(candidate, fl_source.get("name", "balancer"))
        gas_cost_eth = gas_units * (gas_price_gwei / 1e9)
        gas_cost_usd = gas_cost_eth * self._eth_price_usd

        gross_profit_usd = (gross_profit / 1e18) * self._eth_price_usd
        swap_fees_usd = (all_swap_fees / 1e18) * self._eth_price_usd
        fl_fee_usd = (fl_fee / 1e18) * self._eth_price_usd

        net_profit_usd = gross_profit_usd - swap_fees_usd - gas_cost_usd - fl_fee_usd

        return {
            "viable": net_profit_usd >= MIN_PROFIT_USD,
            "net_profit_usd": net_profit_usd,
            "gross_profit_usd": gross_profit_usd,
            "swap_fees_usd": swap_fees_usd,
            "gas_used": gas_units,
            "gas_cost_usd": gas_cost_usd,
            "fl_fee_usd": fl_fee_usd,
            "slippage_applied": total_slippage / max(len(steps), 1),
            "borrow_amount": borrow_amount / 1e18,
            "repay_amount": repay_amount / 1e18,
            "block_number": block_number,
            "route": candidate,
        }

    async def stress_test(
        self,
        candidate: Dict[str, Any],
        reserves: Dict[str, Dict[str, Any]],
        block_number: int,
        gas_price_gwei: float = 0.1,
    ) -> bool:
        """Stress test: re-simulate under three adverse conditions.

        BUG 9 FIX: All three tests must pass.
        Test A: Re-simulate at -5% reserves.
        Test B: Re-simulate with gas price 3x current.
        Test C: Re-simulate with reserve change (swap one reserve by +2%).
        """
        test_a = await self._stress_test_reserves_minus_5(candidate, reserves, block_number)
        if not test_a:
            return False

        test_b = await self._stress_test_gas_3x(candidate, reserves, block_number, gas_price_gwei)
        if not test_b:
            return False

        test_c = await self._stress_test_reserve_plus_2(candidate, reserves, block_number)
        if not test_c:
            return False

        return True

    async def _stress_test_reserves_minus_5(
        self,
        candidate: Dict[str, Any],
        reserves: Dict[str, Dict[str, Any]],
        block_number: int,
    ) -> bool:
        """Test A: Re-simulate at -5% reserves."""
        stressed_reserves = {}
        for addr, res in reserves.items():
            stressed_reserves[addr] = {
                k: int(v * 0.95) if isinstance(v, (int, float)) else v
                for k, v in res.items()
            }

        result = await self.simulate_flashloan_arb(candidate, stressed_reserves, block_number)
        return result is not None and result.get("viable", False)

    async def _stress_test_gas_3x(
        self,
        candidate: Dict[str, Any],
        reserves: Dict[str, Dict[str, Any]],
        block_number: int,
        gas_price_gwei: float,
    ) -> bool:
        """Test B: Re-simulate with gas price 3x current."""
        result = await self.simulate_flashloan_arb(
            candidate, reserves, block_number, gas_price_gwei=gas_price_gwei * 3
        )
        return result is not None and result.get("viable", False)

    async def _stress_test_reserve_plus_2(
        self,
        candidate: Dict[str, Any],
        reserves: Dict[str, Dict[str, Any]],
        block_number: int,
    ) -> bool:
        """Test C: Re-simulate with reserve change (swap one reserve by +2%)."""
        stressed_reserves = copy.deepcopy(reserves)

        steps = candidate.get("steps", [])
        if steps:
            first_pool = steps[0].get("pool", "")
            if first_pool in stressed_reserves:
                r = stressed_reserves[first_pool]
                if "reserve0" in r and r["reserve0"] > 0:
                    r["reserve0"] = int(r["reserve0"] * 1.02)
                elif "sqrtPriceX96" in r and r["sqrtPriceX96"] > 0:
                    r["sqrtPriceX96"] = int(r["sqrtPriceX96"] * 1.01)

        result = await self.simulate_flashloan_arb(candidate, stressed_reserves, block_number)
        return result is not None and result.get("viable", False)

    @staticmethod
    def _calc_step_amount_out(
        dex: str,
        amount_in: int,
        reserves: Dict[str, Any],
        step: Dict[str, Any],
    ) -> int:
        """Calculate output amount for a single swap step."""
        reserve_in = reserves.get("reserve0", reserves.get("liquidity", 0))
        reserve_out = reserves.get("reserve1", 0)
        fee = 0.003

        if dex in ("uniswap_v3", "sushiswap_v3", "pancakeswap_v3"):
            sqrt_price = reserves.get("sqrtPriceX96", 0)
            liquidity = reserves.get("liquidity", 0)
            zero_for_one = reserves.get("zero_for_one", True)
            return calc_v3_amount_out(amount_in, sqrt_price, liquidity, fee, zero_for_one)
        elif dex == "balancer_v2":
            balances = reserves.get("balances", [reserve_in, reserve_out])
            weights = reserves.get("weights", [int(0.5e18), int(0.5e18)])
            return calc_balancer_amount_out(
                amount_in, balances[0], balances[1], weights[0], weights[1], fee
            )
        elif dex == "curve":
            balances = reserves.get("balances", [reserve_in, reserve_out])
            amp = reserves.get("amp", 100)
            return calc_curve_amount_out(amount_in, balances[0], balances[1], fee, amp)
        else:
            return calc_v2_amount_out(amount_in, reserve_in, reserve_out, fee)
