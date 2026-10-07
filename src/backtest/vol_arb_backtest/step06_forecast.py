"""Yearly realized-move forecast from the last 20 and 60 sessions."""

import math

import numpy as np


def cleaned_returns(spots: list[float]) -> np.ndarray:
    # A one-for-one bonus cuts the printed price in half. That is not a move the straddle hedged.
    returns = np.diff(np.log(spots)).astype(float)
    returns[np.abs(returns) > math.log(1.25)] = np.nan
    return returns


def forecast_pct(returns: np.ndarray, index: int) -> float | None:
    if index < 60:
        return None
    window = returns[index - 60 : index]
    recent = window[-20:]
    recent = recent[~np.isnan(recent)]
    longer = window[~np.isnan(window)]
    if len(recent) < 15 or len(longer) < 40:
        return None
    move_20 = float(recent.std(ddof=1) * math.sqrt(252))
    move_60 = float(longer.std(ddof=1) * math.sqrt(252))
    return (0.70 * move_20 + 0.30 * move_60) * 100
