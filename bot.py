

# ==========================================
# CRYPTOBOOST PRO BOT (FULL PROFESSIONAL)
# ==========================================

import ccxt
import pandas as pd
import requests
import time
import schedule
import matplotlib.pyplot as plt
from datetime import datetime

# ==============================
# CONFIG
# ==============================

BOT_TOKEN = "8518401386:AAF7EI3b9VsK9uOzlYQD0btgUQ-MKkSbxY0"

CHAT_ID = "-1003564816977"

SYMBOL = "BTC/USDT"

exchange = ccxt.binance()
active_trade = None

# ==============================
# TELEGRAM FUNCTIONS
# ==============================

def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": text})

def send_chart(file):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    with open(file, 'rb') as f:
        requests.post(url, data={"chat_id": CHAT_ID}, files={"photo": f})

# ==============================
# STARTUP + HEARTBEAT
# ==============================

def send_startup():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    msg = f"""
🚀 CRYPTOBOOST PRO™ BOT STARTED

Status: ✅ Running
Mode: Signal Only
Strategy: Smart Money (SMC)

Timeframes:
5M • 15M • 1H • 4H

Start Time: {now}

⚠️ Trade with proper risk management
"""
    send_message(msg)

def heartbeat():
    now = datetime.now().strftime("%H:%M:%S")

    msg = f"""
💓 BOT HEARTBEAT

Status: ACTIVE
Time: {now}

Scanning market for setups...
"""
    send_message(msg)

# ==============================
# DATA FETCH
# ==============================

def get_data(tf, limit=200):
    ohlcv = exchange.fetch_ohlcv(SYMBOL, timeframe=tf, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['time','open','high','low','close','volume'])
    return df

# ==============================
# SMART MONEY LOGIC
# ==============================

def liquidity_sweep(df):
    last_high = df['high'].iloc[-2]
    last_low = df['low'].iloc[-2]

    current_high = df['high'].iloc[-1]
    current_low = df['low'].iloc[-1]

    if current_high > last_high:
        return "BUY_SWEEP"

    if current_low < last_low:
        return "SELL_SWEEP"

    return None

def demand_supply(df):
    demand = df['low'].rolling(50).min().iloc[-1]
    supply = df['high'].rolling(50).max().iloc[-1]
    return demand, supply

# ==============================
# SIGNAL GENERATION
# ==============================

def generate_signal():
    df_5m = get_data('5m')
    df_15m = get_data('15m')
    df_1h = get_data('1h')
    df_4h = get_data('4h')

    price = df_5m['close'].iloc[-1]

    demand, supply = demand_supply(df_4h)
    sweep = liquidity_sweep(df_5m)

    if sweep == "SELL_SWEEP" and price <= demand * 1.01:
        return {
            "type": "BUY",
            "entry": price,
            "sl": price * 0.98,
            "tp": price * 1.04
        }

    if sweep == "BUY_SWEEP" and price >= supply * 0.99:
        return {
            "type": "SELL",
            "entry": price,
            "sl": price * 1.02,
            "tp": price * 0.96
        }

    return None

# ==============================
# CHART CREATION
# ==============================

def create_chart(df, trade):
    plt.figure(figsize=(10,5))
    plt.plot(df['close'], label="BTC Price")

    plt.axhline(trade['entry'], linestyle='--', label="Entry")
    plt.axhline(trade['sl'], linestyle='--', label="SL")
    plt.axhline(trade['tp'], linestyle='--', label="TP")

    plt.legend()
    plt.title(f"{trade['type']} SIGNAL")

    filename = "chart.png"
    plt.savefig(filename)
    plt.close()

    return filename

# ==============================
# TRADE MANAGEMENT
# ==============================

def check_trade():
    global active_trade

    if not active_trade:
        return

    df = get_data('5m')
    price = df['close'].iloc[-1]

    if active_trade['type'] == "BUY":
        if price >= active_trade['tp']:
            send_message("✅ TP HIT — Trade Closed")
            active_trade = None
        elif price <= active_trade['sl']:
            send_message("❌ SL HIT — Trade Closed")
            active_trade = None

    elif active_trade['type'] == "SELL":
        if price <= active_trade['tp']:
            send_message("✅ TP HIT — Trade Closed")
            active_trade = None
        elif price >= active_trade['sl']:
            send_message("❌ SL HIT — Trade Closed")
            active_trade = None

# ==============================
# MAIN BOT LOGIC
# ==============================

def run_bot():
    global active_trade

    try:
        # If trade active → monitor only
        if active_trade:
            check_trade()
            return

        signal = generate_signal()

        if signal:
            active_trade = signal

            message = f"""
🚨 CRYPTOBOOST PREMIUM SIGNAL

Pair: BTC/USDT
Type: {signal['type']}

Entry: {signal['entry']:.2f}
Stop Loss: {signal['sl']:.2f}
Take Profit: {signal['tp']:.2f}

Timeframe: Multi-TF (5M–4H)
Strategy: Smart Money (Liquidity Sweep + Zone)
RR: 1:2

⚠️ Manage your risk properly
"""

            send_message(message)

            df = get_data('5m')
            chart = create_chart(df, signal)
            send_chart(chart)

    except Exception as e:
        send_message(f"⚠️ BOT ERROR:\n{str(e)}")

# ==============================
# SCHEDULER
# ==============================

schedule.every(15).minutes.do(run_bot)
schedule.every(2).hours.do(heartbeat)

# ==============================
# RUN SYSTEM WITH AUTO-RESTART
# ==============================

def main():
    send_startup()

    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except Exception as e:
            send_message(f"⚠️ SYSTEM CRASH DETECTED:\n{str(e)}")
            time.sleep(5)

# ==============================
# START BOT
# ==============================

print("🚀 CryptoBoost Pro Bot Running...")
main()