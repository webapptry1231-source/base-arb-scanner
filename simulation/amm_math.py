import math
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

Q96 = 2**96
Q192 = Q96 ** 2


def calc_v2_amount_out(
    amount_in: int,
    reserve_in: int,
    reserve_out: int,
    fee: float,
) -> int:
    """V2 constant product: amount_out = (amount_in * (1-fee) * reserve_out) / (reserve_in + amount_in * (1-fee))"""
    if reserve_in <= 0 or reserve_out <= 0:
        return 0
    amount_in_with_fee = int(amount_in * (1 - fee))
    numerator = amount_in_with_fee * reserve_out
    denominator = reserve_in + amount_in_with_fee
    if denominator == 0:
        return 0
    return numerator // denominator


def calc_v3_amount_out(
    amount_in: int,
    sqrt_price_x96: int,
    liquidity: int,
    fee: float,
    zero_for_one: bool,
) -> int:
    """Simplified V3 single-tick amount out calculation."""
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


def calc_balancer_amount_out(
    amount_in: int,
    balance_in: int,
    balance_out: int,
    weight_in: int,
    weight_out: int,
    fee: float,
) -> int:
    """Balancer V2 weighted pool swap formula."""
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


def calc_curve_amount_out(
    amount_in: int,
    balance_in: int,
    balance_out: int,
    fee: float,
    amp: int = 100,
) -> int:
    """Simplified StableSwap output calculation."""
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
