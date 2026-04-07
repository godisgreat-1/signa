import asyncio
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
from telegram import Bot, InputFile
import matplotlib.pyplot as plt
import mplfinance as mpf
import io
import logging
from typing import Dict, Optional
import json
import os

# ------------------------------
# CONFIGURATION
# ------------------------------
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8518401386:AAF7EI3b9VsK9uOzlYQD0btgUQ-MKkSbxY0")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "@your_channel_username")
HEARTBEAT_INTERVAL = 3600
SIGNAL_COOLDOWN_HOURS = 4

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

sent_trades_file = "sent_trades.json"
if os.path.exists(sent_trades_file):
    with open(sent_trades_file, "r") as f:
        sent_trades = json.load(f)
else:
    sent_trades = {}

class BTCSignalBot:
    def __init__(self):
        self.bot = Bot(token=TELEGRAM_BOT_TOKEN)
        self.last_heartbeat = datetime.now()
        self.last_signal_time = None
        
    def fetch_ohlcv(self, timeframe: str, limit: int = 200) -> pd.DataFrame:
        """Fetch BTC data using Yahoo Finance"""
        try:
            ticker = yf.Ticker("BTC-USD")
            
            if timeframe == "15m":
                df = ticker.history(period="3d", interval="5m")
                if not df.empty:
                    df = df.resample('15min').agg({
                        'Open': 'first',
                        'High': 'max',
                        'Low': 'min',
                        'Close': 'last',
                        'Volume': 'sum'
                    }).dropna()
                    df = df.tail(limit)
                    
            elif timeframe == "1h":
                df = ticker.history(period="7d", interval="15m")
                if not df.empty:
                    df = df.resample('1h').agg({
                        'Open': 'first',
                        'High': 'max',
                        'Low': 'min',
                        'Close': 'last',
                        'Volume': 'sum'
                    }).dropna()
                    df = df.tail(limit)
                    
            elif timeframe == "4h":
                df = ticker.history(period="30d", interval="60m")
                if not df.empty:
                    df = df.resample('4h').agg({
                        'Open': 'first',
                        'High': 'max',
                        'Low': 'min',
                        'Close': 'last',
                        'Volume': 'sum'
                    }).dropna()
                    df = df.tail(limit)
                    
            elif timeframe == "1d":
                df = ticker.history(period=f"{limit}d", interval="1d")
                
            else:
                raise Exception(f"Unsupported timeframe: {timeframe}")
            
            if df.empty:
                raise Exception(f"No data received for {timeframe}")
            
            df.columns = [col.lower() for col in df.columns]
            
            required_cols = ['open', 'high', 'low', 'close', 'volume']
            for col in required_cols:
                if col not in df.columns:
                    df[col] = df['close'] if col == 'close' else 0
            
            logger.info(f"✅ Fetched {len(df)} candles for {timeframe}")
            return df[required_cols]
            
        except Exception as e:
            logger.error(f"Failed to fetch {timeframe} data: {e}")
            raise
    
    def multi_timeframe_analysis(self) -> Dict:
        """Perform analysis across all timeframes"""
        timeframes = ["15m", "1h", "4h", "1d"]
        results = {}
        
        for tf in timeframes:
            try:
                df = self.fetch_ohlcv(tf)
                
                if len(df) < 20:
                    continue
                
                results[tf] = {
                    "current_price": df['close'].iloc[-1],
                    "trend": "bullish" if df['close'].iloc[-1] > df['close'].iloc[-20:].mean() else "bearish",
                    "rsi": self.calculate_rsi(df['close']),
                    "volume_ratio": df['volume'].iloc[-1] / df['volume'].iloc[-20:].mean() if len(df) >= 20 else 1,
                    "support": df['low'].rolling(window=20).min().iloc[-1],
                    "resistance": df['high'].rolling(window=20).max().iloc[-1],
                    "liquidity_grab": self.detect_liquidity_grab(df)
                }
                
                if tf == "15m":
                    results[tf]["ema_fast"] = df['close'].ewm(span=9, adjust=False).mean().iloc[-1]
                    results[tf]["ema_slow"] = df['close'].ewm(span=21, adjust=False).mean().iloc[-1]
                    
                logger.info(f"✅ Analyzed {tf} - Price: ${results[tf]['current_price']:,.0f} - Trend: {results[tf]['trend']}")
                    
            except Exception as e:
                logger.error(f"Failed to analyze {tf}: {e}")
                continue
        
        if not results:
            raise Exception("No timeframe data available")
            
        return results
    
    def calculate_rsi(self, prices: pd.Series, period: int = 14) -> float:
        if len(prices) < period + 1:
            return 50
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        result = rsi.iloc[-1]
        return result if not pd.isna(result) else 50
    
    def detect_liquidity_grab(self, df: pd.DataFrame) -> bool:
        if len(df) < 10:
            return False
        recent_low = df['low'].iloc[-10:-1].min()
        return df['low'].iloc[-1] < recent_low and df['close'].iloc[-1] > df['open'].iloc[-1]
    
    def generate_signal(self, analysis: Dict) -> Optional[Dict]:
        if not analysis:
            return None
            
        bullish_signals = 0
        bearish_signals = 0
        
        for tf, data in analysis.items():
            weight = 1.5 if tf == "15m" else 1.0
            
            if data['trend'] == 'bullish':
                bullish_signals += (1 * weight)
            else:
                bearish_signals += (1 * weight)
                
            if data['liquidity_grab']:
                bullish_signals += (2 * weight)
                
            if data['rsi'] < 30:
                bullish_signals += (1 * weight)
            elif data['rsi'] > 70:
                bearish_signals += (1 * weight)
                
            if data['volume_ratio'] > 1.2:
                if data['trend'] == 'bullish':
                    bullish_signals += (1 * weight)
                else:
                    bearish_signals += (1 * weight)
            
            if tf == "15m" and 'ema_fast' in data and 'ema_slow' in data:
                if data['ema_fast'] > data['ema_slow']:
                    bullish_signals += 1
                else:
                    bearish_signals += 1
        
        current_price = analysis.get('15m', analysis.get('1h', {})).get('current_price', 0)
        if current_price == 0:
            return None
        
        logger.info(f"Signal scores - Bullish: {bullish_signals}, Bearish: {bearish_signals}")
        
        if bullish_signals >= bearish_signals + 2:
            return {
                "type": "LONG 🟢",
                "entry": round(current_price, 2),
                "sl": round(current_price * 0.985, 2),
                "tp1": round(current_price * 1.02, 2),
                "tp2": round(current_price * 1.04, 2),
                "tp3": round(current_price * 1.06, 2),
                "confidence": round(min(100, (bullish_signals / (bullish_signals + bearish_signals)) * 100), 1),
                "reasoning": self.generate_reasoning(analysis, "LONG")
            }
        elif bearish_signals >= bullish_signals + 2:
            return {
                "type": "SHORT 🔴",
                "entry": round(current_price, 2),
                "sl": round(current_price * 1.015, 2),
                "tp1": round(current_price * 0.98, 2),
                "tp2": round(current_price * 0.96, 2),
                "tp3": round(current_price * 0.94, 2),
                "confidence": round(min(100, (bearish_signals / (bullish_signals + bearish_signals)) * 100), 1),
                "reasoning": self.generate_reasoning(analysis, "SHORT")
            }
        
        return None
    
    def generate_reasoning(self, analysis: Dict, direction: str) -> str:
        reasons = []
        for tf, data in analysis.items():
            if data['trend'] == direction.lower():
                reasons.append(f"📈 {tf.upper()} trend aligned")
            if data['liquidity_grab']:
                reasons.append(f"💧 {tf.upper()} liquidity grab")
            if data['volume_ratio'] > 1.2:
                reasons.append(f"📊 {tf.upper()} volume spike ({data['volume_ratio']:.1f}x)")
            if tf == "15m" and 'ema_fast' in data and 'ema_slow' in data:
                if direction == "LONG" and data['ema_fast'] > data['ema_slow']:
                    reasons.append(f"⚡ 15m EMA bullish cross")
        return "\n".join(reasons[:5]) if reasons else "Technical confluence detected"
    
    async def create_chart_image(self, analysis: Dict) -> io.BytesIO:
        try:
            df = self.fetch_ohlcv("15m", limit=100)
            
            if df.empty:
                raise Exception("No chart data")
            
            support = analysis.get('15m', {}).get('support', df['low'].min())
            resistance = analysis.get('15m', {}).get('resistance', df['high'].max())
            
            apds = [
                mpf.make_addplot([support] * len(df), color='green', linestyle='--', width=0.8, alpha=0.7),
                mpf.make_addplot([resistance] * len(df), color='red', linestyle='--', width=0.8, alpha=0.7),
            ]
            
            if len(df) > 21:
                ema21 = df['close'].ewm(span=21, adjust=False).mean()
                apds.append(mpf.make_addplot(ema21, color='orange', width=0.8, alpha=0.5))
            
            buffer = io.BytesIO()
            mpf.plot(df, type='candle', style='charles', 
                     addplot=apds,
                     title=f'BTC/USDT - Smart Money Analysis (15m)',
                     ylabel='Price (USD)',
                     volume=True,
                     savefig=buffer, 
                     figsize=(12, 8))
            buffer.seek(0)
            return buffer
        except Exception as e:
            logger.error(f"Chart creation failed: {e}")
            return io.BytesIO()
    
    async def send_signal(self, signal: Dict):
        signal_id = f"{signal['type']}_{signal['entry']}_{datetime.now().strftime('%Y-%m-%d')}"
        if signal_id in sent_trades:
            logger.info(f"Duplicate prevented: {signal_id}")
            return
            
        message = f"""
🚨 **BTC SMART MONEY SIGNAL** 🚨

**Signal:** {signal['type']}
**Confidence:** {signal['confidence']}%

📊 **Entry:** ${signal['entry']:,.0f}
🎯 **Take Profits:**
   TP1: ${signal['tp1']:,.0f} (2%)
   TP2: ${signal['tp2']:,.0f} (4%)
   TP3: ${signal['tp3']:,.0f} (6%)

🛑 **Stop Loss:** ${signal['sl']:,.0f} (1.5%)

📈 **Setup:**
{signal['reasoning']}

⚠️ *Risk Management: Use 1-2% risk per trade*

🤖 Bot Active | {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}
        """
        
        try:
            analysis = await self.get_analysis_async()
            chart_buffer = await self.create_chart_image(analysis)
            
            await self.bot.send_photo(
                chat_id=TELEGRAM_CHANNEL_ID,
                photo=InputFile(chart_buffer, filename="btc_chart.png"),
                caption=message,
                parse_mode='Markdown'
            )
            
            sent_trades[signal_id] = {"timestamp": datetime.now().isoformat(), "signal": signal}
            with open(sent_trades_file, "w") as f:
                json.dump(sent_trades, f)
                
            self.last_signal_time = datetime.now()
            logger.info(f"✅ Signal sent: {signal['type']} at ${signal['entry']:,.0f}")
        except Exception as e:
            logger.error(f"Failed to send signal: {e}")
    
    async def get_analysis_async(self):
        return await asyncio.get_event_loop().run_in_executor(None, self.multi_timeframe_analysis)
    
    async def send_startup_message(self):
        message = f"""
🤖 **BTC Signal Bot ONLINE** 🟢

📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
📊 **Strategy:** Smart Money + Multi-Timeframe
⏱️ **Timeframes:** 15m, 1h, 4h, 1d
📈 **Data Source:** Yahoo Finance

✅ Bot is live and monitoring BTC!
        """
        await self.bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=message, parse_mode='Markdown')
        logger.info("Startup message sent")
    
    async def send_heartbeat(self):
        if (datetime.now() - self.last_heartbeat).total_seconds() >= HEARTBEAT_INTERVAL:
            try:
                analysis = await self.get_analysis_async()
                price = analysis.get('15m', {}).get('current_price', 0)
                trend = analysis.get('15m', {}).get('trend', 'unknown')
                
                message = f"""
💓 **Heartbeat - Bot Active**

🟢 Status: RUNNING
⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}
💰 BTC Price: ${price:,.0f}
📈 15M Trend: {trend.upper()}
📊 Last Signal: {self.last_signal_time.strftime('%H:%M UTC') if self.last_signal_time else 'None yet'}
                """
                await self.bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=message, parse_mode='Markdown')
                self.last_heartbeat = datetime.now()
                logger.info("Heartbeat sent")
            except Exception as e:
                logger.error(f"Heartbeat failed: {e}")
    
    async def run_analysis_loop(self):
        logger.info("Starting BTC signal bot...")
        await self.send_startup_message()
        
        await asyncio.sleep(5)
        
        while True:
            try:
                logger.info("Running market analysis...")
                analysis = await self.get_analysis_async()
                signal = self.generate_signal(analysis)
                
                if signal:
                    if self.last_signal_time:
                        hours_since = (datetime.now() - self.last_signal_time).total_seconds() / 3600
                        if hours_since >= SIGNAL_COOLDOWN_HOURS:
                            await self.send_signal(signal)
                        else:
                            logger.info(f"Signal skipped - cooldown ({hours_since:.1f}h left)")
                    else:
                        await self.send_signal(signal)
                else:
                    logger.info("No signal - market conditions not met")
                
                await self.send_heartbeat()
                
                logger.info("Waiting 5 minutes...")
                await asyncio.sleep(300)
                
            except Exception as e:
                logger.error(f"Loop error: {e}")
                await asyncio.sleep(60)