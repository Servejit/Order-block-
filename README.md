# NSE Intraday Reversal Scanner & Market Dashboards

A Streamlit application for NSE market research. The original scanner and portfolio app remain in `app.py`; additional dashboards are available in the Streamlit sidebar.

## Pages

### 1. Original app — `app.py`
The existing NIFTY 200 intraday reversal scanner and portfolio/watchlist workflow are preserved.

### 2. Order Flow — `pages/1_Order_Flow.py`
- Stock candlestick and volume charts with timeframe selection.
- Estimated buying/selling pressure from candle volume.
- Approximate volume profile and point of control.
- High-volume candidate demand/supply zones.
- Rule-based BUY / SELL / WAIT decision with indicative entry, target and stop-loss levels.
- Sector basket snapshots.
- Market-depth section clearly explains the absence of genuine Level-2 data.

### 3. Market Pulse — `pages/2_Market_Pulse.py`
- NIFTY 50, BANK NIFTY and selected sector index snapshots.
- Advancing/declining watchlist breadth.
- Sector basket performance and approximate money-flow view.
- Daily RSI, EMA20/EMA50 and MACD watchlist screener.

## Data and accuracy limitations

This is an independent implementation inspired by publicly described market-dashboard features. It does not copy Tredye's private source code, backend, data pipeline, or proprietary calculations.

The free version uses Yahoo Finance through `yfinance`. Data can be delayed, incomplete, throttled, sampled or unavailable. Yahoo Finance does not provide genuine exchange Level-2 bid/ask depth, buyer/seller-initiated trade flags, full options-chain/OI walls, or a guaranteed real-time NSE feed. The dashboards therefore label candle-derived pressure, volume profile, sector flow and zones as estimates and do not fabricate missing order-book or options data.

Sector and breadth baskets are representative watchlists, not official exhaustive NSE constituent lists. The BUY / SELL / WAIT panel is a simple educational rule set, not a recommendation or guaranteed prediction. Confirm all prices and signals with your broker before making decisions.

No broker orders are placed by this application.

## Run locally or in GitHub Codespaces

```bash
pip install -r requirements.txt
streamlit run app.py
```

Forward port **8501** in Codespaces and open the forwarded URL. Use the sidebar to switch between the original app, Order Flow and Market Pulse pages.
