"""One session, a pending order, and an open straddle."""

from dataclasses import dataclass
from datetime import date


@dataclass
class Session:
    day: date
    spot: float
    futures: dict[date, tuple[float, int]]
    options: dict[tuple[date, float, str], tuple[float, int, int]]


@dataclass
class Pending:
    expiry: date
    strike: float
    direction: int
    forecast_pct: float
    edge: float


@dataclass
class Position:
    expiry: date
    strike: float
    direction: int
    entry_day: date
    entry_forecast_pct: float
    entry_edge: float
    call_entry: float
    put_entry: float
    option_lot: int
    future_lot: int
    call_sigma: float
    put_sigma: float
    futures_lots: int = 0
    future_prev: float = 0.0
    call_prev: float = 0.0
    put_prev: float = 0.0
    gross_points: float = 0.0
    cost_points: float = 0.0
    hedge_trades: int = 0

    @property
    def premium(self) -> float:
        return self.call_entry + self.put_entry

    @property
    def net_points(self) -> float:
        return self.gross_points - self.cost_points


def quote(session: Session, expiry: date, strike: float, right: str) -> tuple[float, int, int] | None:
    row = session.options.get((expiry, strike, right))
    if row is None or row[0] <= 0:
        return None
    return row


def nearest_expiry(session: Session) -> date | None:
    later = [expiry for expiry in session.futures if expiry > session.day]
    return min(later) if later else None
