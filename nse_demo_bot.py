# AI-style NSE Paper Trading Bot (DEMO ONLY)
# Historical-data simulator. It does NOT place real broker orders.
# Install: pip install streamlit yfinance pandas
# Run: streamlit run nse_demo_bot.py

import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import date

st.set_page_config(page_title="NSE AI Paper Trading Bot", page_icon="📈", layout="wide")
st.title("🇮🇳 NSE AI Paper Trading Bot — DEMO")
st.warning("DEMO ONLY: This app simulates trades on historical/delayed Yahoo Finance data. It never connects to a broker or places real orders. Profits are not guaranteed.")

with st.sidebar:
    st.header("Bot Settings")
    symbol = st.text_input("NSE symbol", "RELIANCE").strip().upper()
    start_cash = st.number_input("Virtual capital (₹)", min_value=1000, max_value=10000000, value=100000, step=5000)
    fast = st.number_input("Fast SMA", min_value=2, max_value=50, value=10)
    slow = st.number_input("Slow SMA", min_value=5, max_value=200, value=30)
    stop_pct = st.slider("Stop loss (%)", 0.5, 10.0, 2.0, 0.5)
    target_pct = st.slider("Take profit (%)", 1.0, 20.0, 4.0, 0.5)
    risk_pct = st.slider("Max capital per trade (%)", 1, 25, 10)
    max_loss_pct = st.slider("Stop opening new trades after total loss (%)", 0.5, 20.0, 5.0, 0.5)
    period = st.selectbox("Historical period", ["6mo", "1y", "2y", "5y"], index=1)

if fast >= slow:
    st.error("Fast SMA must be smaller than Slow SMA.")
    st.stop()

ticker = symbol if symbol.endswith(".NS") else symbol + ".NS"

@st.cache_data(ttl=300)
def load_data(ticker_symbol, history):
    df = yf.download(ticker_symbol, period=history, interval="1d", auto_adjust=True, progress=False)
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.dropna()

with st.spinner("Fetching historical NSE data..."):
    data = load_data(ticker, period)

if data.empty or "Close" not in data.columns:
    st.error(f"Could not fetch data for {ticker}. Check the symbol (examples: RELIANCE, TCS, INFY, HDFCBANK) or try again later.")
    st.stop()

data = data.copy()
data["Fast_SMA"] = data["Close"].rolling(int(fast)).mean()
data["Slow_SMA"] = data["Close"].rolling(int(slow)).mean()
data = data.dropna().copy()
if len(data) < 3:
    st.error("Not enough history for these moving averages.")
    st.stop()

# Long-only, one-position-at-a-time historical paper simulation.
cash = float(start_cash)
qty = 0
entry = None
entry_date = None
equity_at_day_start = cash
current_day = None
trades = []
equity_curve = []

for idx, row in data.iterrows():
    day = idx.date() if hasattr(idx, "date") else idx
    close = float(row["Close"])
    fast_now = float(row["Fast_SMA"])
    slow_now = float(row["Slow_SMA"])

    if current_day != day:
        current_day = day
        equity_at_day_start = cash + qty * close

    # Portfolio loss lock: stop opening new trades after total equity falls
    # below starting capital by the configured threshold. Existing positions
    # can still exit by stop loss or take profit.

    # Risk exits are evaluated before new entry signals.
    if qty > 0 and entry is not None:
        if close <= entry * (1 - stop_pct / 100):
            cash += qty * close
            trades.append({"Date": str(day), "Action": "STOP LOSS SELL", "Price": close, "Qty": qty,
                           "P/L (₹)": (close - entry) * qty})
            qty, entry, entry_date = 0, None, None
        elif close >= entry * (1 + target_pct / 100):
            cash += qty * close
            trades.append({"Date": str(day), "Action": "TAKE PROFIT SELL", "Price": close, "Qty": qty,
                           "P/L (₹)": (close - entry) * qty})
            qty, entry, entry_date = 0, None, None

    # SMA crossover signal (based on completed daily close).
    if qty == 0 and (cash + qty * close) > float(start_cash) * (1 - max_loss_pct / 100):
        prev = data.loc[:idx].iloc[-2] if len(data.loc[:idx]) >= 2 else None
        crossed_up = prev is not None and float(prev["Fast_SMA"]) <= float(prev["Slow_SMA"]) and fast_now > slow_now
        if crossed_up:
            allocation = min(cash, start_cash * risk_pct / 100)
            buy_qty = int(allocation // close)
            if buy_qty > 0:
                cost = buy_qty * close
                cash -= cost
                qty = buy_qty
                entry = close
                entry_date = day
                trades.append({"Date": str(day), "Action": "BUY", "Price": close, "Qty": qty, "P/L (₹)": 0.0})

    equity_curve.append({"Date": idx, "Equity (₹)": cash + qty * close, "Close": close,
                         "Fast SMA": fast_now, "Slow SMA": slow_now})

# Mark-to-market final open position; no forced liquidation.
last_close = float(data["Close"].iloc[-1])
final_equity = cash + qty * last_close
net_pnl = final_equity - float(start_cash)
returns = net_pnl / float(start_cash) * 100

c1, c2, c3, c4 = st.columns(4)
c1.metric("Virtual equity", f"₹{final_equity:,.2f}")
c2.metric("Net P/L", f"₹{net_pnl:,.2f}", f"{returns:.2f}%")
c3.metric("Closed trades", str(sum(1 for t in trades if "SELL" in t["Action"])))
c4.metric("Open quantity", str(qty))

st.subheader(f"{ticker} — Historical price & moving averages")
chart = pd.DataFrame({
    "Close": data["Close"],
    f"SMA {fast}": data["Fast_SMA"],
    f"SMA {slow}": data["Slow_SMA"],
})
st.line_chart(chart)

st.subheader("Paper trade log")
if trades:
    st.dataframe(pd.DataFrame(trades), use_container_width=True, hide_index=True)
else:
    st.info("No trades were triggered in this historical period with the selected settings.")

st.subheader("Equity curve")
curve = pd.DataFrame(equity_curve).set_index("Date")
st.line_chart(curve[["Equity (₹)"]])

st.caption(f"Last available daily close: ₹{last_close:,.2f} | Data through: {data.index[-1].date()} | Data source: Yahoo Finance. Data may be delayed or adjusted.")
st.caption("Strategy: long-only SMA crossover + fixed stop loss/take profit + position cap + portfolio loss lock. This is a simple rule-based demo, not predictive AI. Backtest results do not predict future returns.")
