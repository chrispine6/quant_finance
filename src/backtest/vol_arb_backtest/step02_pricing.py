"""Black-76 price, delta, and implied volatility on a sqrt(252) year."""

import math
from datetime import date, timedelta

import numpy as np

from backtest.vol_arb_backtest.step01_config import RATE


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def black76(future: float, strike: float, time: float, rate: float, sigma: float, right: str) -> float:
    discount = math.exp(-rate * time)
    if time <= 0 or sigma <= 0:
        intrinsic = max(future - strike, 0.0) if right == "CE" else max(strike - future, 0.0)
        return discount * intrinsic
    width = sigma * math.sqrt(time)
    d1 = (math.log(future / strike) + 0.5 * sigma * sigma * time) / width
    d2 = d1 - width
    if right == "CE":
        return discount * (future * norm_cdf(d1) - strike * norm_cdf(d2))
    return discount * (strike * norm_cdf(-d2) - future * norm_cdf(-d1))


def black76_delta(future: float, strike: float, time: float, rate: float, sigma: float, right: str) -> float:
    """Change in the option price for a one-point change in the futures price."""
    discount = math.exp(-rate * time)
    if time <= 0 or sigma <= 0:
        if right == "CE":
            return discount if future > strike else 0.0
        return -discount if future < strike else 0.0
    width = sigma * math.sqrt(time)
    d1 = (math.log(future / strike) + 0.5 * sigma * sigma * time) / width
    if right == "CE":
        return discount * norm_cdf(d1)
    return discount * (norm_cdf(d1) - 1.0)


def implied_vol(price: float, future: float, strike: float, time: float, rate: float, right: str) -> float | None:
    if time <= 0 or price <= 0 or future <= 0 or strike <= 0:
        return None
    discount = math.exp(-rate * time)
    intrinsic = discount * (max(future - strike, 0.0) if right == "CE" else max(strike - future, 0.0))
    if price < intrinsic - 1e-6:
        return None
    low, high = 1e-4, 5.0
    if black76(future, strike, time, rate, high, right) < price:
        return None
    for _ in range(60):
        mid = 0.5 * (low + high)
        if black76(future, strike, time, rate, mid, right) > price:
            high = mid
        else:
            low = mid
    return 0.5 * (low + high)


def round_lots(value: float) -> int:
    if value == 0:
        return 0
    return int(math.copysign(math.floor(abs(value) + 0.5), value))


def year_fraction(day: date, expiry: date) -> float:
    # Close of `day` has already happened, so count sessions from tomorrow through expiry.
    sessions = int(np.busday_count(day + timedelta(days=1), expiry + timedelta(days=1)))
    return max(sessions, 0) / 252


def leg_vol(price: float, future: float, strike: float, time: float, right: str) -> float | None:
    sigma = implied_vol(price, future, strike, time, RATE, right)
    if sigma is None:
        return None
    percent = sigma * 100
    if not 1.0 <= percent <= 150.0:
        return None
    return sigma
