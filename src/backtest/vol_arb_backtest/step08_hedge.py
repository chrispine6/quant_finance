"""Mark the book, hedge delta with futures, and close when an exit hits."""

import math

from backtest.vol_arb_backtest.step01_config import GAP_MULTIPLE, RATE, REHEDGE_LOTS, SHORT_LOSS_MULTIPLE
from backtest.vol_arb_backtest.step02_pricing import black76_delta, leg_vol, round_lots, year_fraction
from backtest.vol_arb_backtest.step03_books import Pending, Position, Session, quote
from backtest.vol_arb_backtest.step04_costs import charge_future, charge_option


def marked_prices(position: Position, session: Session) -> tuple[float, float, float]:
    future_row = session.futures.get(position.expiry)
    future = future_row[0] if future_row else position.future_prev
    # On expiry the file repeats the underlying price in every option's settlement field.
    # The contract settles at intrinsic value.
    if session.day >= position.expiry:
        return (
            max(session.spot - position.strike, 0.0),
            max(position.strike - session.spot, 0.0),
            future,
        )
    call = quote(session, position.expiry, position.strike, "CE")
    put = quote(session, position.expiry, position.strike, "PE")
    call_price = call[0] if call else max(session.spot - position.strike, 0.0)
    put_price = put[0] if put else max(position.strike - session.spot, 0.0)
    return call_price, put_price, future


def mark(position: Position, session: Session) -> None:
    call_price, put_price, future = marked_prices(position, session)
    position.gross_points += position.direction * (
        (call_price - position.call_prev) + (put_price - position.put_prev)
    )
    scale = position.future_lot / position.option_lot
    position.gross_points += position.futures_lots * scale * (future - position.future_prev)
    position.call_prev = call_price
    position.put_prev = put_price
    position.future_prev = future


def option_delta_lots(position: Position, session: Session) -> float | None:
    future_row = session.futures.get(position.expiry)
    call = quote(session, position.expiry, position.strike, "CE")
    put = quote(session, position.expiry, position.strike, "PE")
    if future_row is None or call is None or put is None:
        return None
    future, _lot = future_row
    time = year_fraction(session.day, position.expiry)
    if time <= 0:
        return None
    call_sigma = leg_vol(call[0], future, position.strike, time, "CE") or position.call_sigma
    put_sigma = leg_vol(put[0], future, position.strike, time, "PE") or position.put_sigma
    call_delta = black76_delta(future, position.strike, time, RATE, call_sigma, "CE")
    put_delta = black76_delta(future, position.strike, time, RATE, put_sigma, "PE")
    per_share = position.direction * (call_delta + put_delta)
    return per_share * position.option_lot / position.future_lot


def rehedge(position: Position, session: Session) -> None:
    delta_lots = option_delta_lots(position, session)
    future_row = session.futures.get(position.expiry)
    if delta_lots is None or future_row is None:
        return
    residual = delta_lots + position.futures_lots
    if abs(residual) < REHEDGE_LOTS:
        return
    # Futures lots that put option delta + futures delta back through zero.
    target = round_lots(-delta_lots)
    trade = target - position.futures_lots
    if trade == 0:
        return
    future, _lot = future_row
    charge_future(position, future, trade, session.day)
    position.futures_lots = target
    position.hedge_trades += 1


def loss_limit_hit(position: Position) -> bool:
    if position.direction < 0:
        return position.net_points <= -SHORT_LOSS_MULTIPLE * position.premium
    return position.net_points <= -position.premium


def gap_hit(position: Position, session: Session, previous_spot: float) -> bool:
    if previous_spot <= 0 or session.spot <= 0:
        return False
    move = abs(math.log(session.spot / previous_spot))
    normal_day = (position.entry_forecast_pct / 100) / math.sqrt(252)
    return move > GAP_MULTIPLE * normal_day


def iv_gap(position: Position, session: Session, forecast: float | None) -> float | None:
    if forecast is None:
        return None
    future_row = session.futures.get(position.expiry)
    call = quote(session, position.expiry, position.strike, "CE")
    put = quote(session, position.expiry, position.strike, "PE")
    if future_row is None or call is None or put is None:
        return None
    time = year_fraction(session.day, position.expiry)
    if time <= 0:
        return None
    future, _lot = future_row
    call_sigma = leg_vol(call[0], future, position.strike, time, "CE")
    put_sigma = leg_vol(put[0], future, position.strike, time, "PE")
    if call_sigma is None or put_sigma is None:
        return None
    atm_iv = 0.5 * (call_sigma + put_sigma) * 100
    return abs(atm_iv - forecast)


def close_position(
    position: Position,
    session: Session,
    reason: str,
    call_price: float | None = None,
    put_price: float | None = None,
) -> dict:
    if call_price is None or put_price is None:
        call_price, put_price, _future = marked_prices(position, session)
    exercising = reason == "expiry" and position.direction > 0
    charge_option(position, call_price, selling=position.direction > 0, day=session.day, exercising=exercising)
    charge_option(position, put_price, selling=position.direction > 0, day=session.day, exercising=exercising)
    lots_at_exit = position.futures_lots
    if lots_at_exit != 0:
        future_row = session.futures.get(position.expiry)
        future = future_row[0] if future_row else position.future_prev
        charge_future(position, future, -lots_at_exit, session.day)
        position.futures_lots = 0
    return {
        "entry": position.entry_day,
        "exit": session.day,
        "direction": "short" if position.direction < 0 else "long",
        "expiry": position.expiry,
        "strike": position.strike,
        "premium": position.premium,
        "entry_forecast": position.entry_forecast_pct,
        "entry_edge": position.entry_edge,
        "reason": reason,
        "hold_sessions": None,
        "gross_points": position.gross_points,
        "cost_points": position.cost_points,
        "net_points": position.net_points,
        "net_rupees": position.net_points * position.option_lot,
        "hedge_trades": position.hedge_trades,
        "futures_lots_at_exit": lots_at_exit,
        "spot_entry": None,
        "spot_exit": session.spot,
    }


def try_enter(session: Session, pending: Pending) -> Position | None:
    if session.day >= pending.expiry:
        return None
    call = quote(session, pending.expiry, pending.strike, "CE")
    put = quote(session, pending.expiry, pending.strike, "PE")
    future_row = session.futures.get(pending.expiry)
    if call is None or put is None or future_row is None or call[2] <= 0 or put[2] <= 0:
        return None
    future, future_lot = future_row
    time = year_fraction(session.day, pending.expiry)
    if time <= 0 or future_lot <= 0 or call[1] <= 0:
        return None
    call_sigma = leg_vol(call[0], future, pending.strike, time, "CE")
    put_sigma = leg_vol(put[0], future, pending.strike, time, "PE")
    if call_sigma is None or put_sigma is None:
        return None
    position = Position(
        expiry=pending.expiry,
        strike=pending.strike,
        direction=pending.direction,
        entry_day=session.day,
        entry_forecast_pct=pending.forecast_pct,
        entry_edge=pending.edge,
        call_entry=call[0],
        put_entry=put[0],
        option_lot=call[1],
        future_lot=future_lot,
        call_sigma=call_sigma,
        put_sigma=put_sigma,
        future_prev=future,
        call_prev=call[0],
        put_prev=put[0],
    )
    # Opening a short sells both options. Opening a long buys them.
    charge_option(position, call[0], selling=position.direction < 0, day=session.day)
    charge_option(position, put[0], selling=position.direction < 0, day=session.day)
    rehedge(position, session)
    return position
