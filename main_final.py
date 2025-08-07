import os
import yfinance as yf
import pandas as pd
import ta
import asyncio
from telegram.ext import ApplicationBuilder
from telegram.constants import ParseMode
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

# === Your Telegram Bot Info ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")


app = None
signal_cache = {}

# === Load All NSE Symbols from Local CSV ===
def load_all_nse_symbols(csv_path='EQUITY_L.csv'):
    print("📅 Loading NSE stock list from local CSV...")
    try:
        df = pd.read_csv(csv_path)
        df.columns = df.columns.str.strip()  # 🧹 Remove leading/trailing whitespace
        df = df[df['SERIES'] == 'EQ']  # Only EQ series
        symbols = df['SYMBOL'].unique().tolist()
        print(f"✅ Loaded {len(symbols)} NSE symbols.")
        return [symbol + '.NS' for symbol in symbols]
    except Exception as e:
        print(f"❌ Failed to load NSE symbols: {e}")
        return []

# === Send Telegram Alert ===
async def send_alert(message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 📲 ALERT SENT")
    await app.bot.send_message(chat_id=CHAT_ID, text=message, parse_mode=ParseMode.HTML)

# === Check if Indian Market is Open ===
def is_market_open():
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    return now.weekday() < 5 and dtime(9, 15) <= now.time() <= dtime(16, 30)

# === Buy/Sell Signal Calculation ===
def calculate_signal_score(rsi, prev_rsi, price, sma, macd_line, signal_line, volume, avg_volume):
    buy_score = sell_score = 0
    buy_notes, sell_notes = [], []

    if rsi < 30 and rsi > prev_rsi:
        buy_score += 2
        buy_notes.append("RSI Rising from Oversold ✅")
    elif rsi < 30:
        buy_score += 1
        buy_notes.append("RSI Oversold ❗")

    if price > sma:
        buy_score += 1
        buy_notes.append("Price Above SMA(20) ✅")

    if macd_line > signal_line:
        buy_score += 2
        buy_notes.append("MACD Bullish Crossover ✅")

    if volume > 1.5 * avg_volume:
        buy_score += 1
        buy_notes.append("Volume Spike ✅")

    if prev_rsi < 30 and rsi >= 30:
        buy_score += 2
        buy_notes.append("RSI Crossover 30 ➡️ ✅")

    if rsi > 70 and rsi < prev_rsi:
        sell_score += 2
        sell_notes.append("RSI Falling from Overbought ❗")
    elif rsi > 70:
        sell_score += 1
        sell_notes.append("RSI Overbought ⚠️")

    if price < sma:
        sell_score += 1
        sell_notes.append("Price Below SMA(20) ⚠️")

    if macd_line < signal_line:
        sell_score += 2
        sell_notes.append("MACD Bearish Crossover ⚠️")

    if volume > 1.5 * avg_volume:
        sell_score += 1
        sell_notes.append("Volume Spike During Drop 📉")

    if prev_rsi > 70 and rsi <= 70:
        sell_score += 2
        sell_notes.append("RSI Crossed Below 70 ❗")

    return buy_score, buy_notes, sell_score, sell_notes

# === Signal Checker ===
async def check_signal(symbol):
    try:
        data = yf.download(symbol, interval='1m', period='1d', auto_adjust=True, progress=False)
        if data.empty or len(data) < 25:
            return

        close_array = data['Close'].values.squeeze()
        volume_array = data['Volume'].values.squeeze()

        close = pd.Series(close_array, index=data.index)
        volume = pd.Series(volume_array, index=data.index)

        rsi = ta.momentum.RSIIndicator(close=close, window=14).rsi()
        macd = ta.trend.MACD(close=close)
        macd_line = macd.macd()
        macd_signal = macd.macd_signal()
        sma = ta.trend.SMAIndicator(close=close, window=20).sma_indicator()

        last_price = close.iloc[-1]
        last_rsi = rsi.iloc[-1]
        prev_rsi = rsi.iloc[-2]
        last_macd = macd_line.iloc[-1]
        last_signal = macd_signal.iloc[-1]
        last_sma = sma.iloc[-1]
        last_volume = volume.iloc[-1]
        avg_volume = volume.iloc[-20:].mean()

        buy_score, buy_notes, sell_score, sell_notes = calculate_signal_score(
            last_rsi, prev_rsi, last_price, last_sma,
            last_macd, last_signal, last_volume, avg_volume
        )

        message = ""

        if buy_score >= 6:
            classification = "<b>🚀 STRONG BUY Opportunity</b>"
            if signal_cache.get(symbol) != classification:
                signal_cache[symbol] = classification
                criteria = '\n- '.join(buy_notes)
                message = f"""
{classification} for <b>{symbol}</b>

• RSI: {last_rsi:.2f} (Prev: {prev_rsi:.2f})
• MACD: {last_macd:.2f} vs Signal: {last_signal:.2f}
• SMA(20): ₹{last_sma:.2f}
• Price: ₹{last_price:.2f}
• Volume: {int(last_volume):,} (Avg: {int(avg_volume):,})

📊 Criteria:
- {criteria}

⚠️ Not financial advice. Review manually before acting.
"""
        elif sell_score >= 6:
            classification = "<b>📉 STRONG SELL Opportunity</b>"
            if signal_cache.get(symbol) != classification:
                signal_cache[symbol] = classification
                criteria = '\n- '.join(sell_notes)
                message = f"""
{classification} for <b>{symbol}</b>

• RSI: {last_rsi:.2f} (Prev: {prev_rsi:.2f})
• MACD: {last_macd:.2f} vs Signal: {last_signal:.2f}
• SMA(20): ₹{last_sma:.2f}
• Price: ₹{last_price:.2f}
• Volume: {int(last_volume):,} (Avg: {int(avg_volume):,})

📊 Criteria:
- {criteria}

⚠️ Not financial advice. Review manually before acting.
"""

        if message:
            await send_alert(message)

    except Exception as e:
        print(f"❌ Error for {symbol}: {e}")

# === Main Async Loop ===
async def main():
    global app
    symbols = load_all_nse_symbols()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    await send_alert("✅ Bot Started. Monitoring stocks...")

    while True:
        if is_market_open():
            tasks = [check_signal(symbol) for symbol in symbols]
            await asyncio.gather(*tasks)
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 💤 Market closed. Waiting...")
        await asyncio.sleep(60)

# === Run the Bot ===
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🔌 Bot stopped manually.")

