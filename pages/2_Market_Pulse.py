import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(page_title="Market Pulse | Servejit", page_icon="🌐", layout="wide")
st.title("🌐 NSE Market Pulse")
st.caption("Independent Tredye-style market overview built with free Yahoo Finance OHLCV data.")

st.info("Data note: this page uses publicly accessible Yahoo Finance data, which may be delayed, sampled, incomplete or rate-limited. It does not provide genuine live exchange order-book depth, tick-by-tick trades, or a complete official NSE market breadth feed.")

SECTORS = {
    "Banking": ["HDFCBANK", "ICICIBANK", "SBIN", "AXISBANK", "KOTAKBANK", "INDUSINDBK", "BANKBARODA"],
    "IT": ["TCS", "INFY", "HCLTECH", "WIPRO", "TECHM", "LTIM"],
    "Auto": ["MARUTI", "M&M", "TATAMOTORS", "BAJAJ-AUTO", "EICHERMOT", "HEROMOTOCO"],
    "FMCG": ["ITC", "HINDUNILVR", "NESTLEIND", "TATACONSUM", "BRITANNIA", "DABUR"],
    "Pharma": ["SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB", "APOLLOHOSP", "LUPIN"],
    "Energy": ["RELIANCE", "ONGC", "NTPC", "POWERGRID", "COALINDIA", "IOC"],
    "Metal": ["TATASTEEL", "JSWSTEEL", "HINDALCO", "VEDL", "JINDALSTEL", "NMDC"],
}
INDEXES = {
    "NIFTY 50": "^NSEI",
    "BANK NIFTY": "^NSEBANK",
    "NIFTY IT": "^CNXIT",
    "NIFTY AUTO": "^CNXAUTO",
    "NIFTY FMCG": "^CNXFMCG",
    "NIFTY PHARMA": "^CNXPHARMA",
}
BREADTH_SYMBOLS = list(dict.fromkeys(sum(SECTORS.values(), []) + ["RELIANCE", "LT", "BHARTIARTL", "ADANIENT", "ASIANPAINT", "ULTRACEMCO"]))

@st.cache_data(ttl=180, show_spinner=False)
def history(symbol, period="1mo", interval="1d"):
    ticker = symbol if symbol.startswith("^") else symbol.upper() + ".NS"
    try:
        df = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=False)
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.reset_index()
        tcol = "Datetime" if "Datetime" in df.columns else "Date"
        return df.rename(columns={tcol: "Time"}).dropna(subset=["Close"])
    except Exception:
        return pd.DataFrame()

def pct_change(df):
    if df.empty or len(df) < 2 or not df["Close"].iloc[-2]:
        return None
    return float((df["Close"].iloc[-1] / df["Close"].iloc[-2] - 1) * 100)

def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    rs = gain / loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))

def get_snapshot(symbols, label):
    rows = []
    bar = st.progress(0, text=f"Loading {label}…")
    for i, symbol in enumerate(symbols):
        df = history(symbol, "5d", "1d")
        if not df.empty:
            change = pct_change(df)
            if change is not None:
                rows.append({"Symbol": symbol, "Last": float(df["Close"].iloc[-1]), "Change %": change,
                             "Volume": float(df["Volume"].iloc[-1]) if "Volume" in df else 0})
        bar.progress((i + 1) / len(symbols), text=f"Loading {label}: {symbol}")
    bar.empty()
    return pd.DataFrame(rows)

tab_market, tab_sector, tab_scan = st.tabs(["📍 Market Overview", "🏭 Sector Money Flow", "🔎 Stock Screener"])

with tab_market:
    st.subheader("Major indices")
    cols = st.columns(3)
    for i, (name, ticker) in enumerate(INDEXES.items()):
        df = history(ticker, "5d", "1d")
        if not df.empty:
            change = pct_change(df)
            cols[i % 3].metric(name, f"{df['Close'].iloc[-1]:,.2f}", f"{change:+.2f}%" if change is not None else "—")
        else:
            cols[i % 3].metric(name, "Unavailable", "Yahoo data unavailable")
    st.divider()
    st.subheader("Market breadth snapshot")
    if st.button("Load / refresh market breadth", key="breadth"):
        history.clear()
        breadth = get_snapshot(BREADTH_SYMBOLS, "market breadth")
        if not breadth.empty:
            adv = int((breadth["Change %"] > 0).sum())
            dec = int((breadth["Change %"] < 0).sum())
            unchanged = int((breadth["Change %"] == 0).sum())
            a, b, c, d = st.columns(4)
            a.metric("Advancers", adv)
            b.metric("Decliners", dec)
            c.metric("Unchanged", unchanged)
            d.metric("Advance / decline", f"{adv / dec:.2f}" if dec else "∞")
            ordered = breadth.sort_values("Change %")
            fig = go.Figure(go.Bar(x=ordered["Symbol"], y=ordered["Change %"],
                                   marker_color=["#16a34a" if x >= 0 else "#dc2626" for x in ordered["Change %"]]))
            fig.update_layout(title="Constituent change snapshot (watchlist basket)", yaxis_title="Change %", height=430)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(breadth.sort_values("Change %", ascending=False).style.format(
                {"Last": "₹{:,.2f}", "Change %": "{:+.2f}%", "Volume": "{:,.0f}"}),
                use_container_width=True, hide_index=True)
        else:
            st.warning("Market breadth could not be loaded. Retry later; Yahoo Finance may throttle requests.")
    else:
        st.caption("Tap **Load / refresh market breadth** when you want the constituent snapshot. It is not fetched automatically.");

with tab_sector:
    st.subheader("Sector money-flow approximation")
    st.caption("Sector baskets are representative watchlists, not official index constituents. Flow is approximated from price change and reported volume; it is not institutional net buying.")
    if st.button("Load all sector snapshots", type="primary", key="sectors"):
        sector_rows = []
        for sector, symbols in SECTORS.items():
            snap = get_snapshot(symbols, sector)
            if not snap.empty:
                sector_rows.append({"Sector": sector, "Average change %": snap["Change %"].mean(),
                                    "Advancers": int((snap["Change %"] > 0).sum()),
                                    "Decliners": int((snap["Change %"] < 0).sum()),
                                    "Basket volume": snap["Volume"].sum()})
        if sector_rows:
            result = pd.DataFrame(sector_rows).sort_values("Average change %", ascending=False)
            st.dataframe(result.style.format({"Average change %": "{:+.2f}%", "Basket volume": "{:,.0f}"}),
                         use_container_width=True, hide_index=True)
            fig = go.Figure(go.Bar(x=result["Sector"], y=result["Average change %"],
                                   marker_color=["#16a34a" if v >= 0 else "#dc2626" for v in result["Average change %"]]))
            fig.update_layout(title="Sector basket performance", yaxis_title="Average constituent change %", height=400)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.error("No sector data returned. Try again later.")

with tab_scan:
    st.subheader("Technical watchlist screener")
    symbol_input = st.text_input("NSE symbols (comma separated)", "RELIANCE,TCS,HDFCBANK,INFY,SBIN,ICICIBANK")
    period_choice = st.selectbox("Analysis period", ["1mo", "3mo", "6mo"], index=1)
    if st.button("Run screener", type="primary"):
        symbols = list(dict.fromkeys(s.strip().upper().replace(".NS", "") for s in symbol_input.split(",") if s.strip()))
        rows = []
        progress = st.progress(0)
        for i, symbol in enumerate(symbols):
            df = history(symbol, period_choice, "1d")
            if len(df) >= 20:
                close = df["Close"]
                current = float(close.iloc[-1])
                avg20 = float(close.rolling(20).mean().iloc[-1])
                rsi_now = float(rsi(close).iloc[-1]) if pd.notna(rsi(close).iloc[-1]) else None
                ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
                ema50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
                macd = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
                signal = macd.ewm(span=9, adjust=False).mean()
                rows.append({"Symbol": symbol, "Price": current, "RSI 14": rsi_now,
                             "EMA20": ema20, "EMA50": ema50,
                             "MACD": float(macd.iloc[-1]), "MACD signal": float(signal.iloc[-1]),
                             "Trend": "Bullish" if current > ema20 > ema50 else "Bearish" if current < ema20 < ema50 else "Mixed"})
            progress.progress((i + 1) / max(len(symbols), 1))
        progress.empty()
        if rows:
            result = pd.DataFrame(rows)
            st.dataframe(result.style.format({"Price": "₹{:,.2f}", "RSI 14": "{:.1f}",
                "EMA20": "₹{:,.2f}", "EMA50": "₹{:,.2f}", "MACD": "{:.2f}", "MACD signal": "{:.2f}"}),
                use_container_width=True, hide_index=True)
            st.caption("RSI, EMA and MACD are calculated from daily closes. They are screening indicators, not guaranteed entry signals.")
        else:
            st.warning("No usable history found for these symbols. Check NSE symbols and retry.")

with st.expander("Data definitions and limitations"):
    st.markdown("""
    - **Market breadth:** advancing/declining counts across the displayed representative watchlist, not all NSE-listed stocks.
    - **Sector flow:** average constituent price change and reported volume; not exchange-reported sector fund flow or institutional activity.
    - **RSI / EMA / MACD:** standard calculations on daily closing prices.
    - **No options/OI walls or Level-2 depth:** these require a reliable options-chain and broker/exchange market-data source. This free version intentionally does not fabricate them.
    - **No trade execution:** this dashboard is for research and paper-trading workflows only.
    """)
st.caption(f"Servejit Market Pulse · Yahoo Finance · Rendered {datetime.now().strftime('%d %b %Y %H:%M:%S')}")
