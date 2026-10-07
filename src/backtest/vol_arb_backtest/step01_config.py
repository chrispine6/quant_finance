"""Paths, rates, and the entry and exit thresholds."""

from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / "data" / "fo_bhavcopy"
BHAV_URL = (
    "https://nsearchives.nseindia.com/content/fo/"  #nse archive link
    "BhavCopy_NSE_FO_0_0_0_{yyyymmdd}_F_0000.csv.zip"
)
COLUMNS = [
    "TradDt",
    "XpryDt",
    "TckrSymb",
    "FinInstrmTp",
    "StrkPric",
    "OptnTp",
    "SttlmPric",
    "UndrlygPric",
    "TtlTradgVol",
    "NewBrdLotQty",
]

RATE = 0.065    #india's risk free interst rate
REHEDGE_LOTS = 0.5
IV_EXIT_POINTS = 1.0
LONG_ENTRY_EDGE = 3.0
SHORT_LOSS_MULTIPLE = 2.0
GAP_MULTIPLE = 2.0
BROKERAGE_RUPEES = 20 * 1.18
STT_CHANGE = date(2026, 4, 1)
SAMPLE_START = date(2024, 7, 8)
