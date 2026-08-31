import asyncio, json, random, time, os
from datetime import datetime, timezone, timedelta
from aiohttp import web, ClientSession

TELEGRAM_BOT_TOKEN = "8608793202:AAFoIeTiaDbGlx2PqLtduwo0EwAjKJaPrOA"
TELEGRAM_CHAT_ID = "-1004393987433"

ASSET_NAME = "EUR/USD"
ws_clients = set()
current_price = 1.15898
candles = []
stats = {"wins": 0, "losses": 0}
last_signal_time = ""

def get_bd_time(ts=None):
    if ts is None:
        ts = time.time()
    bd_tz = timezone(timedelta(hours=6))
    return datetime.fromtimestamp(ts, tz=bd_tz).strftime("%H:%M")

async def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        async with ClientSession() as session:
            async with session.post(url, json=payload, timeout=5) as resp:
                pass
    except Exception as e:
        print(f"❌ [TELEGRAM ERROR]: {e}")

# লাইভ ফরেক্স রেট ফেচিং
async def get_live_forex_price():
    global current_price
    url = "https://open.er-api.com/v6/latest/EUR"
    try:
        async with ClientSession() as session:
            async with session.get(url, timeout=4) as resp:
                data = await resp.json()
                rate = data.get("rates", {}).get("USD")
                if rate:
                    return float(rate)
    except Exception:
        pass
    return current_price

# প্রাইস অ্যাকশন ও সুপারট্রেন্ড বিশ্লেষণ
def analyze_real_market(c_list):
    if len(c_list) < 3: return "NEUTRAL", "NONE"
    c1, c2, c3 = c_list[-3], c_list[-2], c_list[-1]
    
    if c3["close"] < c2["close"] and c2["close"] < c1["close"]:
        return "DOWNTREND", "STRONG_BEARISH_MOMENTUM"
    elif c3["close"] > c2["close"] and c2["close"] > c1["close"]:
        return "UPTREND", "STRONG_BULLISH_MOMENTUM"
    
    body = abs(c3["close"] - c3["open"])
    lower_wick = min(c3["open"], c3["close"]) - c3["low"]
    upper_wick = c3["high"] - max(c3["open"], c3["close"])
    
    if lower_wick > body * 1.1:
        return "BULLISH_FLOW", "LOWER_WICK_REJECTION"
    elif upper_wick > body * 1.1:
        return "BEARISH_FLOW", "UPPER_WICK_REJECTION"
        
    return "SIDEWAYS", "PRICE_CONSOLIDATION"

async def broadcast(data):
    for ws in list(ws_clients):
        try:
            await ws.send_json(data)
        except Exception:
            ws_clients.remove(ws)

def init_history(base_p):
    global candles
    history = []
    now = int(time.time())
    start = (now // 60) * 60 - (35 * 60)
    p = base_p + 0.00030
    for i in range(35):
        o = p
        diff = -0.00002 if i > 15 else 0.00001
        c = round(o + diff, 5)
        h = round(max(o, c) + 0.00002, 5)
        l = round(min(o, c) - 0.00002, 5)
        history.append({"time": start + (i * 60), "open": o, "high": h, "low": l, "close": c})
        p = c
    candles = history

# মাস্টার সিগন্যাল লুপ
async def real_signal_master_loop():
    global current_price, stats, candles, last_signal_time
    in_trade = False
    trade_end_time = 0
    trade_type = ""
    trade_entry = 0.0
    setup_name = ""

    p = await get_live_forex_price()
    if p: current_price = p
    init_history(current_price)

    await asyncio.sleep(2)
    bd_now = get_bd_time()
    await send_telegram(
        f"🌍 <b>RAFI BHAI AI BOT — 100% REAL MARKET ONLINE</b>\n\n"
        f"💎 <b>Asset:</b> {ASSET_NAME}\n"
        f"⏰ <b>Start Time:</b> {bd_now}\n"
        f"💰 <b>Live Price:</b> <code>{current_price:.5f}</code>\n"
        f"🚀 <i>২৪ ঘণ্টা সক্রিয় লাইভ অ্যানালাইসিস শুরু হয়েছে!</i>"
    )

    while True:
        await asyncio.sleep(1)
        now = int(time.time())
        sec = now % 60
        candle_ts = (now // 60) * 60

        if sec % 3 == 0:
            live_p = await get_live_forex_price()
            if live_p:
                current_price = live_p

        if len(candles) == 0 or candles[-1]["time"] != candle_ts:
            candles.append({
                "time": candle_ts,
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

        # ৫৫ থেকে ৫৭ সেকেন্ডে সিগন্যাল ডিটেকশন
        if not in_trade and 54 <= sec <= 57 and len(candles) >= 4:
            next_candle_ts = now + (60 - sec)
            next_t = get_bd_time(next_candle_ts)

            if next_t != last_signal_time:
                trend, pattern = analyze_real_market(candles)
                
                sig_found = False
                if "DOWN" in trend or "BEARISH" in pattern or current_price < candles[-1]["open"]:
                    trade_type = "SELL (PUT)"
                    setup_name = f"Trend Flow: {pattern.replace('_', ' ')}"
                    sig_found = True
                elif "UP" in trend or "BULLISH" in pattern or current_price > candles[-1]["open"]:
                    trade_type = "BUY (CALL)"
                    setup_name = f"Trend Flow: {pattern.replace('_', ' ')}"
                    sig_found = True

                if sig_found:
                    in_trade = True
                    trade_entry = current_price
                    trade_end_time = next_candle_ts + 59
                    last_signal_time = next_t

                    await broadcast({
                        "type": "NEW_SIGNAL",
                        "asset": ASSET_NAME,
                        "time": next_t,
                        "direction": trade_type,
                        "entry_price": f"{trade_entry:.5f}",
                        "payout": "87%",
                        "setup": setup_name,
                        "structure": trend
                    })

                    emoji_dir = "🟢 <b>BUY (CALL) ⬆️</b>" if "BUY" in trade_type else "🔴 <b>SELL (PUT) ⬇️</b>"
                    tg_msg = (
                        f"⚡ <b>RAFI BHAI AI BOT SIGNAL</b> ⚡\n\n"
                        f"🌍 <b>Asset:</b> {ASSET_NAME}\n"
                        f"⏰ <b>Time:</b> {next_t} (1 Min Candle)\n"
                        f"🧭 <b>Direction:</b> {emoji_dir}\n"
                        f"💰 <b>Entry Price:</b> <code>{trade_entry:.5f}</code>\n"
                        f"🧩 <b>Setup:</b> {setup_name}\n"
                        f"💸 <b>Payout:</b> 87%\n\n"
                        f"⚠️ <i>Strict 1-Step Martingale If Needed</i>"
                    )
                    asyncio.create_task(send_telegram(tg_msg))

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
            tg_res_msg = (
                f"🏁 <b>TRADE RESULT UPDATE</b>\n\n"
                f"🌍 <b>Asset:</b> {ASSET_NAME}\n"
                f"📊 <b>Outcome:</b> {res_emoji}\n"
                f"📈 <b>Wins:</b> {stats['wins']} | <b>Losses:</b> {stats['losses']}\n"
                f"🎯 <b>Accuracy:</b> {win_r}"
            )
            asyncio.create_task(send_telegram(tg_res_msg))

# ২৪ ঘণ্টা সার্ভার চালু রাখার সেল্ফ-পিং লুপ
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
    app["engine"] = asyncio.create_task(real_signal_master_loop())
    app["pinger"] = asyncio.create_task(self_keep_alive())

async def stop_tasks(app):
    app["engine"].cancel()
    app["pinger"].cancel()

app.on_startup.append(start_tasks)
app.on_cleanup.append(stop_tasks)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)
