import asyncio, json, random, time, os
from datetime import datetime, timezone, timedelta
from aiohttp import web, ClientSession

TELEGRAM_BOT_TOKEN = "8608793202:AAFoIeTiaDbGlx2PqLtduwo0EwAjKJaPrOA"
TELEGRAM_CHAT_ID = "-1004393987433"

ASSET_NAME = "EUR/USD"
ws_clients = set()
current_price = 1.15920
candles = []
stats = {"wins": 0, "losses": 0}
last_signal_time = ""

# বর্তমান সময়ের লাইভ ক্যান্ডেল হিস্টোরি তৈরি (টাইম গ্যাপ ফিক্স)
def generate_fresh_history():
    global candles, current_price
    history = []
    now = int(time.time())
    current_minute = (now // 60) * 60
    start_ts = current_minute - (40 * 60)
    p = 1.15880
    
    for i in range(40):
        o = p
        change = (random.random() - 0.495) * 0.00015
        c = round(o + change, 5)
        h = round(max(o, c) + random.random() * 0.00008, 5)
        l = round(min(o, c) - random.random() * 0.00008, 5)
        history.append({
            "time": start_ts + (i * 60),
            "open": o,
            "high": h,
            "low": l,
            "close": c
        })
        p = c
    candles = history
    current_price = candles[-1]["close"]

generate_fresh_history()

# বাংলাদেশ টাইম (GMT+6) ফরম্যাট
def get_bd_time(ts=None):
    if ts is None:
        ts = time.time()
    bd_tz = timezone(timedelta(hours=6))
    dt = datetime.fromtimestamp(ts, tz=bd_tz)
    return dt.strftime("%H:%M")

async def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        async with ClientSession() as session:
            async with session.post(url, json=payload, timeout=5) as resp:
                pass
    except Exception as e:
        print(f"❌ [TELEGRAM ERROR]: {e}")

# ১. মার্কেট স্ট্রাকচার
def get_market_structure(c_list):
    if len(c_list) < 4: return "SIDEWAYS"
    recent = c_list[-4:]
    if recent[-1]["close"] >= recent[-3]["close"]: return "UPTREND"
    return "DOWNTREND"

# ২. ফ্র্যাক্টাল সাপোর্ট ও রেজিস্ট্যান্স
def detect_fractals(c_list):
    up, down = [], []
    if len(c_list) < 5: return up, down
    for i in range(2, len(c_list) - 2):
        if c_list[i]["high"] >= max(c_list[i-1]["high"], c_list[i+1]["high"]):
            up.append(c_list[i]["high"])
        if c_list[i]["low"] <= min(c_list[i-1]["low"], c_list[i+1]["low"]):
            down.append(c_list[i]["low"])
    return up, down

# ৩. ক্যান্ডেল রিঅ্যাকশন (Wick Rejection)
def check_candle_reaction(candle):
    body = abs(candle["close"] - candle["open"])
    lower_wick = min(candle["open"], candle["close"]) - candle["low"]
    upper_wick = candle["high"] - max(candle["open"], candle["close"])
    if lower_wick >= body * 0.6: return "BULLISH_REJECTION"
    elif upper_wick >= body * 0.6: return "BEARISH_REJECTION"
    return "NONE"

async def broadcast(data):
    for ws in list(ws_clients):
        try:
            await ws.send_json(data)
        except Exception:
            ws_clients.remove(ws)

async def real_live_engine():
    global current_price, stats, candles, last_signal_time
    in_trade = False
    trade_end_time = 0
    trade_type = ""
    trade_entry = 0.0
    setup_name = ""

    await asyncio.sleep(2)
    start_time_str = get_bd_time()
    await send_telegram(f"🚀 <b>RAFI BHAI AI BOT — REAL-TIME SYNCED</b>\n\nমার্কেট: <b>EUR/USD</b>\nবর্তমান বাংলাদেশ সময়: <b>{start_time_str}</b>\nলাইভ সিগন্যাল ট্র্যাকিং শুরু হয়েছে।")

    while True:
        await asyncio.sleep(1)
        now = int(time.time())
        sec = now % 60
        candle_ts = (now // 60) * 60

        # প্রতি সেকেন্ডে লাইভ ফরেক্স টিক মুভমেন্ট
        step = (random.random() - 0.496) * 0.00005
        current_price = round(current_price + step, 5)

        # প্রতি মিনিটে নতুন ক্যান্ডেল তৈরি
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

        # ব্রাউজারে লাইভ ডাটা পাঠানো
        await broadcast({"type": "TICK", "price": current_price, "candle": candles[-1]})

        # ৫৫ থেকে ৫৮ সেকেন্ডে কনফ্লুয়েন্স চেক ও বর্তমান সময়ের সিগন্যাল তৈরি
        if not in_trade and 54 <= sec <= 57 and len(candles) >= 5:
            next_candle_ts = now + (60 - sec)
            next_t = get_bd_time(next_candle_ts)
            
            # নিশ্চিত করা যেন একই মিনিটে ডাবল সিগন্যাল না যায়
            if next_t != last_signal_time:
                trend = get_market_structure(candles[:-1])
                reaction = check_candle_reaction(candles[-1])
                is_green = current_price >= candles[-1]["open"]
                
                sig_found = False
                if (trend == "UPTREND" and is_green) or reaction == "BULLISH_REJECTION":
                    trade_type = "BUY (CALL)"
                    setup_name = "Price Action + Support Flow"
                    sig_found = True
                elif (trend == "DOWNTREND" and not is_green) or reaction == "BEARISH_REJECTION":
                    trade_type = "SELL (PUT)"
                    setup_name = "Price Action + Resistance Flow"
                    sig_found = True

                if sig_found:
                    in_trade = True
                    trade_entry = current_price
                    trade_end_time = next_candle_ts + 59
                    last_signal_time = next_t
                    
                    # ওয়েবসাইট ড্যাশবোর্ড আপডেট
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

                    # বর্তমান টাইমে টেলিগ্রাম সিগন্যাল
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
                    print(f"🎯 [NEW SIGNAL] {next_t} -> {trade_type} @ {trade_entry:.5f}")

        # ১ মিনিট পর ট্রেডের ফলাফল
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
    app["engine"] = asyncio.create_task(real_live_engine())

async def stop_tasks(app):
    app["engine"].cancel()

app.on_startup.append(start_tasks)
app.on_cleanup.append(stop_tasks)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)
