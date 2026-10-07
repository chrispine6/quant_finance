"""Brokerage, stamp, and securities transaction tax, charged in option points."""

from datetime import date

from backtest.vol_arb_backtest.step01_config import BROKERAGE_RUPEES, STT_CHANGE
from backtest.vol_arb_backtest.step03_books import Position


def option_sell_stt(day: date) -> float:
    return 0.0015 if day >= STT_CHANGE else 0.001


def future_sell_stt(day: date) -> float:
    return 0.0005 if day >= STT_CHANGE else 0.0002


def exercise_stt(day: date) -> float:
    return 0.0015 if day >= STT_CHANGE else 0.00125


def brokerage_points(lot: int) -> float:
    return BROKERAGE_RUPEES / lot


def charge_option(position: Position, premium: float, selling: bool, day: date, exercising: bool = False) -> None:
    points = brokerage_points(position.option_lot)
    if selling and not exercising:
        points += option_sell_stt(day) * premium
    elif exercising:
        points += exercise_stt(day) * premium
    elif not selling:
        points += 0.00003 * premium
    position.cost_points += points


def charge_future(position: Position, price: float, lots: int, day: date) -> None:
    if lots == 0:
        return
    traded = abs(lots)
    points = brokerage_points(position.future_lot) * traded
    if lots < 0:
        points += future_sell_stt(day) * price * traded
    else:
        points += 0.00002 * price * traded
    scale = position.future_lot / position.option_lot
    position.cost_points += points * scale
