import yfinance

def price(symbol: str) -> float:
    yahoo = symbol if "." in symbol or symbol.startswith("^") else f"{symbol}.NS"
    ticker = yfinance.Ticker(yahoo)
    last = ticker.fast_info.last_price
    if last == last:
        return float(last)

    bars = ticker.history(period="5d", auto_adjust=True)
    close = bars["Close"].dropna() if "Close" in bars else bars
    if close.empty:
        raise LookupError(yahoo)
    return float(close.iloc[-1])

def __getattr__(name: str) -> float:
    if name.startswith("_"):
        raise AttributeError(name)
    return price(name)