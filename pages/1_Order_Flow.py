import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

st.set_page_config(page_title="Order Flow | Servejit", page_icon="📊", layout="wide")

st.title("📊 NSE Order Flow & Liquidity")
st.caption("A Tredye Pulse-style analysis dashboard. Uses Yahoo Finance OHLCV data; it is not an exchange Level-2 order book.")

st.info(
    "Data limitation: free Yahoo Finance data does not provide genuine bid/ask depth, "
    "individual market orders, or buyer/seller-initiated trade flags. Buying/selling pressure, "
    "volume profile and order-block zones below are candle/volume-based estimates—not actual order flow."
)

SECTORS = {
    "NIFTY 50": ["RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS", "ITC", "LT", "SBIN", "BHARTIARTL", "AXISBANK"],
    "Banking": ["HDFCBANK", "ICICIBANK", "SBIN", "AXISBANK", "KOTAKBANK", "INDUSINDBK", "BANKBARODA"],
    "IT": ["TCS", "INFY", "HCLTECH", "WIPRO", "TECHM", "LTIM"],
    "Auto": ["MARUTI", "M&M", "TATAMOTORS", "BAJAJ-AUTO", "EICHERMOT", "HEROMOTOCO"],
    "FMCG": ["ITC", "HINDUNILVR", "NESTLEIND", "TATACONSUM", "BRITANNIA", "DABUR"],
    "Pharma": ["SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB", "APOLLOHOSP", "LUPIN"],
    "Energy": ["RELIANCE", "ONGC", "NTPC", "POWERGRID", "COALINDIA", "IOC"],
    "Metal": ["TATASTEEL", "JSWSTEEL", "HINDALCO", "VEDL", "JINDALSTEL", "NMDC"],
}

INTERVALS = {
    "1 minute": ("1m", "1d"),
    "5 minutes": ("5m", "5d"),
    "15 minutes": ("15m", "1mo"),
    "30 minutes": ("30m", "1mo"),
    "1 hour": ("60m", "3mo"),
    "1 day": ("1d", "1y"),
}

@st.cache_data(ttl=45, show_spinner=False)
def load_history(symbol, interval, period):
    ticker = symbol.strip().upper()
    if not ticker.endswith(".NS"):
        ticker += ".NS"
    data = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=False)
    if data is None or data.empty:
        return pd.DataFrame()
    data = data.reset_index()
    time_col = "Datetime" if "Datetime" in data.columns else "Date"
    data = data.rename(columns={time_col: "Time"})
    data = data.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
    return data

def add_indicators(df):
    d = df.copy()
    d["Typical"] = (d["High"] + d["Low"] + d["Close"]) / 3
    d["AvgVol"] = d["Volume"].rolling(20, min_periods=5).mean()
    candle_range = (d["High"] - d["Low"]).replace(0, pd.NA)
    d["ClosePosition"] = ((d["Close"] - d["Low"]) / candle_range).fillna(0.5)
    d["BuyPressure"] = d["Volume"] * d["ClosePosition"]
    d["SellPressure"] = d["Volume"] * (1 - d["ClosePosition"])
    d["NetPressure"] = d["BuyPressure"] - d["SellPressure"]
    d["RelativeVolume"] = d["Volume"] / d["AvgVol"].replace(0, pd.NA)
    return d

def fmt_num(value):
    if pd.isna(value):
        return "—"
    return f"{value:,.0f}"

def build_profile(df, bins=24):
    low, high = float(df["Low"].min()), float(df["High"].max())
    if low == high:
        return pd.DataFrame()
    edges = pd.Series(pd.cut(df["Typical"], bins=bins, retbins=True)[1])
    labels = pd.cut(df["Typical"], bins=edges, include_lowest=True)
    profile = df.assign(Bin=labels).groupby("Bin", observed=False)["Volume"].sum().reset_index()
    profile["Price"] = profile["Bin"].apply(lambda x: (x.left + x.right) / 2 if pd.notna(x) else None)
    return profile.dropna(subset=["Price"]).sort_values("Price")

def find_zones(df):
    d = df.copy()
    d["VolAvg"] = d["Volume"].rolling(20, min_periods=5).mean()
    d["HighVol"] = d["Volume"] > d["VolAvg"] * 1.5
    zones = []
    for _, row in d[d["HighVol"]].tail(12).iterrows():
        direction = "Bullish demand (estimated)" if row["Close"] > row["Open"] else "Bearish supply (estimated)"
        zones.append({
            "Time": row["Time"],
            "Type": direction,
            "Low": float(row["Low"]),
            "High": float(row["High"]),
            "Volume": float(row["Volume"]),
        })
    return pd.DataFrame(zones)

def chart_candles(df, symbol, profile):
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.04,
                        row_heights=[0.72, 0.28])
    fig.add_trace(go.Candlestick(
        x=df["Time"], open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
        name="Price"
    ), row=1, col=1)
    if not profile.empty:
        max_vol = profile["Volume"].max()
        for _, zone in profile.nlargest(3, "Volume").iterrows():
            fig.add_hline(y=zone["Price"], line_dash="dot", opacity=0.55,
                          annotation_text="High-volume node", row=1, col=1)
    colors = ["#16a34a" if c >= o else "#dc2626" for o, c in zip(df["Open"], df["Close"])]
    fig.add_trace(go.Bar(x=df["Time"], y=df["Volume"], marker_color=colors, name="Volume"), row=2, col=1)
    fig.update_layout(height=650, title=f"{symbol} · Price and volume", xaxis_rangeslider_visible=False,
                      margin=dict(l=10, r=10, t=55, b=10), legend_orientation="h")
    return fig

def render_stock_view():
    left, right = st.columns([2, 1])
    with left:
        symbol = st.text_input("NSE symbol", value="RELIANCE", help="Enter a symbol without .NS, for example TCS or SBIN.")
    with right:
        interval_label = st.selectbox("Timeframe", list(INTERVALS.keys()), index=1)
    interval, period = INTERVALS[interval_label]
    if st.button("↻ Refresh data", type="primary"):
        load_history.clear()
    with st.spinner(f"Loading {symbol.upper()} market data…"):
        raw = load_history(symbol, interval, period)
    if raw.empty:
        st.error("No data returned. Check the NSE symbol, try another timeframe, or retry later.")
        return
    df = add_indicators(raw)
    latest = df.iloc[-1]
    previous = df.iloc[-2] if len(df) > 1 else latest
    change = float(latest["Close"] - previous["Close"])
    pct = (change / previous["Close"] * 100) if previous["Close"] else 0
    buy = float(df["BuyPressure"].sum())
    sell = float(df["SellPressure"].sum())
    net = buy - sell
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Last price", f"₹{latest['Close']:,.2f}", f"{change:+.2f} ({pct:+.2f}%)")
    c2.metric("Candle volume", fmt_num(latest["Volume"]))
    c3.metric("Estimated buy pressure", fmt_num(buy))
    c4.metric("Estimated sell pressure", fmt_num(sell))
    c5.metric("Net pressure", fmt_num(net), "Buy-side" if net >= 0 else "Sell-side")
    profile = build_profile(df)
    st.plotly_chart(chart_candles(df, symbol.upper(), profile), use_container_width=True)
    a, b = st.columns(2)
    with a:
        st.subheader("Volume profile by price")
        if profile.empty:
            st.caption("Not enough price variation to build a profile.")
        else:
            fig = go.Figure(go.Bar(x=profile["Volume"], y=profile["Price"], orientation="h",
                                   name="Volume at price"))
            fig.update_layout(height=420, xaxis_title="Volume", yaxis_title="Price (₹)",
                              margin=dict(l=10, r=10, t=20, b=10))
            st.plotly_chart(fig, use_container_width=True)
            poc = profile.loc[profile["Volume"].idxmax()]
            st.metric("Point of control (estimated)", f"₹{poc['Price']:,.2f}")
    with b:
        st.subheader("Buying vs selling pressure")
        pressure = pd.DataFrame({"Side": ["Buy estimate", "Sell estimate"], "Volume": [buy, sell]})
        fig = go.Figure(go.Bar(x=pressure["Side"], y=pressure["Volume"], text=pressure["Volume"].map(fmt_num),
                               textposition="auto"))
        fig.update_layout(height=420, showlegend=False, yaxis_title="Estimated volume")
        st.plotly_chart(fig, use_container_width=True)
    st.subheader("High-volume zones / estimated order blocks")
    zones = find_zones(df)
    if zones.empty:
        st.caption("No high-volume candles found in the selected period.")
    else:
        zones["Time"] = pd.to_datetime(zones["Time"]).dt.strftime("%d %b %H:%M")
        zones["Price zone"] = zones.apply(lambda r: f"₹{r['Low']:,.2f} – ₹{r['High']:,.2f}", axis=1)
        st.dataframe(zones[["Time", "Type", "Price zone", "Volume"]].sort_values("Time", ascending=False),
                     use_container_width=True, hide_index=True)
    st.subheader("Market depth")
    st.warning("Actual bid/ask quantities and Level-2 depth are not supplied by this free data source. Connect a supported broker market-data feed to enable genuine depth.")

def render_sector_view():
    sector = st.selectbox("Choose sector basket", list(SECTORS.keys()))
    symbols = SECTORS[sector]
    st.caption("Starter watchlist basket. This is not an official live index constituent list.")
    if st.button("Load sector snapshot", type="primary"):
        rows = []
        progress = st.progress(0)
        for i, symbol in enumerate(symbols):
            try:
                data = load_history(symbol, "5m", "5d")
                if not data.empty and len(data) >= 2:
                    last, prev = data.iloc[-1], data.iloc[-2]
                    pct = (last["Close"] / prev["Close"] - 1) * 100 if prev["Close"] else 0
                    rows.append({"Symbol": symbol, "Price": last["Close"], "Change %": pct,
                                 "Volume": last["Volume"]})
            except Exception:
                pass
            progress.progress((i + 1) / len(symbols))
        progress.empty()
        if rows:
            result = pd.DataFrame(rows).sort_values("Change %", ascending=False)
            st.dataframe(result.style.format({"Price": "₹{:,.2f}", "Change %": "{:+.2f}%", "Volume": "{:,.0f}"}),
                         use_container_width=True, hide_index=True)
            adv = int((result["Change %"] > 0).sum())
            dec = int((result["Change %"] < 0).sum())
            x, y, z = st.columns(3)
            x.metric("Advancing", adv)
            y.metric("Declining", dec)
            z.metric("Average change", f"{result['Change %'].mean():+.2f}%")
            fig = go.Figure(go.Bar(x=result["Symbol"], y=result["Change %"],
                                   marker_color=["#16a34a" if v >= 0 else "#dc2626" for v in result["Change %"]]))
            fig.update_layout(title=f"{sector} · constituent snapshot", yaxis_title="Change %", height=380)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.error("Could not load this sector snapshot. Yahoo Finance may be rate-limiting requests.")

tab1, tab2 = st.tabs(["📈 Stock Order Flow", "🏭 Sector Flow"])
with tab1:
    render_stock_view()
with tab2:
    render_sector_view()

with st.expander("How to interpret this dashboard"):
    st.markdown("""
    - **Estimated buy/sell pressure:** candle volume weighted by where the close sits between that candle's low and high.
    - **Volume profile:** distributes observed candle volume across approximate price bins; it is not exchange-by-exchange traded volume at price.
    - **High-volume zones:** candles with volume above 1.5× their rolling 20-candle average. These are candidate zones, not guaranteed institutional order blocks.
    - **Market depth:** requires a broker or exchange Level-2 feed and is intentionally not fabricated here.
    """)
st.caption(f"Servejit · Data fetched from Yahoo Finance · Last page render: {datetime.now().strftime('%d %b %Y, %H:%M:%S')}")
