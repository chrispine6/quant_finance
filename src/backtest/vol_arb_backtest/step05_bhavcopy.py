"""Download NSE F&O bhavcopies and turn Reliance rows into sessions."""

import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from curl_cffi import requests

from backtest.vol_arb_backtest.step01_config import BHAV_URL, CACHE, COLUMNS
from backtest.vol_arb_backtest.step03_books import Session


def _fetch_zip(stamp: str) -> tuple[str, bytes | None, int | None]:
    url = BHAV_URL.format(yyyymmdd=stamp)
    status = None
    for _attempt in range(3):
        response = requests.get(url, impersonate="chrome", timeout=40)
        status = response.status_code
        if status == 200 and response.content[:2] == b"PK":
            return stamp, response.content, status
        if status == 404:
            return stamp, None, status
    return stamp, None, status


def download_bhavcopies(start: date, end: date, cache: Path = CACHE) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    missing_path = cache / "missing.txt"
    missing = set(missing_path.read_text().split()) if missing_path.exists() else set()
    wanted: list[date] = []
    cursor = start
    while cursor <= end:
        key = cursor.isoformat()
        path = cache / f"BhavCopy_NSE_FO_0_0_0_{cursor.strftime('%Y%m%d')}_F_0000.csv.zip"
        if cursor.weekday() < 5 and not path.exists() and key not in missing:
            wanted.append(cursor)
        cursor += timedelta(days=1)
    if not wanted:
        return
    print(f"fetching {len(wanted)} bhavcopies")
    newly_missing = []
    done = 0
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(_fetch_zip, day.strftime("%Y%m%d")) for day in wanted]
        for future in as_completed(futures):
            stamp, body, status = future.result()
            done += 1
            key = f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}"
            if body is None and status == 404:
                newly_missing.append(key)
            elif body is None:
                print(f"no file {key} status {status}")
            else:
                (cache / f"BhavCopy_NSE_FO_0_0_0_{stamp}_F_0000.csv.zip").write_bytes(body)
            if done % 50 == 0 or done == len(wanted):
                print(f"bhavcopy requests {done}/{len(wanted)}")
    if newly_missing:
        missing.update(newly_missing)
        missing_path.write_text("\n".join(sorted(missing)) + "\n")


def load_reliance(cache: Path = CACHE) -> pd.DataFrame:
    frames = []
    for path in sorted(cache.glob("BhavCopy_NSE_FO_0_0_0_*.csv.zip")):
        with zipfile.ZipFile(path) as archive:
            name = archive.namelist()[0]
            frame = pd.read_csv(archive.open(name), usecols=lambda column: column in COLUMNS)
        if "TckrSymb" not in frame.columns:
            continue
        keep = frame[frame["TckrSymb"].eq("RELIANCE") & frame["FinInstrmTp"].isin(["STO", "STF"])]
        if not keep.empty:
            frames.append(keep)
    if not frames:
        return pd.DataFrame(columns=COLUMNS)
    return pd.concat(frames, ignore_index=True)


def sessions_from_frame(frame: pd.DataFrame) -> list[Session]:
    frame = frame.copy()
    frame["TradDt"] = pd.to_datetime(frame["TradDt"]).dt.date
    frame["XpryDt"] = pd.to_datetime(frame["XpryDt"]).dt.date
    sessions = []
    for day, block in frame.groupby("TradDt", sort=True):
        spot_values = block["UndrlygPric"].dropna()
        if spot_values.empty:
            continue
        futures = {}
        options = {}
        for row in block.itertuples(index=False):
            lot = int(row.NewBrdLotQty) if pd.notna(row.NewBrdLotQty) else 0
            settle = float(row.SttlmPric) if pd.notna(row.SttlmPric) else 0.0
            volume = int(row.TtlTradgVol) if pd.notna(row.TtlTradgVol) else 0
            if row.FinInstrmTp == "STF":
                futures[row.XpryDt] = (settle, lot)
            elif row.FinInstrmTp == "STO" and row.OptnTp in ("CE", "PE") and pd.notna(row.StrkPric):
                strike = round(float(row.StrkPric), 2)
                options[(row.XpryDt, strike, row.OptnTp)] = (settle, lot, volume)
        if futures and options:
            sessions.append(Session(day, float(spot_values.median()), futures, options))
    return sessions
