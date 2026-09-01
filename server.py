import asyncio, os, time, io
from datetime import datetime, timezone, timedelta
from aiohttp import web, ClientSession, FormData
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from playwright.async_api import async_playwright

# ==========================================
# ⚙️ CONFIGURATION & TARGET MANAGEMENT
# ==========================================
TELEGRAM_BOT_TOKEN = "8608793202:AAFoIeTiaDbGlx2PqLtduwo0EwAjKJaPrOA"
TELEGRAM_CHAT_ID = "-1004393987433"

ASSET_NAME = "EUR/USD"
PAYOUT_MULTIPLIER = 0.87

MTG_LEVELS = [2.0, 4.0, 8.0, 18.0, 40.0]
TARGET_PROFIT = 10.0
STOP_LOSS = 100.0

current_step_idx = 0
daily_profit_loss = 0.0
is_trading_locked = False
current_price = 1.15900
candles = []
stats = {"wins": 0, "losses": 0}
last_signal_time = ""

# গ্লোবাল ব্রাউজার পেজ অবজেক্ট
browser_page = None

# আপনার সংগৃহীত অরিজিনাল Quotex লগইন কুকিজ
QUOTEX_COOKIES = [
    {"name": "activeAccount", "value": "live", "domain": ".market-qx.info", "path": "/"},
    {"name": "laravel_session", "value": "eyJpdiI6InBPd01DYjlqVStBUWtVSld4b2Y5ZVE9PSIsInZhbHVlIjoiRzBoSlRtakNkM0dSMmJFQnpSbEhXVVFRaFduZWZzS1VVTVhadHp1STViSWF2aEl6NHpBamF6YXZvQVRRWkFxRmxWTERsNGY2NVpiMFlaOVdGdnhaTVhBTkROYXMycWo2T1lSZEJ5WldPRCsrZVJWbEpyOGlYZW5zVUpDdFNWWkkiLCJtYWMiOiJlZThlOGMwZDdjZWEwMzdiNDEwYmM0M2JiYjc4ZmJhZWJkZjY0ZjEzNGU1NmRjY2ZlY2RjZGIzZGI3ZDQyZTdkIiwidGFnIjoiIn0%3D", "domain": "market-qx.info", "path": "/"},
    {"name": "remember_web_59ba36addc2b2f9401580f014c7f58ea4e30989d", "value": "eyJpdiI6InJLSGFZZk55S0pGRnNxcUdDcUsxaGc9PSIsInZhbHVlIjoiQTk4R1ROa2RUSEN6NkhaemErWEVXK25OVUpjUE5zMm1EZDNpUUFyZ1Z6b3NDQy9WVHkySXJ3WkxnWTlENUtnQ293Ym50eFBYVDhCVytTZ1QwaFZuZ3p2VUJaQnVseEZTVnduc0VDYkx4MGJUY1M5eExPWll1VTJpQXVSN3pEcXlGdFY2VzhDZ25QTVczZGIwajM1RWoyV1JzcUlLV0FqNUdZejZ3VzF4UThhYmdSS0VEMzZ6WXFVeEZNR21BT21hZnNXeVdDYkxjaGljTlZwS3lheVcrV0ZRdW94SjRVRGRndGtySW1sUWpDbXgzdWZtK29qSEdmeGg1ZytJVUxzRyIsIm1hYyI6IjE4MGY5MWU2OTg5MzAzZWFkYjc2YmU5MTcwOGVlYmRhNjkwM2ZiM2Q5MTI4ZDU0ODY1NDI4MDM1MGE0YTQzOTYiLCJ0YWciOiIifQ%3D%3D", "domain": "market-qx.info", "path": "/"}
]

# ==========================================
# 🌐 CLOUD HEADLESS BROWSER LAUNCHER
# ==========================================
async def launch_cloud_browser():
    global browser_page
    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
    context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    await context.add_cookies(QUOTEX_COOKIES)
    browser_page = await context.new_page()
    try:
        await browser_page.goto("https://market-qx.info/en/trade", timeout=60000)
        await asyncio.sleep(5)
        print("🟢 Cloud Browser Active: Quotex Live Session Loaded.")
    except Exception as e:
        print(f"Browser load info: {e}")

async def cloud_execute_trade(direction, amount):
    global browser_page
    if not browser_page: return False
    try:
        # ১. অ্যামাউন্ট সেট
        await browser_page.evaluate(f"""() => {{
            const input = document.querySelector('input[name="amount"]') || document.querySelector('.input-control_number input');
            if (input) {{
                input.value = '{amount}';
                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                input.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }}
        }}""")
        await asyncio.sleep(0.2)
        
        # ২. বাটন ক্লিক
        is_call = "BUY" in direction
        await browser_page.evaluate(f"""() => {{
            const buttons = document.querySelectorAll('button');
            buttons.forEach(btn => {{
                const txt = (btn.innerText || '').toLowerCase();
                if ({'true' if is_call else 'false'} && (txt.includes('up') || txt.includes('call') || btn.classList.contains('call-btn'))) {{
                    btn.click();
                }} else if ({'false' if is_call else 'true'} && (txt.includes('down') || txt.includes('put') || btn.classList.contains('put-btn'))) {{
                    btn.click();
                }}
            }});
        }}""")
        print(f"⚡ [CLOUD AUTO-TRADE EXECUTED] {direction} ${amount}")
        return True
    except Exception as e:
        print(f"Execution Error: {e}")
        return False

# ==========================================
# 📊 SIGNAL ENGINE & INDICATORS
# ==========================================
def get_bd_time(ts=None):
    if ts is None: ts = time.time()
    bd_tz = timezone(timedelta(hours=6))
    return datetime.fromtimestamp(ts, tz=bd_tz).strftime("%H:%M")

def calculate_rsi(closes, period=14):
    if len(closes) < period + 1: return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        if diff >= 0: gains.append(diff); losses.append(0.0)
        else: gains.append(0.0); losses.append(abs(diff))
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0: return 100.0
    rs = (sum(gains[-period:]) / period) / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 2)

def generate_chart_image(c_list, title_text, mark_dir=None, step_label=""):
    fig, ax = plt.subplots(figsize=(7, 3.8), dpi=100)
    fig.patch.set_facecolor('#080d1a'); ax.set_facecolor('#080d1a')
    recent_candles = c_list[-16:]
    width, width2 = 0.55, 0.08
    for i, c in enumerate(recent_candles):
        col = '#00e676' if c['close'] >= c['open'] else '#ff1744'
        ax.bar(i, c['close'] - c['open'], width, bottom=c['open'], color=col, edgecolor=col)
        ax.bar(i, c['high'] - max(c['open'], c['close']), width2, bottom=max(c['open'], c['close']), color=col)
        ax.bar(i, min(c['open'], c['close']) - c['low'], width2, bottom=c['low'], color=col)

    if mark_dir and len(recent_candles) > 0:
        last_idx = len(recent_candles) - 1
        last_c = recent_candles[-1]
        tag = f"▲ {step_label} CALL" if "BUY" in mark_dir else f"▼ {step_label} PUT"
        arrow_col = '#00e676' if "BUY" in mark_dir else '#ff1744'
        y_pos = last_c['low'] - 0.00008 if "BUY" in mark_dir else last_c['high'] + 0.00008
        ax.annotate(tag, xy=(last_idx, last_c['low'] if "BUY" in mark_dir else last_c['high']),
                    xytext=(last_idx, y_pos), arrowprops=dict(facecolor=arrow_col, shrink=0.05, width=2, headwidth=6),
                    color=arrow_col, fontweight='bold', ha='center', fontsize=9)

    ax.set_title(title_text, color='#f8fafc', fontsize=11, fontweight='bold', pad=10)
    ax.tick_params(colors='#64748b', labelsize=8)
    ax.grid(True, linestyle='--', alpha=0.12, color='#ffffff')
    for spine in ax.spines.values(): spine.set_color('#1e293b')

    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format='png', facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()

async def send_telegram_photo(photo_bytes, caption_text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    data = FormData()
    data.add_field('chat_id', TELEGRAM_CHAT_ID)
    data.add_field('caption', caption_text)
    data.add_field('parse_mode', 'HTML')
    data.add_field('photo', photo_bytes, filename='chart.png', content_type='image/png')
    try:
        async with ClientSession() as session:
            await session.post(url, data=data, timeout=8)
    except Exception: pass

async def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        async with ClientSession() as session:
            await session.post(url, json=payload, timeout=5)
    except Exception: pass

async def fetch_truefx_price(session):
    global current_price
    try:
        async with session.get("https://webrates.truefx.com/rates/connect.html?f=csv&c=EUR/USD", timeout=3) as resp:
            text = (await resp.text()).strip()
            if text:
                parts = text.split(",")
                if len(parts) >= 6:
                    current_price = round((float(parts[2] + parts[3]) + float(parts[4] + parts[5])) / 2.0, 5)
    except Exception: pass

def prefill_history(p):
    global candles
    start_ts = (int(time.time()) // 60) * 60 - (40 * 60)
    history = []
    for i in range(40):
        o = p
        diff = 0.00003 if i % 2 == 0 else -0.00003
        c = round(o + diff, 5)
        history.append({"time": start_ts + (i * 60), "open": o, "high": round(max(o, c) + 0.00002, 5), "low": round(min(o, c) - 0.00002, 5), "close": c})
        p = c
    candles = history

def institutional_ai_analyzer(c_list):
    if len(c_list) < 30: return "NONE", "NO_DATA", 0, False
    c_cur, c_prev = c_list[-1], c_list[-2]
    closes = [c["close"] for c in c_list]
    ema_9, ema_21, ema_50 = sum(closes[-9:])/9, sum(closes[-21:])/21, sum(closes[-30:])/30
    rsi = calculate_rsi(closes, period=14)
    body = abs(c_prev["close"] - c_prev["open"])
    upper_wick = c_prev["high"] - max(c_prev["open"], c_prev["close"])
    lower_wick = min(c_prev["open"], c_prev["close"]) - c_prev["low"]

    if body < 0.000025: return "NONE", "DOJI_SKIP", 0, False
    recent_highs, recent_lows = max([c["high"] for c in c_list[-15:-2]]), min([c["low"] for c in c_list[-15:-2]])

    if ema_9 > ema_21 > ema_50 and 48 <= rsi <= 70:
        if lower_wick >= body * 0.7 and c_prev["low"] <= recent_lows: return "BUY (CALL)", "Liquidity Sweep", 95, True
        elif c_prev["close"] > c_prev["open"] and c_cur["close"] > c_prev["high"]: return "BUY (CALL)", "Momentum Breakout", 92, True
    elif ema_9 < ema_21 < ema_50 and 30 <= rsi <= 52:
        if upper_wick >= body * 0.7 and c_prev["high"] >= recent_highs: return "SELL (PUT)", "Liquidity Sweep", 95, True
        elif c_prev["close"] < c_prev["open"] and c_cur["close"] < c_prev["low"]: return "SELL (PUT)", "Momentum Breakdown", 92, True
    return "NONE", "SCANNING", 0, False

# ==========================================
# 🧠 LIVE CLOUD ENGINE LOOP
# ==========================================
async def live_ai_master_engine():
    global current_price, candles, last_signal_time, stats
    global current_step_idx, daily_profit_loss, is_trading_locked
    
    in_trade = False
    trade_type, trade_entry, trade_end_time, trade_amount = "", 0.0, 0, MTG_LEVELS[0]
    last_trade_minute = 0

    async with ClientSession() as session:
        await fetch_truefx_price(session)
        prefill_history(current_price)
        asyncio.create_task(launch_cloud_browser())
        await send_telegram(f"🚀 <b>24/7 CLOUD AUTO-TRADER ACTIVE</b> 🚀\n\n🌍 <b>Asset:</b> {ASSET_NAME}\n💰 <b>Steps:</b> $2 ➔ $4 ➔ $8 ➔ $18 ➔ $40\n🎯 <b>Target:</b> +${TARGET_PROFIT} | <b>SL:</b> -${STOP_LOSS}\n📱 <i>আপনার ফোন অফলাইন থাকলেও সার্ভারে ট্রেড চলবে!</i>")

        while True:
            await asyncio.sleep(1)
            now = int(time.time()); sec = now % 60; c_ts = (now // 60) * 60
            await fetch_truefx_price(session)

            if len(candles) == 0 or candles[-1]["time"] != c_ts:
                candles.append({"time": c_ts, "open": current_price, "high": current_price, "low": current_price, "close": current_price})
                if len(candles) > 60: candles.pop(0)
            else:
                c = candles[-1]
                c["close"] = current_price
                if current_price > c["high"]: c["high"] = current_price
                if current_price < c["low"]: c["low"] = current_price

            current_minute_count = now // 60
            if not in_trade and not is_trading_locked and 54 <= sec <= 58:
                can_trade = (current_step_idx > 0) or (current_minute_count - last_trade_minute >= 3)
                if can_trade:
                    next_t = get_bd_time(now + (60 - sec))
                    if next_t != last_signal_time:
                        direction, setup, confidence, is_valid = institutional_ai_analyzer(candles)
                        if is_valid or current_step_idx > 0:
                            if not is_valid: direction, setup, confidence = trade_type, f"Auto MTG Step {current_step_idx}", 95
                            trade_type, trade_amount, trade_entry = direction, MTG_LEVELS[current_step_idx], current_price
                            trade_end_time, in_trade, last_signal_time = now + (60 - sec) + 59, True, next_t
                            if current_step_idx == 0: last_trade_minute = current_minute_count

                            # 🚀 সার্ভার ব্যাকগ্রাউন্ড ব্রাউজারে অটো ট্রেড এক্সিকিউশন
                            asyncio.create_task(cloud_execute_trade(trade_type, trade_amount))

                            step_lbl = "BASE ENTRY" if current_step_idx == 0 else f"MTG {current_step_idx}"
                            emoji_dir = "🟢 <b>BUY (CALL) ⬆️</b>" if "BUY" in trade_type else "🔴 <b>SELL (PUT) ⬇️</b>"
                            tg_cap = f"💎 <b>CLOUD AUTO-TRADE PLACED</b> 💎\n\n🧭 <b>Direction:</b> {emoji_dir}\n💵 <b>Stake:</b> <b>${trade_amount:.2f}</b> ({step_lbl})\n💰 <b>Entry:</b> <code>{trade_entry:.5f}</code>\n📈 <b>Current P/L:</b> <code>{daily_profit_loss:+.2f}$</code>"
                            asyncio.create_task(send_telegram_photo(generate_chart_image(candles, f"{ASSET_NAME} {step_lbl}", trade_type, step_lbl), tg_cap))

            if in_trade and now >= trade_end_time:
                in_trade = False
                is_win = (current_price > trade_entry) if trade_type == "BUY (CALL)" else (current_price < trade_entry)

                if is_win:
                    profit = round(trade_amount * PAYOUT_MULTIPLIER, 2)
                    daily_profit_loss += profit
                    stats["wins"], current_step_idx = stats["wins"] + 1, 0
                    res_msg = f"✅ <b>PROFIT</b> (+${profit:.2f})\n📊 <b>Daily P/L:</b> {daily_profit_loss:+.2f}$"
                else:
                    daily_profit_loss -= trade_amount
                    stats["losses"], current_step_idx = stats["losses"] + 1, current_step_idx + 1
                    if current_step_idx >= len(MTG_LEVELS): current_step_idx = 0
                    res_msg = f"❌ <b>LOSS</b> (-${trade_amount:.2f})\n📊 <b>Daily P/L:</b> {daily_profit_loss:+.2f}$"

                asyncio.create_task(send_telegram_photo(generate_chart_image(candles, f"Result: {'WIN' if is_win else 'LOSS'}"), res_msg))

                if daily_profit_loss >= TARGET_PROFIT:
                    is_trading_locked = True
                    asyncio.create_task(send_telegram(f"🏆 <b>DAILY PROFIT HIT!</b> (+${daily_profit_loss:.2f})\n🔒 <i>Cloud Trading Stopped Safely.</i>"))
                elif daily_profit_loss <= -STOP_LOSS:
                    is_trading_locked = True
                    asyncio.create_task(send_telegram(f"🛑 <b>STOP LOSS HIT!</b> (-${abs(daily_profit_loss):.2f})\n🔒 <i>Cloud Trading Stopped Safely.</i>"))

async def self_keep_alive():
    while True:
        await asyncio.sleep(180)
        try:
            async with ClientSession() as session: await session.get("http://127.0.0.1:8080/", timeout=3)
        except Exception: pass

app = web.Application()
app.router.add_get("/", lambda r: web.Response(text="🟢 Cloud Headless Trader Online 24/7!"))

async def start_tasks(app):
    app["feed"] = asyncio.create_task(live_ai_master_engine())
    app["pinger"] = asyncio.create_task(self_keep_alive())

app.on_startup.append(start_tasks)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)
