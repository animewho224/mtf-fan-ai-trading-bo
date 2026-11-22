import os
import logging
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Yahoo Finance symbols are DATA PROXIES, not guaranteed to match a broker's CFD quote.
MARKETS = {
    "XAUUSD (Gold proxy: GC=F)": "GC=F",
    "BTCUSD (spot proxy: BTC-USD)": "BTC-USD",
    "NASDAQ (Nasdaq-100 futures proxy: NQ=F)": "NQ=F",
}
TIMEFRAMES = ["M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"]


def clean_ohlcv(df):
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    needed = ["Open", "High", "Low", "Close", "Volume"]
    if not all(c in df.columns for c in needed):
        return pd.DataFrame()
    out = df[needed].copy().dropna(subset=["Open", "High", "Low", "Close"])
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out


def download_data(symbol):
    # Yahoo Finance limits intraday history. Daily history is used for D1/W1/MN1.
    intraday = clean_ohlcv(yf.download(symbol, period="5d", interval="5m",
                                       auto_adjust=False, progress=False, threads=False))
    hourly = clean_ohlcv(yf.download(symbol, period="730d", interval="1h",
                                     auto_adjust=False, progress=False, threads=False))
    daily = clean_ohlcv(yf.download(symbol, period="10y", interval="1d",
                                    auto_adjust=False, progress=False, threads=False))
    return intraday, hourly, daily


def resample_ohlcv(df, rule):
    if df.empty:
        return df
    return df.resample(rule).agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum"
    }).dropna(subset=["Open", "High", "Low", "Close"])


def make_timeframes(intraday, hourly, daily):
    frames = {}
    frames["M5"] = intraday
    frames["M15"] = resample_ohlcv(intraday, "15min")
    frames["M30"] = resample_ohlcv(intraday, "30min")
    frames["H1"] = hourly
    frames["H4"] = resample_ohlcv(hourly, "4h")
    frames["D1"] = daily
    frames["W1"] = resample_ohlcv(daily, "W")
    frames["MN1"] = resample_ohlcv(daily, "MS")
    return {k: v for k, v in frames.items() if not v.empty}


def pivots(df, left=3, right=3):
    """Return confirmed pivot-high and pivot-low indices; right bars confirm a pivot."""
    highs, lows = [], []
    h = df["High"].to_numpy()
    l = df["Low"].to_numpy()
    for i in range(left, len(df) - right):
        if h[i] >= max(h[i-left:i+right+1]):
            highs.append(i)
        if l[i] <= min(l[i-left:i+right+1]):
            lows.append(i)
    return highs, lows


def fan_lines(df, kind, max_pivots=12):
    """Create projected trendlines from pairs of confirmed pivots."""
    if len(df) < 25:
        return []
    hi, lo = pivots(df)
    points = hi if kind == "R" else lo
    points = points[-max_pivots:]
    lines = []
    n = len(df) - 1
    for a in range(len(points)):
        for b in range(a + 1, len(points)):
            i, j = points[a], points[b]
            if j - i < 4:
                continue
            p1 = float(df["High"].iloc[i] if kind == "R" else df["Low"].iloc[i])
            p2 = float(df["High"].iloc[j] if kind == "R" else df["Low"].iloc[j])
            slope = (p2 - p1) / (j - i)
            # Resistance fan descends; support fan ascends.
            if kind == "R" and slope >= 0:
                continue
            if kind == "S" and slope <= 0:
                continue
            projected = p2 + slope * (n - j)
            if projected > 0:
                lines.append(projected)
    return lines[-30:]


def horizontal_levels(df, kind):
    hi, lo = pivots(df)
    inds = hi if kind == "R" else lo
    col = "High" if kind == "R" else "Low"
    return [float(df[col].iloc[i]) for i in inds[-12:]]


def cluster_levels(values, tolerance):
    clusters = []
    for value in sorted(values):
        placed = False
        for c in clusters:
            if abs(value - sum(c) / len(c)) <= tolerance:
                c.append(value)
                placed = True
                break
        if not placed:
            clusters.append([value])
    return sorted(
        [(sum(c) / len(c), len(c)) for c in clusters],
        key=lambda x: (x[1], -x[0]), reverse=True
    )


def analyze_market(label, symbol):
    intraday, hourly, daily = download_data(symbol)
    frames = make_timeframes(intraday, hourly, daily)
    if "M5" not in frames or len(frames["M5"]) < 40:
        return f"⚠️ {label}: Data M5 tidak mencukupi sekarang."

    price = float(frames["M5"]["Close"].iloc[-1])
    supports, resistances, trend = [], [], []
    tf_notes = []

    for tf in TIMEFRAMES:
        df = frames.get(tf)
        if df is None or len(df) < 25:
            continue
        last = float(df["Close"].iloc[-1])
        r = fan_lines(df, "R") + horizontal_levels(df, "R")
        s = fan_lines(df, "S") + horizontal_levels(df, "S")
        # Convert each timeframe's levels into the current market-price scale.
        resistances.extend([(x, tf) for x in r if x > 0])
        supports.extend([(x, tf) for x in s if x > 0])
        if len(df) >= 21:
            ema20 = float(df["Close"].ewm(span=20).mean().iloc[-1])
            ema50 = float(df["Close"].ewm(span=50).mean().iloc[-1])
            trend.append("bull" if last > ema20 > ema50 else "bear" if last < ema20 < ema50 else "neutral")
        tf_notes.append(tf)

    # Cluster levels within 0.25% of current price (minimum absolute tolerance).
    tol = max(price * 0.0025, 0.01)
    r_clusters = cluster_levels([x for x, _ in resistances if abs(x-price) < price*0.08], tol)
    s_clusters = cluster_levels([x for x, _ in supports if abs(x-price) < price*0.08], tol)

    nearest_r = min((x for x in r_clusters if x[0] >= price), key=lambda z: z[0], default=None)
    nearest_s = max((x for x in s_clusters if x[0] <= price), key=lambda z: z[0], default=None)

    m5 = frames["M5"]
    prev = m5.iloc[-2]
    curr = m5.iloc[-1]
    bearish_reject = curr["Close"] < curr["Open"] and curr["High"] > prev["High"] and curr["Close"] < prev["Close"]
    bullish_reject = curr["Close"] > curr["Open"] and curr["Low"] < prev["Low"] and curr["Close"] > prev["Close"]
    bull_count = trend.count("bull")
    bear_count = trend.count("bear")
    bias = "BULLISH" if bull_count > bear_count else "BEARISH" if bear_count > bull_count else "MIXED"

    # Educational/watchlist signals only; never execute trades.
    signal = "WAIT"
    if nearest_r and nearest_r[1] >= 3 and abs(price-nearest_r[0]) <= tol and bearish_reject:
        signal = "SELL WATCH"
    elif nearest_s and nearest_s[1] >= 3 and abs(price-nearest_s[0]) <= tol and bullish_reject:
        signal = "BUY WATCH"

    def fmt(level):
        return f"{level[0]:,.2f} (gabungan {level[1]} level)" if level else "Tiada zon berhampiran"

    return (
        f"📊 {label}\n"
        f"Harga data: {price:,.2f}\n"
        f"Bias EMA MTF: {bias}\n"
        f"Resistance terdekat: {fmt(nearest_r)}\n"
        f"Support terdekat: {fmt(nearest_s)}\n"
        f"Isyarat: {signal}\n"
        f"Timeframe tersedia: {', '.join(tf_notes)}\n"
        f"Nota: zon ialah anggaran teknikal; sahkan harga/spread pada broker."
    )


def send_telegram(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID dalam GitHub Secrets.")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    response = requests.post(url, json={
        "chat_id": chat_id, "text": message, "disable_web_page_preview": True
    }, timeout=20)
    response.raise_for_status()


def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts = [f"🤖 MTF FAN AI | {now}", "Analisis automatik setiap 5 minit", ""]
    for label, symbol in MARKETS.items():
        try:
            parts.append(analyze_market(label, symbol))
        except Exception as exc:
            logging.exception("Analysis failed for %s", symbol)
            parts.append(f"⚠️ {label}: gagal ambil data ({type(exc).__name__}).")
        parts.append("")
    parts.append("⚠️ Bukan nasihat kewangan atau arahan auto-trade. Tiada order dihantar.")
    send_telegram("\n".join(parts))


if __name__ == "__main__":
    main()
