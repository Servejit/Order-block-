import time
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
import yfinance as yf

IST = ZoneInfo("Asia/Kolkata")
NIFTY200_URL = "https://www.niftyindices.com/IndexConstituent/ind_nifty200list.csv"
MARKET_OPEN_MINUTES = 9 * 60 + 15
MARKET_CLOSE_MINUTES = 15 * 60 + 30

st.set_page_config(page_title="NIFTY 200 Reversal Scanner", page_icon="📈", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 1.4rem; padding-bottom: 2rem;}
h1, h2, h3 {letter-spacing: -.4px;}
[data-testid="stMetric"] {background: var(--secondary-background-color); padding: 14px; border-radius: 12px;}
div[data-testid="stDataFrame"] {border: 1px solid rgba(128,128,128,.2); border-radius: 10px;}
.small-note {font-size: .88rem; opacity: .8;}
</style>
""", unsafe_allow_html=True)

st.title("📈 NIFTY 200 — Intraday Reversal Scanner")
st.caption("Daily downside sweep → 1-hour downside sweep → 5-minute reclaim trigger")

with st.sidebar:
    st.header("Scanner settings")
    refresh_seconds = st.selectbox("Auto-refresh", [0, 30, 60, 120, 300], index=2,
                                   format_func=lambda x: "Off" if x == 0 else f"{x} seconds")
    batch_size = st.select_slider("Symbols per data batch", options=[10, 20, 25, 40, 50], value=20)
    scan_button = st.button("🔄 Scan NIFTY 200 now", type="primary", use_container_width=True)
    st.divider()
    st.markdown("**Data source:** Yahoo Finance via yfinance")
    st.markdown("**Market:** NSE · India (IST)")
    st.markdown("**Use:** Research / paper trading only")

if refresh_seconds:
    st.autorefresh = None
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=refresh_seconds * 1000, key="nifty200_refresh")
    except Exception:
        st.sidebar.info("Install streamlit-autorefresh to enable automatic refresh.")

@st.cache_data(ttl=3600, show_spinner=False)
def load_nifty200():
    headers = {"User-Agent": "Mozilla/5.0"}
    response = pd.read_csv(NIFTY200_URL, storage_options={"User-Agent": headers["User-Agent"]})
    symbol_col = next((c for c in response.columns if c.strip().lower() in ("symbol", "ticker")), None)
    name_col = next((c for c in response.columns if c.strip().lower() in ("company name", "company")), None)
    if symbol_col is None:
        raise ValueError("The NIFTY 200 constituent CSV did not contain a Symbol column.")
    result = response[[symbol_col] + ([name_col] if name_col else [])].copy()
    result.columns = ["Symbol"] + (["Company"] if name_col else [])
    result["Ticker"] = result["Symbol"].astype(str).str.strip() + ".NS"
    return result.drop_duplicates("Ticker").reset_index(drop=True)

def normalize_intraday(frame):
    if frame is None or frame.empty:
        return pd.DataFrame()
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    needed = ["Open", "High", "Low", "Close", "Volume"]
    if any(c not in frame.columns for c in needed):
        return pd.DataFrame()
    frame = frame[needed].dropna(subset=["Open", "High", "Low", "Close"]).copy()
    idx = pd.to_datetime(frame.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    frame.index = idx.tz_convert(IST)
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    return frame

def today_hourly_bars(intraday):
    """Build NSE-session hours from 5-minute candles, anchored at 09:15 IST."""
    if intraday.empty:
        return pd.DataFrame()
    today = datetime.now(IST).date()
    data = intraday[intraday.index.date == today].copy()
    if data.empty:
        return pd.DataFrame()
    mins = data.index.hour * 60 + data.index.minute
    data = data[(mins >= MARKET_OPEN_MINUTES) & (mins < MARKET_CLOSE_MINUTES)].copy()
    if data.empty:
        return pd.DataFrame()
    mins = data.index.hour * 60 + data.index.minute
    data["hour_bucket"] = ((mins - MARKET_OPEN_MINUTES) // 60).astype(int)
    hourly = data.groupby("hour_bucket").agg(
        Open=("Open", "first"), High=("High", "max"), Low=("Low", "min"),
        Close=("Close", "last"), Volume=("Volume", "sum")
    )
    hourly["Start"] = hourly.index.map(
        lambda n: datetime.combine(today, dt_time(9, 15), tzinfo=IST) + pd.Timedelta(hours=int(n))
    )
    return hourly

def fetch_one(ticker):
    # Yahoo intraday history is used only as a free indicative feed; it is not an exchange-grade feed.
    raw = yf.download(ticker, period="5d", interval="5m", progress=False,
                      auto_adjust=False, threads=False, timeout=15)
    return normalize_intraday(raw)

def analyze_symbol(ticker, symbol, company, frame):
    """Return a scored candidate even when only some scan conditions match."""
    if frame.empty:
        return None

    today = datetime.now(IST).date()
    today_data = frame[frame.index.date == today].copy()
    if today_data.empty:
        return None

    dates = sorted(set(frame.index.date))
    previous_day = dates[-2] if len(dates) >= 2 else None
    prev_day_data = frame[frame.index.date == previous_day] if previous_day else pd.DataFrame()

    current_price = float(today_data["Close"].iloc[-1])
    today_low = float(today_data["Low"].min())
    prev_day_low = float(prev_day_data["Low"].min()) if not prev_day_data.empty else float("nan")
    daily_ok = bool(not prev_day_data.empty and today_low < prev_day_low and current_price > prev_day_low)

    hourly = today_hourly_bars(frame)
    hourly_ok = False
    current_hour_low = float("nan")
    current_hour_high = float("nan")
    previous_hour_low = float("nan")
    cross_found = False
    reclaim_time = "Not found"
    live_above_previous_hour_low = False
    last5 = today_data.iloc[-1]

    if len(hourly) >= 2:
        current_hour = hourly.iloc[-1]
        previous_hour = hourly.iloc[-2]
        current_hour_low = float(current_hour["Low"])
        current_hour_high = float(current_hour["High"])
        previous_hour_low = float(previous_hour["Low"])
        hourly_ok = bool(current_hour_low < previous_hour_low and current_price > previous_hour_low)
        live_above_previous_hour_low = bool(float(last5["Close"]) > previous_hour_low)

        current_hour_start = current_hour["Start"]
        hour_5m = today_data[today_data.index >= current_hour_start].copy()
        if len(hour_5m) >= 2:
            for i in range(1, len(hour_5m)):
                if (float(hour_5m["Close"].iloc[i - 1]) <= current_hour_low
                        and float(hour_5m["Close"].iloc[i]) > current_hour_low):
                    cross_found = True
                    reclaim_time = hour_5m.index[i].strftime("%H:%M")

    # Progressive score: full daily/hourly/5m setup ranks highest.
    score = (3 if daily_ok else 0) + (2 if hourly_ok else 0) + (2 if cross_found else 0) + (1 if live_above_previous_hour_low else 0)
    if daily_ok and hourly_ok and cross_found and live_above_previous_hour_low:
        match_level = "FULL MATCH"
    elif score >= 5:
        match_level = "NEAR MATCH"
    elif score >= 3:
        match_level = "PARTIAL MATCH"
    else:
        match_level = "WATCHLIST"

    return {
        "Symbol": symbol,
        "Company": company,
        "Price": current_price,
        "Match level": match_level,
        "Score": score,
        "Daily condition": "Yes" if daily_ok else "No",
        "1H condition": "Yes" if hourly_ok else "No",
        "5m cross": "Yes" if cross_found else "No",
        "Price above previous 1H low": "Yes" if live_above_previous_hour_low else "No",
        "Prev day low": prev_day_low,
        "Today low": today_low,
        "Prev 1H low": previous_hour_low,
        "Current 1H low": current_hour_low,
        "Current 1H high": current_hour_high,
        "5m close": float(last5["Close"]),
        "5m reclaim candle": reclaim_time,
        "Last update (IST)": today_data.index[-1].strftime("%H:%M:%S")
    }

def download_batch(tickers):
    # Fetch sequentially to reduce the chance of Yahoo rate limiting.
    results = {}
    progress = st.progress(0, text="Downloading intraday candles…")
    status = st.empty()
    total = len(tickers)
    for start in range(0, total, batch_size):
        chunk = tickers[start:start + batch_size]
        for ticker in chunk:
            try:
                results[ticker] = fetch_one(ticker)
            except Exception:
                results[ticker] = pd.DataFrame()
        done = min(start + len(chunk), total)
        progress.progress(done / total, text=f"Downloaded {done} of {total} symbols")
        status.caption(f"Processing batch {start // batch_size + 1}")
        time.sleep(0.15)
    progress.empty()
    status.empty()
    return results

try:
    constituents = load_nifty200()
except Exception as exc:
    st.error(f"Could not load the NIFTY 200 constituent list: {exc}")
    st.info("Check your internet connection. The list is fetched from the official Nifty Indices constituent CSV.")
    st.stop()

st.caption(f"Universe: {len(constituents)} NIFTY 200 constituents · Last app check: {datetime.now(IST).strftime('%d %b %Y, %H:%M:%S IST')}")
st.info(
    "The scanner uses the latest available 5-minute Yahoo Finance candles. "
    "The 1-hour bars are constructed from today's 5-minute candles, aligned to the NSE 09:15 session open. "
    "A signal appears only when all three stages are true."
)

if "scan_results" not in st.session_state:
    st.session_state.scan_results = []
if "scan_time" not in st.session_state:
    st.session_state.scan_time = None

# Main-page rescan control, visible without opening the sidebar.
rescan_button = st.button("🔄 Rescan NIFTY 200", type="primary", use_container_width=True)

if scan_button or rescan_button or st.session_state.scan_time is None:
    with st.spinner("Scanning NIFTY 200. This can take several minutes on a free data feed…"):
        downloaded = download_batch(constituents["Ticker"].tolist())
        company_map = dict(zip(constituents["Ticker"], constituents.get("Company", constituents["Symbol"])))
        symbol_map = dict(zip(constituents["Ticker"], constituents["Symbol"]))
        found = []
        errors = 0
        for ticker, frame in downloaded.items():
            if frame.empty:
                errors += 1
                continue
            row = analyze_symbol(ticker, symbol_map[ticker], company_map[ticker], frame)
            if row:
                found.append(row)
        st.session_state.scan_results = found
        st.session_state.scan_time = datetime.now(IST)
        st.session_state.scan_errors = errors

results = st.session_state.scan_results
scan_time = st.session_state.scan_time
col1, col2, col3 = st.columns(3)
col1.metric("Qualified signals", len(results))
col2.metric("Stocks in universe", len(constituents))
col3.metric("Symbols with missing data", st.session_state.get("scan_errors", 0))
if scan_time:
    st.caption(f"Last completed scan: {scan_time.strftime('%d %b %Y, %H:%M:%S IST')}")

st.subheader("NIFTY 200 results — ranked by matching conditions")
st.caption("The scanner now shows full matches first, followed by near matches, partial matches and watchlist candidates. A relaxed candidate is not a full signal.")
if results:
    output = pd.DataFrame(results)
    output = output.sort_values(["Score", "Price"], ascending=[False, False]).reset_index(drop=True)
    display_cols = ["Symbol", "Company", "Price", "Match level", "Score",
                    "Daily condition", "1H condition", "5m cross",
                    "Price above previous 1H low", "Prev day low", "Today low",
                    "Prev 1H low", "Current 1H low", "Current 1H high",
                    "5m close", "5m reclaim candle", "Last update (IST)"]
    st.dataframe(output[display_cols], use_container_width=True, hide_index=True,
                 column_config={
                     "Price": st.column_config.NumberColumn(format="₹%.2f"),
                     "Prev day low": st.column_config.NumberColumn(format="₹%.2f"),
                     "Today low": st.column_config.NumberColumn(format="₹%.2f"),
                     "Prev 1H low": st.column_config.NumberColumn(format="₹%.2f"),
                     "Current 1H low": st.column_config.NumberColumn(format="₹%.2f"),
                     "Current 1H high": st.column_config.NumberColumn(format="₹%.2f"),
                     "5m close": st.column_config.NumberColumn(format="₹%.2f")
                 })
    csv = output.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download signals CSV", csv, "nifty200_reversal_signals.csv", "text/csv")

else:
    st.warning("No intraday data was received for today's session. Check the data connection or try again during/after NSE market hours.")

with st.expander("Exact scan rules"):
    st.markdown("""
    1. **Daily sweep and reclaim:** today's low < previous trading day's low, and latest price > previous day's low.
    2. **Hourly sweep and reclaim:** current session-hour low < previous completed session-hour low, and latest price > that previous hour's low.
    3. **5-minute reclaim:** any 5-minute candle in the current session-hour crosses from a close at/below the current 1-hour low to a close above it.
    4. **Live-price confirmation:** latest 5-minute price must remain above the previous completed 1-hour candle low.
    
    Results are ranked by these conditions. Full matches appear first; if none exist, the app still displays available stocks as near matches, partial matches or watchlist candidates. These fallback rows are not full trading signals.
    
    The app builds session-hour candles from 5-minute data, starting at 09:15 IST. The currently forming hour is included.
    """)

st.caption(
    "Important: Yahoo Finance is an unofficial third-party data source. Intraday coverage, timestamps, and prices can be delayed, "
    "missing, or throttled. Verify every signal with your broker/NSE chart before acting. This tool does not place orders or provide investment advice."
)
