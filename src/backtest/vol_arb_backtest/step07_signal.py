"""Nearest-expiry ATM straddle signal from forecast minus implied vol."""

from backtest.vol_arb_backtest.step01_config import LONG_ENTRY_EDGE
from backtest.vol_arb_backtest.step02_pricing import leg_vol, year_fraction
from backtest.vol_arb_backtest.step03_books import Pending, Session, nearest_expiry, quote


def signal_for(session: Session, forecast: float) -> Pending | None:
    expiry = nearest_expiry(session)
    if expiry is None:
        return None
    time = year_fraction(session.day, expiry)
    if time <= 0:
        return None
    future_row = session.futures.get(expiry)
    if future_row is None:
        return None
    future, _lot = future_row
    strikes = {strike for exp, strike, _right in session.options if exp == expiry}
    if not strikes:
        return None
    strike = min(strikes, key=lambda item: (abs(item - session.spot), item))
    call = quote(session, expiry, strike, "CE")
    put = quote(session, expiry, strike, "PE")
    if call is None or put is None or call[2] <= 0 or put[2] <= 0:
        return None
    call_sigma = leg_vol(call[0], future, strike, time, "CE")
    put_sigma = leg_vol(put[0], future, strike, time, "PE")
    if call_sigma is None or put_sigma is None or abs(call_sigma - put_sigma) * 100 > 25:
        return None
    atm_iv = 0.5 * (call_sigma + put_sigma) * 100
    edge = forecast - atm_iv
    if edge < 0:
        direction = -1
    elif edge > LONG_ENTRY_EDGE:
        direction = 1
    else:
        return None
    return Pending(expiry, strike, direction, forecast, edge)
