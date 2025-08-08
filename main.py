import os
import yfinance as yf
import pandas as pd
import ta
import asyncio
from telegram.ext import ApplicationBuilder
from telegram.constants import ParseMode
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor, as_completed

# === Telegram Bot Info ===
TELEGRAM_TOKEN = '8305784916:AAE2UP_4CxpYVHxfpD1yFBk8hi3uU-vd32I'
CHAT_ID = '1020815701'

app = None
signal_cache = {}

# === Load symbols from CSV file ===
def load_symbols_from_csv(csv_path='under_100rs_stocks.csv'):
    try:
        df = pd.read_csv(csv_path)
        symbols = df['Symbol'].dropna().unique().tolist()
        print(f"✅ Loaded {len(symbols)} symbols from {csv_path}")
        return symbols
    except Exception as e:
        print(f"❌ Failed to load symbols: {e}")
        return []

# === Check if market is open in IST ===
def is_market_open():
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    return now.weekday() < 5 and dtime(9, 15) <= now.time() <= dtime(13, 30)

# === Improved signal calculation ===
def calculate_signal_score(rsi, prev_rsi, price, sma20, sma50, macd_line, signal_line, volume, avg_volume, adx):
    buy_score = 0
    sell_score = 0
    buy_notes = []
    sell_notes = []

    # BUY conditions
    if rsi < 25 and rsi > prev_rsi:
        buy_score += 3
        buy_notes.append("RSI rising from deeper oversold")
    elif rsi < 30:
        buy_score += 1
        buy_notes.append("RSI oversold")

    if macd_line > signal_line and macd_line > 0:
        buy_score += 3
        buy_notes.append("MACD bullish crossover above zero")

    if sma20 > sma50:
        buy_score += 2
        buy_notes.append("SMA20 above SMA50 (uptrend)")

    if volume > 2 * avg_volume:
        buy_score += 1
        buy_notes.append("Strong volume spike")

    if adx > 25:
        buy_score += 2
        buy_notes.append("Strong trend confirmed by ADX")

    # SELL conditions
    if rsi > 75 and rsi < prev_rsi:
        sell_score += 3
        sell_notes.append("RSI falling from overbought")
    elif rsi > 70:
        sell_score += 1
        sell_notes.append("RSI overbought")

    if macd_line < signal_line and macd_line < 0:
        sell_score += 3
        sell_notes.append("MACD bearish crossover below zero")

    if sma20 < sma50:
        sell_score += 2
        sell_notes.append("SMA20 below SMA50 (downtrend)")

    if volume > 2 * avg_volume:
        sell_score += 1
        sell_notes.append("Strong volume spike during drop")

    if adx > 25:
        sell_score += 2
        sell_notes.append("Strong trend confirmed by ADX")

    return buy_score, buy_notes, sell_score, sell_notes

# === Send Telegram alert ===
async def send_alert(message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 📲 ALERT SENT")
    await app.bot.send_message(chat_id=CHAT_ID, text=message, parse_mode=ParseMode.HTML)

# === Check signal for a stock ===
from ta.trend import ADXIndicator

'''async def check_signal(symbol):
    try:
        data = yf.download(symbol, interval='1d', period='30d', auto_adjust=True, progress=False)
        if data.empty or len(data) < 20:
            print(f"Skipping {symbol}: not enough data")
            return

        close = data['Close'].squeeze()
        volume = data['Volume'].squeeze()

        rsi = ta.momentum.RSIIndicator(close, window=14).rsi()
        macd = ta.trend.MACD(close)
        sma = ta.trend.SMAIndicator(close, window=20).sma_indicator()
        adx = ADXIndicator(high=data['High'], low=data['Low'], close=close, window=14).adx()

        last_price = close.iloc[-1]
        last_rsi = rsi.iloc[-1]
        prev_rsi = rsi.iloc[-2]
        last_macd = macd.macd().iloc[-1]
        last_signal = macd.macd_signal().iloc[-1]
        last_sma = sma.iloc[-1]
        last_volume = volume.iloc[-1]
        avg_volume = volume.iloc[-20:].mean()
        last_adx = adx.iloc[-1]

        buy_score, buy_notes, sell_score, sell_notes = calculate_signal_score(
            last_rsi, prev_rsi, last_price, last_sma,
            last_macd, last_signal, last_volume, avg_volume, last_adx
        )

        # Rest of your code for alerts...

    except Exception as e:
        print(f"❌ Error processing {symbol}: {e}")

'''

async def check_signal(symbol):
    try:
        # Ensure symbol is a string, not a list
        data = yf.download(symbol, interval='1d', period='60d', auto_adjust=True, progress=False)

        if data.empty or len(data) < 20:
            print(f"Skipping {symbol}: not enough data")
            return

        # rest of your processing...

    except Exception as e:
        print(f"❌ Error processing {symbol}: {e}")


# === Main bot ===
async def main():
    global app
    symbols = load_symbols_from_csv()
    if not symbols:
        print("❌ No symbols to monitor. Exiting.")
        return

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    await send_alert("✅ Bot Started. Monitoring shortlisted stocks...")

    last_heartbeat = datetime.now()

    while True:
        now = datetime.now()
        if is_market_open():
            print(f"[{now.strftime('%H:%M:%S')}] Market open. Checking signals for {len(symbols)} stocks...")
            tasks = [check_signal(symbol) for symbol in symbols]
            await asyncio.gather(*tasks)
        else:
            print(f"[{now.strftime('%H:%M:%S')}] 💤 Market closed. Waiting...")

        # Heartbeat message every 2 hours
        if (now - last_heartbeat).seconds >= 7200:
            await send_alert("⏳ Heartbeat Check: Bot is running fine ✅")
            last_heartbeat = now

        await asyncio.sleep(60)

# === Run the bot ===
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🔌 Bot stopped manually.")

