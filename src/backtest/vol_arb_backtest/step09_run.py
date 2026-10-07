"""Daily loop: exit, hedge, then fill yesterday's signal on today's settlement."""

import math
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from backtest.vol_arb_backtest.step01_config import IV_EXIT_POINTS, RATE, SAMPLE_START
from backtest.vol_arb_backtest.step02_pricing import black76, implied_vol, year_fraction
from backtest.vol_arb_backtest.step03_books import Pending, Position, Session
from backtest.vol_arb_backtest.step05_bhavcopy import download_bhavcopies, load_reliance, sessions_from_frame
from backtest.vol_arb_backtest.step06_forecast import cleaned_returns, forecast_pct
from backtest.vol_arb_backtest.step07_signal import signal_for
from backtest.vol_arb_backtest.step08_hedge import (
    close_position,
    gap_hit,
    iv_gap,
    loss_limit_hit,
    mark,
    rehedge,
    try_enter,
)


def run_sessions(sessions: list[Session]) -> tuple[dict, pd.DataFrame]:
    spots = [session.spot for session in sessions]
    returns = cleaned_returns(spots)
    pending: Pending | None = None
    position: Position | None = None
    trades: list[dict] = []
    entry_spots: dict[date, float] = {}
    for index, session in enumerate(sessions):
        previous_spot = spots[index - 1] if index else session.spot
        today_return = returns[index - 1] if index else 0.0
        adjustment = bool(index and np.isnan(today_return))
        forecast = forecast_pct(returns, index)
        if position is not None and session.day > position.entry_day:
            reason = None
            exit_call = exit_put = None
            if adjustment:
                reason = "adjustment"
                exit_call = position.call_prev
                exit_put = position.put_prev
            elif session.day >= position.expiry:
                mark(position, session)
                reason = "expiry"
            else:
                mark(position, session)
                if gap_hit(position, session, previous_spot):
                    reason = "gap"
                elif loss_limit_hit(position):
                    reason = "loss"
                elif forecast is not None:
                    gap = iv_gap(position, session, forecast)
                    if gap is not None and gap <= IV_EXIT_POINTS:
                        reason = "iv"
            if reason is not None:
                trade = close_position(
                    position, session, reason, call_price=exit_call, put_price=exit_put
                )
                trade["spot_entry"] = entry_spots.pop(position.entry_day, None)
                trade["hold_sessions"] = index - next(
                    i for i, item in enumerate(sessions) if item.day == position.entry_day
                )
                trades.append(trade)
                position = None
            else:
                rehedge(position, session)
        if position is None and pending is not None:
            opened = try_enter(session, pending)
            pending = None
            if opened is not None:
                position = opened
                entry_spots[session.day] = session.spot
        if position is None and pending is None and forecast is not None and index + 1 < len(sessions):
            chosen = signal_for(session, forecast)
            if chosen is not None:
                pending = chosen
    open_points = position.net_points if position is not None else 0.0
    frame = pd.DataFrame(trades)
    if frame.empty:
        summary = {
            "trades": 0,
            "net_points": 0.0,
            "net_rupees": 0.0,
            "open_points": open_points,
        }
        return summary, frame
    by_reason = frame["reason"].value_counts().to_dict()
    summary = {
        "sessions": len(sessions),
        "first": sessions[0].day.isoformat(),
        "last": sessions[-1].day.isoformat(),
        "trades": int(len(frame)),
        "shorts": int((frame["direction"] == "short").sum()),
        "longs": int((frame["direction"] == "long").sum()),
        "net_points": float(frame["net_points"].sum()),
        "gross_points": float(frame["gross_points"].sum()),
        "cost_points": float(frame["cost_points"].sum()),
        "net_rupees": float(frame["net_rupees"].sum()),
        "average_net_points": float(frame["net_points"].mean()),
        "median_hold_sessions": float(frame["hold_sessions"].median()),
        "one_session_holds": int((frame["hold_sessions"] <= 1).sum()),
        "hedge_trades": int(frame["hedge_trades"].sum()),
        "exits": by_reason,
        "open_points": open_points,
    }
    return summary, frame


def run(start: date = SAMPLE_START, end: date | None = None) -> tuple[dict, pd.DataFrame]:
    if end is None:
        now = datetime.now(ZoneInfo("Asia/Kolkata"))
        end = now.date()
        close = now.replace(hour=15, minute=30, second=0, microsecond=0)
        if now < close:
            end -= timedelta(days=1)
    download_bhavcopies(start, end)
    sessions = sessions_from_frame(load_reliance())
    sessions = [session for session in sessions if start <= session.day <= end]
    summary, trades = run_sessions(sessions)
    return summary, trades


def _book(day: date, expiry: date, spot: float, strike: float, direction: int) -> tuple[Session, Position]:
    time = year_fraction(day, expiry)
    future = spot * math.exp(RATE * time)
    call = black76(future, strike, time, RATE, 0.25, "CE")
    put = black76(future, strike, time, RATE, 0.25, "PE")
    session = Session(
        day,
        spot,
        {expiry: (future, 500)},
        {
            (expiry, strike, "CE"): (call, 500, 100),
            (expiry, strike, "PE"): (put, 500, 100),
        },
    )
    position = Position(
        expiry=expiry,
        strike=strike,
        direction=direction,
        entry_day=day - timedelta(days=1),
        entry_forecast_pct=18.0,
        entry_edge=-5.0,
        call_entry=call,
        put_entry=put,
        option_lot=500,
        future_lot=500,
        call_sigma=0.25,
        put_sigma=0.25,
        future_prev=future,
        call_prev=call,
        put_prev=put,
    )
    return session, position


def self_check() -> None:
    price = black76(100, 100, 20 / 252, RATE, 0.25, "CE")
    solved = implied_vol(price, 100, 100, 20 / 252, RATE, "CE")
    if solved is None or abs(solved - 0.25) > 1e-3:
        raise AssertionError(f"implied vol roundtrip failed: {solved}")

    expiry = date(2024, 8, 29)
    short_session, short_position = _book(date(2024, 7, 2), expiry, 1100, 1000, -1)
    rehedge(short_position, short_session)
    if short_position.futures_lots <= 0:
        raise AssertionError(f"short rally hedge sold or skipped: {short_position.futures_lots}")

    long_session, long_position = _book(date(2024, 7, 2), expiry, 1100, 1000, 1)
    rehedge(long_position, long_session)
    if long_position.futures_lots >= 0:
        raise AssertionError(f"long rally hedge bought or skipped: {long_position.futures_lots}")

    down_session, down_position = _book(date(2024, 7, 2), expiry, 900, 1000, -1)
    rehedge(down_position, down_session)
    if down_position.futures_lots >= 0:
        raise AssertionError(f"short decline hedge bought or skipped: {down_position.futures_lots}")
    print(
        "self_check ok",
        f"short rally futures {short_position.futures_lots}",
        f"long rally futures {long_position.futures_lots}",
        f"short decline futures {down_position.futures_lots}",
    )


if __name__ == "__main__":
    self_check()
    summary, trades = run()
    print(summary)
    if not trades.empty:
        print(trades.to_string(index=False))
