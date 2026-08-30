import asyncio, json, random, time, os
from datetime import datetime
from aiohttp import web, ClientSession

TELEGRAM_BOT_TOKEN = "8608793202:AAFoIeTiaDbGlx2PqLtduwo0EwAjKJaPrOA"
TELEGRAM_CHAT_ID = "-1004393987433"

ws_clients = set()
current_price = 122.278
candles = []
current_ticks = []
stats = {"wins": 0, "losses": 0}

def init_history():
    history = []
    now = int(time.time())
    start = (now // 60) * 60 - (35 * 60)
    p = 122.220
    for i in range(35):
        o = p
        change = (random.random() - 0.48) * 0.014
        c = round(o + change, 4)
        h = round(max(o, c) + random.random() * 0.007, 4)
        l = round(min(o, c) - random.random() * 0.007, 4)
        history.append({"time": start + (i * 60), "open": o, "high": h, "low": l, "close": c})
        p = c
    return history

candles = init_history()

# টেলিগ্রাম মেসেজ সেন্ডার ও এরর লগার
async def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        async with ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                res_data = await resp.json()
                if not res_data.get("ok"):
                    print(f"❌ [TELEGRAM API ERROR]: {res_data.get('description')}")
                else:
                    print("✅ [TELEGRAM SUCCESS] Message posted to channel!")
    except Exception as e:
        print(f"❌ [TELEGRAM NETWORK ERROR]: {e}")

def get_market_structure(c_list):
    if len(c_list) < 6: return "SIDEWAYS"
    recent = c_list[-6:]
    highs = [c["high"] for c in recent]
    lows = [c["low"] for c in recent]
    if highs[-1] >= highs[-3] and lows[-1] >= lows[-3]: return "UPTREND"
    elif highs[-1] <= highs[-3] and lows[-1] <= lows[-3]: return "DOWNTREND"
    return "SIDEWAYS"

def detect_fractals(c_list):
    up, down = [], []
    if len(c_list) < 5: return up, down
    for i in range(2, len(c_list) - 2):
        if (c_list[i]["high"] > c_list[i-1]["high"] and c_list[i]["high"] > c_list[i-2]["high"] and
            c_list[i]["high"] > c_list[i+1]["high"] and c_list[i]["high"] > c_list[i+2]["high"]):
            up.append(c_list[i]["high"])
        if (c_list[i]["low"] < c_list[i-1]["low"] and c_list[i]["low"] < c_list[i-2]["low"] and
            c_list[i]["low"] < c_list[i+1]["low"] and c_list[i]["low"] < c_list[i+2]["low"]):
            down.append(c_list[i]["low"])
    return up, down

def check_candle_reaction(candle):
    total_range = candle["high"] - candle["low"]
    if total_range == 0: return "NONE"
    body = abs(candle["close"] - candle["open"])
    lower_wick = min(candle["open"], candle["close"]) - candle["low"]
    upper_wick = candle["high"] - max(candle["open"], candle["close"])
    if lower_wick > body * 0.8 and candle["close"] >= candle["open"]: return "BULLISH_REJECTION"
    elif upper_wick > body * 0.8 and candle["close"] <= candle["open"]: return "BEARISH_REJECTION"
    return "NONE"

async def broadcast(data):
    for ws in list(ws_clients):
        try:
            await ws.send_json(data)
        except Exception:
            ws_clients.remove(ws)

async def rafi_bhai_engine():
    global current_price, stats, current_ticks, candles
    in_trade = False
    trade_end_time = 0
    trade_type = ""
    trade_entry = 0.0
    setup_name = ""

    # সার্ভার চালু হওয়ামাত্রই টেলিগ্রাম টেস্ট মেসেজ
    await asyncio.sleep(3)
    await send_telegram("🚀 <b>RAFI BHAI AI BOT ONLINE!</b>\n\nসিস্টেম চালু হয়েছে এবং মার্কেট স্ক্যানিং শুরু হয়েছে।")

    while True:
        await asyncio.sleep(1)
        now = int(time.time())
        sec = now % 60
        candle_ts = (now // 60) * 60

        step = (random.random() - 0.495) * 0.005
        current_price = round(current_price + step, 4)
        current_ticks.append(current_price)

        if len(candles) == 0 or candles[-1]["time"] != candle_ts:
            candles.append({"time": candle_ts, "open": current_price, "high": current_price, "low": current_price, "close": current_price})
            if len(candles) > 60: candles.pop(0)
            current_ticks = [current_price]
        else:
            c = candles[-1]
            c["close"] = current_price
            if current_price > c["high"]: c["high"] = current_price
            if current_price < c["low"]: c["low"] = current_price

        await broadcast({"type": "TICK", "price": current_price, "candle": candles[-1]})

        # ৫৫-৫৮ সেকেন্ডে নিশ্চিত সিগন্যাল তৈরি
        if not in_trade and 54 <= sec <= 57 and len(candles) >= 5:
            trend = get_market_structure(candles[:-1])
            up_f, down_f = detect_fractals(candles[:-1])
            reaction = check_candle_reaction(candles[-1])
            
            sig_found = False
            
            if trend == "UPTREND" or reaction == "BULLISH_REJECTION" or current_price > candles[-1]["open"]:
                trade_type = "BUY (CALL)"
                setup_name = "Price Action Bullish Flow"
                sig_found = True
            else:
                trade_type = "SELL (PUT)"
                setup_name = "Price Action Bearish Flow"
                sig_found = True

            if sig_found:
                in_trade = True
                trade_entry = current_price
                trade_end_time = now + (60 - sec) + 59
                next_t = datetime.fromtimestamp(now + (60 - sec)).strftime("%H:%M")
                
                await broadcast({
                    "type": "NEW_SIGNAL",
                    "asset": "USD/BDT (OTC)",
                    "time": next_t,
                    "direction": trade_type,
                    "entry_price": f"{trade_entry:.4f}",
                    "payout": "92%",
                    "setup": setup_name,
                    "structure": trend
                })

                emoji_dir = "🟢 <b>BUY (CALL) ⬆️</b>" if "BUY" in trade_type else "🔴 <b>SELL (PUT) ⬇️</b>"
                tg_msg = (
                    f"⚡ <b>RAFI BHAI AI BOT SIGNAL</b> ⚡\n\n"
                    f"💎 <b>Asset:</b> USD/BDT (OTC)\n"
                    f"⏰ <b>Time:</b> {next_t} (1 Min)\n"
                    f"🧭 <b>Direction:</b> {emoji_dir}\n"
                    f"💰 <b>Entry Price:</b> <code>{trade_entry:.4f}</code>\n"
                    f"🧩 <b>Setup:</b> {setup_name}\n"
                    f"💸 <b>Payout:</b> 92%\n\n"
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
    app["engine"] = asyncio.create_task(rafi_bhai_engine())

async def stop_tasks(app):
    app["engine"].cancel()

app.on_startup.append(start_tasks)
app.on_cleanup.append(stop_tasks)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)
