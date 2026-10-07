from io import StringIO
import pandas as pd
import requests
import yfinance

url="https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"
response=requests.get(url, headers={f"User-Agent":"Mozilla/5.0"}, timeout=30)
response.raise_for_status()

members=pd.read_csv(StringIO(response.text))
symbols=members["Symbol"].to_list()

tickers=[f"{symbol}.NS" for symbol in symbols]
closes=yfinance.download(tickers, period="1y", auto_adjust=True)["Close"]