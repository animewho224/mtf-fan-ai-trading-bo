# MTF Fan AI Trading Bot

Automated multi-timeframe support/resistance fan scanner for Telegram.

## Markets and data proxies
- XAUUSD: `GC=F` (COMEX gold futures proxy)
- BTCUSD: `BTC-USD` (Yahoo Finance BTC/USD spot proxy)
- NASDAQ: `NQ=F` (Nasdaq-100 futures proxy)

**Important:** These are not guaranteed to match your broker's XAUUSD/BTCUSD/NASDAQ CFD feed. Compare prices and confirm levels in MT5 before trading.

## Timeframes
M5, M15, M30, H1, H4, D1, W1, MN1. Some frames are resampled from Yahoo Finance data. Availability and freshness depend on Yahoo Finance.

## Create a Telegram bot
1. In Telegram, open `@BotFather`.
2. Send `/newbot` and follow the instructions.
3. Copy the bot token. Do not share it in chat or put it in source code.
4. Open your new bot and press Start.
5. To obtain your chat ID, send a message to the bot, then open:
   `https://api.telegram.org/botYOUR_TOKEN/getUpdates`
   Find `message.chat.id`. Keep the token private.

## Create a new GitHub repository
1. On GitHub, tap **New repository**.
2. Name it `mtf-fan-ai-trading-bot`.
3. Choose **Public** (recommended for GitHub Actions free usage), then create it.
4. Upload all files and folders from this project, preserving `.github/workflows/scan.yml`.

## Add GitHub Secrets
Repository → Settings → Secrets and variables → Actions → New repository secret:
- `TELEGRAM_BOT_TOKEN` = token from BotFather
- `TELEGRAM_CHAT_ID` = your Telegram chat ID

Never put these values in `bot.py`, README, screenshots, or public commits.

## Run
Repository → Actions → MTF Fan AI Scan → Run workflow.

After the first successful manual run, scheduled runs should occur about every 5 minutes. GitHub scheduled workflows can be delayed during high load and may be disabled for inactive public repositories. Check the Actions tab for failures.

## What the scanner does
- Finds confirmed pivot highs/lows.
- Projects descending resistance fan lines and ascending support fan lines.
- Clusters nearby levels from multiple timeframes.
- Uses EMA20/EMA50 as a broad trend filter.
- Sends BUY WATCH / SELL WATCH only when a nearby cluster and a simple M5 rejection condition agree; otherwise WAIT.

This is a rule-based technical scanner, not machine-learning AI and not an execution bot. It does not place trades. Test on demo first; signals can be wrong.
