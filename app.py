import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
import yfinance as yf

IST = ZoneInfo("Asia/Kolkata")
PORTFOLIO_FILE = Path("portfolio.json")
DEFAULT_STOCKS = ["ICICIBANK", "HINDUNILVR"]

st.set_page_config(
    page_title="My NSE Portfolio",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.block-container {padding-top: 1.5rem; padding-bottom: 2rem;}
[data-testid="stMetric"] {
    background: var(--secondary-background-color);
    border: 1px solid rgba(128,128,128,.16);
    padding: 14px 16px;
    border-radius: 12px;
}
div[data-testid="stDataFrame"] {
    border: 1px solid rgba(128,128,128,.18);
    border-radius: 10px;
}
</style>
""", unsafe_allow_html=True)


def load_portfolio():
    try:
        if PORTFOLIO_FILE.exists():
            data = json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                cleaned = []
                for value in data:
                    symbol = str(value).strip().upper().replace(".NS", "")
                    if symbol and symbol not in cleaned:
                        cleaned.append(symbol)
                return cleaned
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return DEFAULT_STOCKS.copy()


def save_portfolio(symbols):
    PORTFOLIO_FILE.write_text(
        json.dumps(symbols, indent=2),
        encoding="utf-8",
    )


if "portfolio_symbols" not in st.session_state:
    st.session_state.portfolio_symbols = load_portfolio()

st.title("📊 My NSE Portfolio")
st.caption("Your personal NSE watchlist with frequent price updates and movement highlighting.")

with st.sidebar:
    st.header("Manage portfolio")
    with st.form("add_stock_form", clear_on_submit=True):
        stock_input = st.text_input(
            "Add NSE symbol(s)",
            placeholder="ICICIBANK, HINDUNILVR, RELIANCE",
            help="Enter NSE trading symbols separated by commas or new lines.",
        )
        add_clicked = st.form_submit_button(
            "＋ Add stock",
            use_container_width=True,
            type="primary",
        )

    if add_clicked:
        additions = []
        existing = st.session_state.portfolio_symbols.copy()
        for raw in stock_input.replace(";", ",").replace("\n", ",").split(","):
            symbol = raw.strip().upper().replace(".NS", "")
            if symbol and symbol.replace("-", "").replace("&", "").isalnum():
                if symbol not in existing:
                    existing.append(symbol)
                    additions.append(symbol)
        if additions:
            st.session_state.portfolio_symbols = existing
            save_portfolio(existing)
            st.success("Added: " + ", ".join(additions))
        elif stock_input.strip():
            st.info("No new valid symbols to add.")

    current_symbols = st.session_state.portfolio_symbols
    if current_symbols:
        st.caption("Stocks in your portfolio")
        st.write(", ".join(current_symbols))
        remove_choice = st.selectbox(
            "Select stock to remove",
            ["Select…"] + current_symbols,
            key="remove_stock_choice",
        )
        if st.button(
            "Remove selected stock",
            use_container_width=True,
            disabled=remove_choice == "Select…",
        ):
            updated = [s for s in current_symbols if s != remove_choice]
            st.session_state.portfolio_symbols = updated
            save_portfolio(updated)
            st.rerun()

    st.divider()
    refresh_seconds = st.selectbox(
        "Live price check",
        [0, 10, 15, 30, 60],
        index=1,
        format_func=lambda value: "Off" if value == 0 else f"Every {value} seconds",
    )
    refresh_now = st.button("↻ Refresh prices now", use_container_width=True)
    st.caption("Data: Yahoo Finance · NSE symbols use the .NS suffix")

if refresh_seconds:
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=refresh_seconds * 1000, key="portfolio_auto_refresh")
    except ImportError:
        st.sidebar.warning("Install streamlit-autorefresh to enable automatic refresh.")


@st.cache_data(ttl=8, show_spinner=False)
def fetch_stock_history(symbol):
    ticker = symbol + ".NS"
    data = yf.download(
        ticker,
        period="5d",
        interval="1m",
        progress=False,
        auto_adjust=False,
        threads=False,
        timeout=15,
    )
    if data is None or data.empty:
        return pd.DataFrame()

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    required = ["Open", "High", "Low", "Close", "Volume"]
    if any(column not in data.columns for column in required):
        return pd.DataFrame()

    data = data[required].dropna(subset=["Open", "High", "Low", "Close"]).copy()
    index = pd.to_datetime(data.index)
    if index.tz is None:
        index = index.tz_localize("UTC")
    data.index = index.tz_convert(IST)
    return data[~data.index.duplicated(keep="last")].sort_index()


def build_portfolio_row(symbol):
    try:
        history = fetch_stock_history(symbol)
        if history.empty:
            raise ValueError("No price data returned")

        trading_dates = sorted(set(history.index.date))
        latest_date = trading_dates[-1]
        latest_day = history[history.index.date == latest_date]
        previous_day = (
            history[history.index.date == trading_dates[-2]]
            if len(trading_dates) > 1
            else pd.DataFrame()
        )

        last_price = float(latest_day["Close"].iloc[-1])
        previous_close = (
            float(previous_day["Close"].iloc[-1])
            if not previous_day.empty
            else float("nan")
        )
        change = last_price - previous_close if pd.notna(previous_close) else float("nan")
        change_pct = (
            change / previous_close * 100
            if pd.notna(previous_close) and previous_close
            else float("nan")
        )

        return {
            "Symbol": symbol,
            "Open": float(latest_day["Open"].iloc[0]),
            "High": float(latest_day["High"].max()),
            "Low": float(latest_day["Low"].min()),
            "Last Price": last_price,
            "Previous Close": previous_close,
            "Change": change,
            "Change %": change_pct,
            "Volume": int(latest_day["Volume"].fillna(0).sum()),
            "Last Updated (IST)": latest_day.index[-1].strftime("%d %b %H:%M:%S"),
            "Status": "OK",
        }
    except Exception as error:
        return {
            "Symbol": symbol,
            "Open": None,
            "High": None,
            "Low": None,
            "Last Price": None,
            "Previous Close": None,
            "Change": None,
            "Change %": None,
            "Volume": None,
            "Last Updated (IST)": "—",
            "Status": "Data unavailable",
        }


symbols = st.session_state.portfolio_symbols

if not symbols:
    st.info("Your portfolio is empty. Add NSE symbols from the sidebar to get started.")
    st.stop()

if refresh_now:
    fetch_stock_history.clear()

with st.spinner("Fetching the latest available prices for your portfolio…"):
    rows = [build_portfolio_row(symbol) for symbol in symbols]

portfolio = pd.DataFrame(rows)
valid = portfolio[portfolio["Status"] == "OK"].copy()

# Rank only positive stocks as gainers and negative stocks as losers.
# A group signal requires exactly three ranked stocks and all three must qualify.
valid["Change %"] = pd.to_numeric(valid["Change %"], errors="coerce")
valid["High"] = pd.to_numeric(valid["High"], errors="coerce")
valid["Low"] = pd.to_numeric(valid["Low"], errors="coerce")
valid["Last Price"] = pd.to_numeric(valid["Last Price"], errors="coerce")

gainers = valid[valid["Change %"] > 0].nlargest(3, "Change %").copy()
losers = valid[valid["Change %"] < 0].nsmallest(3, "Change %").copy()

if not gainers.empty:
    gainers["Below High %"] = ((gainers["High"] - gainers["Last Price"]) / gainers["High"]) * 100
if not losers.empty:
    losers["Above Low %"] = ((losers["Last Price"] - losers["Low"]) / losers["Low"]) * 100

buy_signal = len(gainers) == 3 and bool((gainers["Below High %"] >= 0.50).all())
sell_signal = len(losers) == 3 and bool((losers["Above Low %"] >= 0.50).all())

# Alert only when a complete three-stock group first becomes true.
if "previous_group_signals" not in st.session_state:
    st.session_state.previous_group_signals = {"BUY": False, "SELL": False}
if "alert_trigger_id" not in st.session_state:
    st.session_state.alert_trigger_id = 0

new_alerts = []
if buy_signal and not st.session_state.previous_group_signals["BUY"]:
    new_alerts.append("BUY")
if sell_signal and not st.session_state.previous_group_signals["SELL"]:
    new_alerts.append("SELL")
if new_alerts:
    st.session_state.alert_trigger_id += 1
st.session_state.previous_group_signals = {"BUY": buy_signal, "SELL": sell_signal}

st.subheader("🔔 Three-stock group alerts")
buy_col, sell_col = st.columns(2)
with buy_col:
    if buy_signal:
        st.success("🟢 BUY SIGNAL — all top 3 gainers are at least 0.50% below their day highs.")
    else:
        st.info("BUY alarm OFF — all 3 top gainers have not met the condition.")
with sell_col:
    if sell_signal:
        st.error("🔴 SELL SIGNAL — all bottom 3 losers are at least 0.50% above their day lows.")
    else:
        st.info("SELL alarm OFF — all 3 bottom losers have not met the condition.")

detail_col1, detail_col2 = st.columns(2)
with detail_col1:
    st.markdown("**Top 3 % gainers — BUY group**")
    if len(gainers) == 3:
        st.dataframe(
            gainers[["Symbol", "Change %", "High", "Last Price", "Below High %"]].style.format(
                {"Change %": "{:.2f}%", "High": "₹{:.2f}", "Last Price": "₹{:.2f}", "Below High %": "{:.2f}%"}
            ),
            use_container_width=True, hide_index=True,
        )
        st.caption("All three must show Below High % ≥ 0.50% to activate BUY.")
    else:
        st.caption(f"Need 3 positive % gainers; currently found {len(gainers)}.")

with detail_col2:
    st.markdown("**Bottom 3 % losers — SELL group**")
    if len(losers) == 3:
        st.dataframe(
            losers[["Symbol", "Change %", "Low", "Last Price", "Above Low %"]].style.format(
                {"Change %": "{:.2f}%", "Low": "₹{:.2f}", "Last Price": "₹{:.2f}", "Above Low %": "{:.2f}%"}
            ),
            use_container_width=True, hide_index=True,
        )
        st.caption("All three must show Above Low % ≥ 0.50% to activate SELL.")
    else:
        st.caption(f"Need 3 negative % losers; currently found {len(losers)}.")

# Browser sound is enabled by the user's click inside the sound control.
# Browsers may block automatic audio until the user explicitly enables it.
import streamlit.components.v1 as components
sound_trigger = st.session_state.alert_trigger_id
any_signal_active = buy_signal or sell_signal
sound_html = """
<div style="font-family: sans-serif; display:flex; align-items:center; gap:12px; flex-wrap:wrap;">
  <button id="sound-enable" style="padding:9px 14px;border:1px solid #888;border-radius:8px;background:#f3f4f6;color:#111;cursor:pointer;">
    Enable sound alarm
  </button>
  <span id="sound-status" style="font-size:13px;color:inherit;">Sound is off until enabled.</span>
</div>
<script>
(() => {
  const key = "nse_portfolio_sound_enabled";
  const trigger = Number("__TRIGGER__");
  const active = "__ACTIVE__" === "true";
  let audioContext;
  function beep() {
    try {
      audioContext = audioContext || new (window.AudioContext || window.webkitAudioContext)();
      if (audioContext.state === "suspended") audioContext.resume();
      const now = audioContext.currentTime;
      [0, 0.28, 0.56].forEach((offset, index) => {
        const oscillator = audioContext.createOscillator();
        const gain = audioContext.createGain();
        oscillator.type = "sine";
        oscillator.frequency.value = index === 1 ? 880 : 660;
        gain.gain.setValueAtTime(0.0001, now + offset);
        gain.gain.exponentialRampToValueAtTime(0.22, now + offset + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + offset + 0.18);
        oscillator.connect(gain);
        gain.connect(audioContext.destination);
        oscillator.start(now + offset);
        oscillator.stop(now + offset + 0.2);
      });
    } catch (e) {}
  }
  const button = document.getElementById("sound-enable");
  const status = document.getElementById("sound-status");
  if (localStorage.getItem(key) === "1") {
    button.textContent = "Sound enabled";
    status.textContent = "Sound alarm is enabled in this browser.";
    if (trigger > 0 && localStorage.getItem("nse_portfolio_last_sound_trigger") !== String(trigger)) {
      localStorage.setItem("nse_portfolio_last_sound_trigger", String(trigger));
      if (active) beep();
    }
  }
  button.addEventListener("click", () => {
    localStorage.setItem(key, "1");
    button.textContent = "Sound enabled";
    status.textContent = "Sound alarm enabled.";
    if (active) beep();
  });
})();
</script>
""".replace("__TRIGGER__", str(sound_trigger)).replace("__ACTIVE__", str(any_signal_active).lower())
components.html(sound_html, height=48)
st.caption("Keep this dashboard open for alarms. Sound may require browser permission; alarms trigger once when a group first qualifies, not on every refresh.")

last_updated = datetime.now(IST).strftime("%d %b %Y, %I:%M:%S %p IST")

# Compare each latest price with the previous app refresh to show the direction
# of the most recent observed move (rather than only today's gain/loss).
if "previous_live_prices" not in st.session_state:
    st.session_state.previous_live_prices = {}

movement_labels = {}
for row in rows:
    symbol = row["Symbol"]
    price = row["Last Price"]
    previous_price = st.session_state.previous_live_prices.get(symbol)
    if price is None or pd.isna(price):
        movement_labels[symbol] = "—"
    elif previous_price is None:
        movement_labels[symbol] = "•"
    elif price > previous_price:
        movement_labels[symbol] = "▲ UP"
    elif price < previous_price:
        movement_labels[symbol] = "▼ DOWN"
    else:
        movement_labels[symbol] = "—"
portfolio["Move"] = portfolio["Symbol"].map(movement_labels)
for row in rows:
    if row["Last Price"] is not None and pd.notna(row["Last Price"]):
        st.session_state.previous_live_prices[row["Symbol"]] = row["Last Price"]

total_stocks = len(symbols)
available_stocks = len(valid)
advancers = int((valid["Change"] > 0).sum()) if not valid.empty else 0
decliners = int((valid["Change"] < 0).sum()) if not valid.empty else 0

metric1, metric2, metric3, metric4 = st.columns(4)
metric1.metric("Portfolio stocks", total_stocks)
metric2.metric("Prices available", available_stocks)
metric3.metric("Advancers", advancers)
metric4.metric("Decliners", decliners)

st.subheader("Portfolio overview")
st.caption(f"Last price check: {last_updated} · Data refreshes from Yahoo Finance; price candles are 1-minute data.")

display_columns = [
    "Symbol", "Open", "High", "Low", "Last Price",
    "Previous Close", "Change", "Change %", "Volume",
    "Last Updated (IST)", "Move", "Status",
]
def movement_row_style(row):
    direction = row.get("Move", "—")
    if direction == "▲ UP":
        return ["background-color: #d9fbe5; color: #14532d;"] * len(row)
    if direction == "▼ DOWN":
        return ["background-color: #fee2e2; color: #7f1d1d;"] * len(row)
    return [""] * len(row)


styled_portfolio = portfolio[display_columns].style.apply(movement_row_style, axis=1)
st.dataframe(
    styled_portfolio,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Open": st.column_config.NumberColumn("Open", format="₹%.2f"),
        "High": st.column_config.NumberColumn("High", format="₹%.2f"),
        "Low": st.column_config.NumberColumn("Low", format="₹%.2f"),
        "Last Price": st.column_config.NumberColumn("Last Price", format="₹%.2f"),
        "Previous Close": st.column_config.NumberColumn("Previous Close", format="₹%.2f"),
        "Change": st.column_config.NumberColumn("Change", format="₹%.2f"),
        "Change %": st.column_config.NumberColumn("Change %", format="%.2f%%"),
        "Volume": st.column_config.NumberColumn("Volume", format="%d"),
    },
)

if not valid.empty:
    st.subheader("Price movement")
    chart_symbols = valid["Symbol"].tolist()
    selected_symbol = st.selectbox("Choose a stock", chart_symbols)
    chart_history = fetch_stock_history(selected_symbol)
    if not chart_history.empty:
        latest_date = sorted(set(chart_history.index.date))[-1]
        chart_day = chart_history[chart_history.index.date == latest_date]
        st.line_chart(chart_day["Close"], height=280, use_container_width=True)

st.caption(
    "Prices and OHLC values are based on Yahoo Finance 1-minute candles, checked on the selected refresh interval. "
    "Yahoo Finance is not a guaranteed live NSE tick feed; prices may be delayed, incomplete, or throttled. "
    "This dashboard is for tracking only; verify prices with your broker before trading."
)
