import asyncio
import os
from flask import Flask
import threading
import logging

# Import your bot class
from bot import BTCSignalBot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Flask app for Render's health checks
app = Flask(__name__)

@app.route('/')
@app.route('/health')
def health_check():
    return "✅ BTC Signal Bot is running!", 200

def run_bot():
    """Run the Telegram bot in a background thread"""
    bot = BTCSignalBot()
    try:
        # Create new event loop for the thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(bot.run_analysis_loop())
    except Exception as e:
        logger.error(f"Bot crashed: {e}")

if __name__ == "__main__":
    # Start the bot in background thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    logger.info("Bot thread started")
    
    # Run Flask web server (required for Render)
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"Starting web server on port {port}")
    app.run(host="0.0.0.0", port=port)