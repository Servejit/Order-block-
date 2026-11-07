# NIFTY 200 Intraday Reversal Scanner

A Streamlit scanner for NIFTY 200 stocks using a daily sweep/reclaim, 1-hour sweep/reclaim, and 5-minute reclaim trigger.

## Signal rules

1. Today's low is below the previous trading day's low, while the latest price is back above the previous day's low.
2. The currently forming session-hour candle's low is below the previous completed session-hour candle's low, while price is above that previous hour's low.
3. The latest 5-minute candle closes above the current session-hour low after the previous 5-minute close was at or below it.
4. The latest 5-minute candle's high must remain below the current session-hour high.
5. The target reference is the lowest low among today's bearish (red) 1-hour candles.

Hourly candles are assembled from 5-minute candles and aligned to the NSE session open (09:15 IST).

## Order Flow dashboard

A separate **Order Flow** page is available from the Streamlit sidebar. It adds:
- Stock price and volume chart with timeframe selection.
- Estimated buying/selling pressure derived from candle volume.
- Approximate volume profile and point of control.
- High-volume candidate demand/supply zones.
- Starter sector baskets for quick relative-strength snapshots.

The original scanner and portfolio app in `app.py` are kept separate and are not replaced.

**Important data limitation:** Yahoo Finance does not provide genuine exchange Level-2 bid/ask depth or buyer/seller-initiated trade flags. Order-flow pressure and zones on this page are estimates from OHLCV candles, not actual order-book data. The Market Depth panel therefore does not invent bid/ask quantities. A supported broker/exchange market-data feed is required for true depth.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Data limitations

The app uses Yahoo Finance through yfinance and the official Nifty Indices constituent CSV. Yahoo Finance is not an official NSE real-time feed; intraday prices may be delayed, incomplete, throttled, or unavailable. Confirm all values on your broker's chart. This app is for research and paper-trading workflows only and does not place orders.

## GitHub Codespaces

Create a Codespace, then run the commands above in its terminal. Forward port 8501 and open the forwarded URL.
