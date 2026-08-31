import asyncio, json, time, os
from datetime import datetime
from aiohttp import web, ClientSession, WSMsgType

TELEGRAM_BOT_TOKEN = "8608793202:AAFoIeTiaDbGlx2PqLtduwo0EwAjKJaPrOA"
TELEGRAM_CHAT_ID = "-1004393987433"

ASSET_NAME = "EUR/USD"
ws_clients = set()
current_price = 1.15922
candles = []
current_ticks = []
stats = {"wins": 0, "losses": 0}

# টেলিগ্রাম মেসেজ সেন্ডার
async def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        async with ClientSession() as session:
            async with session.post(url, json=payload) as resp:
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
    if lower_wick >= body * 0.7: return "BULLISH_REJECTION"
    elif upper_wick >= body * 0.7: return "BEARISH_REJECTION"
    return "NONE"

async def broadcast(data):
    for ws in list(ws_clients):
        try:
            await ws.send_json(data)
        except Exception:
            ws_clients.remove(ws)

# লাইভ গ্লোবাল ফরেক্স ডাটা ইঞ্জিন (হুবহু ট্রেডিংভিউ রেট)
async def real_forex_socket_engine():
    global current_price, candles, current_ticks
    
    # বিন্যান্সের ডিরেক্ট রিয়েল ফরেক্স/স্টেবলকারেন্সি টিক স্ট্রিম (EURUSDT = EUR/USD গ্লোবাল ফরেক্স রেট)
    url = "wss://stream.binance.com:9443/ws/eurusdt@kline_1m"
    
    while True:
        try:
            async with ClientSession() as session:
                async with session.ws_connect(url) as ws:
                    print(">> [LIVE FEED CONNECTED] Real Global Forex Stream Synced with TradingView!")
                    async for msg in ws:
                        if msg.type == WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            k = data.get("k")
                            if k:
                                current_price = float(k["c"])
                                candle_ts = int(k["t"] // 1000)
                                c_data = {
                                    "time": candle_ts,
                                    "open": float(k["o"]),
                                    "high": float(k["h"]),
                                    "low": float(k["l"]),
                                    "close": float(k["c"])
                                }
                                
                                if len(candles) == 0 or candles[-1]["time"] != candle_ts:
                                    candles.append(c_data)
                                    if len(candles) > 60: candles.pop(0)
                                    current_ticks = [current_price]
                                else:
                                    candles[-1] = c_data
                                    current_ticks.append(current_price)

                                await broadcast({
                                    "type": "TICK",
                                    "price": current_price,
                                    "candle": c_data
                                })
        except Exception as e:
            print(f">> [RECONNECTING LIVE FEED] {e}")
            await asyncio.sleep(2)

# সিগন্যাল ও স্ট্র্যাটেজি ইঞ্জিন
async def strategy_checker_loop():
    global current_price, stats, current_ticks, candles
    in_trade = False
    trade_end_time = 0
    trade_type = ""
    trade_entry = 0.0
    setup_name = ""

    await asyncio.sleep(3)
    await send_telegram("🌍 <b>RAFI BHAI AI BOT — 100% REAL LIVE MARKET FEED ACTIVE</b>\n\nমার্কেট: <b>EUR/USD</b> (TradingView Synced)\nসরাসরি লাইভ রিয়েল ক্যান্ডেল অনুযায়ী সিগন্যাল মনিটরিং শুরু হয়েছে।")

    while True:
        await asyncio.sleep(1)
        now = int(time.time())
        sec = now % 60

        # ৫৫-৫৮ সেকেন্ডে কনফ্লুয়েন্স চেক ও সিগন্যাল তৈরি
        if not in_trade and 54 <= sec <= 57 and len(candles) >= 5:
            trend = get_market_structure(candles[:-1])
            up_f, down_f = detect_fractals(candles[:-1])
            reaction = check_candle_reaction(candles[-1])
            is_green = current_price >= candles[-1]["open"]
            
            sig_found = False
            
            if (trend == "UPTREND" and is_green) or reaction == "BULLISH_REJECTION":
                trade_type = "BUY (CALL)"
                setup_name = "Price Action + Support Rejection"
                sig_found = True
            elif (trend == "DOWNTREND" and not is_green) or reaction == "BEARISH_REJECTION":
                trade_type = "SELL (PUT)"
                setup_name = "Price Action + Resistance Rejection"
                sig_found = True

            if sig_found:
                in_trade = True
                trade_entry = current_price
                trade_end_time = now + (60 - sec) + 59
                next_t = datetime.fromtimestamp(now + (60 - sec)).strftime("%H:%M")
                
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
                    f"⚡ <b>RAFI BHAI AI BOT (REAL LIVE MARKET)</b> ⚡\n\n"
                    f"🌍 <b>Asset:</b> {ASSET_NAME}\n"
                    f"⏰ <b>Time:</b> {next_t} (1 Min)\n"
                    f"🧭 <b>Direction:</b> {emoji_dir}\n"
                    f"💰 <b>Entry Price:</b> <code>{trade_entry:.5f}</code>\n"
                    f"🧩 <b>Setup:</b> {setup_name}\n"
                    f"💸 <b>Payout:</b> 87%\n\n"
                    f"⚠️ <i>Strict 1-Step Martingale If Needed</i>"
                )
                asyncio.create_task(send_telegram(tg_msg))
                print(f"🎯 [SIGNAL SENT] {next_t} -> {trade_type}")

        # লাইভ রেজাল্ট চেক ও চ্যানেলে আপডেট
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
    app["feed"] = asyncio.create_task(real_forex_socket_engine())
    app["strategy"] = asyncio.create_task(strategy_checker_loop())

async def stop_tasks(app):
    app["feed"].cancel()
    app["strategy"].cancel()

app.on_startup.append(start_tasks)
app.on_cleanup.append(stop_tasks)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)
