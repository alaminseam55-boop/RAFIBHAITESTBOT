import asyncio, os, time, io
from datetime import datetime, timezone, timedelta
from aiohttp import web, ClientSession, FormData
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

TELEGRAM_BOT_TOKEN = "8608793202:AAFoIeTiaDbGlx2PqLtduwo0EwAjKJaPrOA"
TELEGRAM_CHAT_ID = "-1004393987433"

ASSET_NAME = "EUR/USD"
ws_clients = set()
current_price = 1.15900
candles = []
stats = {"wins": 0, "losses": 0}
last_signal_time = ""

def get_bd_time(ts=None):
    if ts is None:
        ts = time.time()
    bd_tz = timezone(timedelta(hours=6))
    return datetime.fromtimestamp(ts, tz=bd_tz).strftime("%H:%M")

# লাইভ ক্যান্ডেলস্টিক চার্ট ছবি তৈরির ফাংশন
def generate_chart_image(c_list, title_text, mark_dir=None):
    fig, ax = plt.subplots(figsize=(7, 3.8), dpi=100)
    fig.patch.set_facecolor('#0f172a')
    ax.set_facecolor('#0f172a')

    recent_candles = c_list[-15:]
    width = 0.55
    width2 = 0.08

    for i, c in enumerate(recent_candles):
        col = '#10b981' if c['close'] >= c['open'] else '#ef4444'
        ax.bar(i, c['close'] - c['open'], width, bottom=c['open'], color=col, edgecolor=col)
        ax.bar(i, c['high'] - max(c['open'], c['close']), width2, bottom=max(c['open'], c['close']), color=col)
        ax.bar(i, min(c['open'], c['close']) - c['low'], width2, bottom=c['low'], color=col)

    if mark_dir and len(recent_candles) > 0:
        last_idx = len(recent_candles) - 1
        last_c = recent_candles[-1]
        if "BUY" in mark_dir:
            ax.annotate('▲ ENTRY CALL', xy=(last_idx, last_c['low']), xytext=(last_idx, last_c['low'] - 0.00008),
                        arrowprops=dict(facecolor='#10b981', shrink=0.05, width=2, headwidth=6),
                        color='#10b981', fontweight='bold', ha='center', fontsize=9)
        elif "SELL" in mark_dir:
            ax.annotate('▼ ENTRY PUT', xy=(last_idx, last_c['high']), xytext=(last_idx, last_c['high'] + 0.00008),
                        arrowprops=dict(facecolor='#ef4444', shrink=0.05, width=2, headwidth=6),
                        color='#ef4444', fontweight='bold', ha='center', fontsize=9)

    ax.set_title(title_text, color='#f8fafc', fontsize=11, fontweight='bold', pad=10)
    ax.tick_params(colors='#64748b', labelsize=8)
    ax.grid(True, linestyle='--', alpha=0.15, color='#ffffff')
    for spine in ax.spines.values():
        spine.set_color('#1e293b')

    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format='png', facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()

# ছবি সহ টেলিগ্রাম মেসেজ পাঠানোর ফাংশন
async def send_telegram_photo(photo_bytes, caption_text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    data = FormData()
    data.add_field('chat_id', TELEGRAM_CHAT_ID)
    data.add_field('caption', caption_text)
    data.add_field('parse_mode', 'HTML')
    data.add_field('photo', photo_bytes, filename='chart.png', content_type='image/png')
    
    try:
        async with ClientSession() as session:
            async with session.post(url, data=data, timeout=8) as resp:
                pass
    except Exception as e:
        print(f"❌ [TG PHOTO ERROR]: {e}")

async def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        async with ClientSession() as session:
            async with session.post(url, json=payload, timeout=5) as resp:
                pass
    except Exception as e:
        print(f"❌ [TG ERROR]: {e}")

async def fetch_truefx_price(session):
    global current_price
    url = "https://webrates.truefx.com/rates/connect.html?f=csv&c=EUR/USD"
    try:
        async with session.get(url, timeout=3) as resp:
            text = (await resp.text()).strip()
            if text:
                parts = text.split(",")
                if len(parts) >= 6:
                    bid = float(parts[2] + parts[3])
                    offer = float(parts[4] + parts[5])
                    current_price = round((bid + offer) / 2.0, 5)
                    return current_price
    except Exception:
        pass
    return current_price

def prefill_history(p):
    global candles
    now = int(time.time())
    start_ts = (now // 60) * 60 - (30 * 60)
    history = []
    for i in range(30):
        o = p
        diff = 0.00003 if i % 2 == 0 else -0.00003
        c = round(o + diff, 5)
        h = round(max(o, c) + 0.00002, 5)
        l = round(min(o, c) - 0.00002, 5)
        history.append({"time": start_ts + (i * 60), "open": o, "high": h, "low": l, "close": c})
        p = c
    candles = history

def deep_ai_analysis(c_list):
    if len(c_list) < 5:
        return "NONE", "NO_DATA", 0, False

    c_cur = c_list[-1]
    c_prev = c_list[-2]

    buy_score = 0
    sell_score = 0
    detected_setups = []

    body = abs(c_prev["close"] - c_prev["open"])
    upper_wick = c_prev["high"] - max(c_prev["open"], c_prev["close"])
    lower_wick = min(c_prev["open"], c_prev["close"]) - c_prev["low"]

    if lower_wick >= body * 0.8:
        buy_score += 35
        detected_setups.append("Liquidity Rejection (Support)")
    elif upper_wick >= body * 0.8:
        sell_score += 35
        detected_setups.append("Liquidity Rejection (Resistance)")

    closes = [c["close"] for c in c_list[-8:]]
    ema_fast = sum(closes[-3:]) / 3
    ema_slow = sum(closes[-6:]) / 6

    if ema_fast >= ema_slow and c_cur["close"] >= c_cur["open"]:
        buy_score += 30
        detected_setups.append("Smart Money Bullish Flow")
    elif ema_fast <= ema_slow and c_cur["close"] <= c_cur["open"]:
        sell_score += 30
        detected_setups.append("Smart Money Bearish Flow")

    if c_cur["close"] > c_prev["high"]:
        buy_score += 25
        detected_setups.append("High-Volume Bullish Breakout")
    elif c_cur["close"] < c_prev["low"]:
        sell_score += 25
        detected_setups.append("High-Volume Bearish Breakdown")
    else:
        if c_cur["close"] > c_cur["open"]: buy_score += 20
        else: sell_score += 20

    if buy_score >= 50 and buy_score > sell_score:
        confidence = min(85 + (buy_score - 50), 96)
        setup_name = " + ".join(detected_setups[:2]) if detected_setups else "Institutional Flow"
        return "BUY (CALL)", setup_name, confidence, True
    elif sell_score >= 50 and sell_score > buy_score:
        confidence = min(85 + (sell_score - 50), 96)
        setup_name = " + ".join(detected_setups[:2]) if detected_setups else "Institutional Flow"
        return "SELL (PUT)", setup_name, confidence, True

    return "NONE", "BALANCED", 0, False

async def broadcast(data):
    for ws in list(ws_clients):
        try:
            await ws.send_json(data)
        except Exception:
            ws_clients.remove(ws)

async def live_ai_core_engine():
    global current_price, candles, last_signal_time, stats
    in_trade = False
    trade_end_time = 0
    trade_type = ""
    trade_entry = 0.0
    setup_name = ""
    last_trade_minute = 0

    async with ClientSession() as session:
        await fetch_truefx_price(session)
        prefill_history(current_price)

        bd_now = get_bd_time()
        await send_telegram(
            f"⚡ <b>RAFI BHAI AI BOT — LIVE VISUAL ENGINE ONLINE</b> ⚡\n\n"
            f"🌍 <b>Asset:</b> {ASSET_NAME} (Quotex Real Feed)\n"
            f"⏰ <b>Start Time:</b> {bd_now}\n"
            f"📸 <i>এখন থেকে সিগন্যাল ও রেজাল্ট লাইভ চার্ট ইমেজ সহ আসবে!</i>"
        )

        while True:
            await asyncio.sleep(1)
            now = int(time.time())
            sec = now % 60
            c_ts = (now // 60) * 60

            await fetch_truefx_price(session)

            if len(candles) == 0 or candles[-1]["time"] != c_ts:
                candles.append({
                    "time": c_ts,
                    "open": current_price,
                    "high": current_price,
                    "low": current_price,
                    "close": current_price
                })
                if len(candles) > 60: candles.pop(0)
            else:
                c = candles[-1]
                c["close"] = current_price
                if current_price > c["high"]: c["high"] = current_price
                if current_price < c["low"]: c["low"] = current_price

            await broadcast({"type": "TICK", "price": current_price, "candle": candles[-1]})

            # ৫৫-৫৮ সেকেন্ডে সিগন্যাল তৈরি ও চার্টের ছবি সহ পোস্ট
            current_minute_count = now // 60
            if not in_trade and 54 <= sec <= 58 and (current_minute_count - last_trade_minute >= 2):
                next_candle_ts = now + (60 - sec)
                next_t = get_bd_time(next_candle_ts)

                if next_t != last_signal_time:
                    direction, setup, confidence, is_valid = deep_ai_analysis(candles)

                    if is_valid:
                        trade_type = direction
                        setup_name = setup
                        in_trade = True
                        trade_entry = current_price
                        trade_end_time = next_candle_ts + 59
                        last_signal_time = next_t
                        last_trade_minute = current_minute_count

                        await broadcast({
                            "type": "NEW_SIGNAL",
                            "asset": ASSET_NAME,
                            "time": next_t,
                            "direction": trade_type,
                            "entry_price": f"{trade_entry:.5f}",
                            "payout": "87%",
                            "setup": setup_name,
                            "structure": f"AI CONFIDENCE: {confidence}%"
                        })

                        emoji_dir = "🟢 <b>BUY (CALL) ⬆️</b>" if "BUY" in trade_type else "🔴 <b>SELL (PUT) ⬇️</b>"
                        tg_caption = (
                            f"🔥 <b>RAFI BHAI AI — NEW LIVE SIGNAL</b> 🔥\n\n"
                            f"🌍 <b>Asset:</b> {ASSET_NAME}\n"
                            f"⏰ <b>Time:</b> {next_t} (1 Min Candle)\n"
                            f"🧭 <b>Direction:</b> {emoji_dir}\n"
                            f"💰 <b>Entry Price:</b> <code>{trade_entry:.5f}</code>\n"
                            f"🧠 <b>AI Setup:</b> {setup_name}\n"
                            f"📊 <b>Confidence Score:</b> <b>{confidence}%</b>\n"
                            f"💸 <b>Payout:</b> 87%\n\n"
                            f"⚠️ <i>Strict 1-Step Martingale If Needed</i>"
                        )
                        chart_img = generate_chart_image(candles, f"{ASSET_NAME} Live Signal ({next_t})", trade_type)
                        asyncio.create_task(send_telegram_photo(chart_img, tg_caption))
                        print(f"🎯 [CHART SIGNAL POSTED] {next_t} -> {trade_type}")

            # রেজাল্ট চেক ও রেজাল্ট চার্ট ছবি সহ পোস্ট
            if in_trade and now >= trade_end_time:
                in_trade = False
                close_p = current_price
                is_win = (close_p > trade_entry) if trade_type == "BUY (CALL)" else (close_p < trade_entry)
                if is_win: stats["wins"] += 1
                else: stats["losses"] += 1
                total = stats["wins"] + stats["losses"]
                win_r = f"{round((stats['wins']/total)*100)}%"

                await broadcast({
                    "type": "SIGNAL_RESULT",
                    "result": "WIN" if is_win else "LOSS",
                    "wins": stats["wins"],
                    "losses": stats["losses"],
                    "win_rate": win_r,
                    "entry": trade_entry,
                    "close": close_p
                })

                res_emoji = "✅ <b>PROFIT (WIN)</b> 🚀" if is_win else "❌ <b>LOSS</b> 🔻"
                tg_res_caption = (
                    f"🏁 <b>TRADE RESULT UPDATE</b>\n\n"
                    f"🌍 <b>Asset:</b> {ASSET_NAME}\n"
                    f"📊 <b>Outcome:</b> {res_emoji}\n"
                    f"📈 <b>Wins:</b> {stats['wins']} | <b>Losses:</b> {stats['losses']}\n"
                    f"🎯 <b>Accuracy:</b> {win_r}"
                )
                res_chart_img = generate_chart_image(candles, f"{ASSET_NAME} Result: {'WIN' if is_win else 'LOSS'}")
                asyncio.create_task(send_telegram_photo(res_chart_img, tg_res_caption))

async def self_keep_alive():
    while True:
        await asyncio.sleep(240)
        try:
            async with ClientSession() as session:
                await session.get("http://127.0.0.1:8080/", timeout=3)
        except Exception:
            pass

async def ws_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    ws_clients.add(ws)
    total = stats["wins"] + stats["losses"]
    win_r = f"{round((stats['wins']/total)*100)}%" if total > 0 else "0%"
    await ws.send_json({
        "type": "INIT",
        "wins": stats["wins"],
        "losses": stats["losses"],
        "win_rate": win_r,
        "price": current_price,
        "history": candles
    })
    try:
        async for _ in ws: pass
    finally:
        ws_clients.remove(ws)
    return ws

async def handle_index(request):
    return web.FileResponse("./index.html")

app = web.Application()
app.router.add_get("/", handle_index)
app.router.add_get("/ws", ws_handler)

async def start_tasks(app):
    app["feed"] = asyncio.create_task(live_ai_core_engine())
    app["pinger"] = asyncio.create_task(self_keep_alive())

async def stop_tasks(app):
    app["feed"].cancel()
    app["pinger"].cancel()

app.on_startup.append(start_tasks)
app.on_cleanup.append(stop_tasks)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)
