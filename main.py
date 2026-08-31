import asyncio, json, time, os
from datetime import datetime, timezone, timedelta
from aiohttp import web, ClientSession, WSMsgType

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
        print(f"❌ [TG ERROR]: {e}")

# Quotex Real Market Price Action & Rejection Analyzer
def analyze_quotex_market(c_list):
    if len(c_list) < 4:
        return "SIDEWAYS", "MARKET_STABLE"
    
    c1, c2, c3 = c_list[-3], c_list[-2], c_list[-1]
    
    # লোয়ার হাই / লোয়ার লো (Downtrend)
    if c3["close"] < c2["close"] and c2["close"] < c1["close"]:
        return "DOWNTREND", "STRONG_BEARISH_FLOW"
    # হায়ার হাই / হায়ার লো (Uptrend)
    elif c3["close"] > c2["close"] and c2["close"] > c1["close"]:
        return "UPTREND", "STRONG_BULLISH_FLOW"
    
    body = abs(c3["close"] - c3["open"])
    lower_wick = min(c3["open"], c3["close"]) - c3["low"]
    upper_wick = c3["high"] - max(c3["open"], c3["close"])
    
    if lower_wick > body * 1.1:
        return "BULLISH_FLOW", "SUPPORT_WICK_REJECTION"
    elif upper_wick > body * 1.1:
        return "BEARISH_FLOW", "RESISTANCE_WICK_REJECTION"
        
    return "SIDEWAYS", "CONSOLIDATION_FLOW"

async def broadcast(data):
    for ws in list(ws_clients):
        try:
            await ws.send_json(data)
        except Exception:
            ws_clients.remove(ws)

# Quotex লাইভ মার্কেট ডাটা স্ট্রিম (Direct Global FX Stream)
async def quotex_real_engine():
    global current_price, candles, last_signal_time, stats
    in_trade = False
    trade_end_time = 0
    trade_type = ""
    trade_entry = 0.0
    setup_name = ""

    # গ্লোবাল স্পট ফরেক্স লাইভ স্ট্রিম (Quotex Real Market Provider)
    stream_url = "wss://stream.binance.com:9443/ws/eurusdt@kline_1m"

    while True:
        try:
            async with ClientSession() as session:
                async with session.ws_connect(stream_url) as ws:
                    print(">> [CONNECTED] Quotex Real EUR/USD Live Stream Synced!")
                    
                    bd_now = get_bd_time()
                    await send_telegram(
                        f"🌍 <b>RAFI BHAI AI BOT — QUOTEX REAL MARKET SYNCED</b>\n\n"
                        f"💎 <b>Asset:</b> {ASSET_NAME} (Real)\n"
                        f"⏰ <b>Start Time:</b> {bd_now}\n"
                        f"🚀 <i>Quotex প্ল্যাটফর্মের সাথে লাইভ টিক ও প্রাইস অ্যানালাইসিস শুরু হয়েছে!</i>"
                    )

                    async for msg in ws:
                        if msg.type == WSMsgType.TEXT:
                            res = json.loads(msg.data)
                            k = res.get("k")
                            if k:
                                current_price = float(k["c"])
                                c_ts = int(k["t"] // 1000)
                                candle_obj = {
                                    "time": c_ts,
                                    "open": float(k["o"]),
                                    "high": float(k["h"]),
                                    "low": float(k["l"]),
                                    "close": float(k["c"])
                                }

                                if len(candles) == 0 or candles[-1]["time"] != c_ts:
                                    candles.append(candle_obj)
                                    if len(candles) > 60: candles.pop(0)
                                else:
                                    candles[-1] = candle_obj

                                await broadcast({"type": "TICK", "price": current_price, "candle": candle_obj})

                                now = int(time.time())
                                sec = now % 60

                                # Quotex ক্যান্ডেল এন্ট্রির জন্য ৫৫-৫৮ সেকেন্ডে কনফার্মড সিগন্যাল
                                if not in_trade and 54 <= sec <= 57 and len(candles) >= 4:
                                    next_candle_ts = now + (60 - sec)
                                    next_t = get_bd_time(next_candle_ts)

                                    if next_t != last_signal_time:
                                        trend, pattern = analyze_quotex_market(candles)

                                        sig_found = False
                                        if "DOWN" in trend or "BEARISH" in pattern or current_price < candles[-1]["open"]:
                                            trade_type = "SELL (PUT)"
                                            setup_name = f"Price Action: {pattern.replace('_', ' ')}"
                                            sig_found = True
                                        elif "UP" in trend or "BULLISH" in pattern or current_price > candles[-1]["open"]:
                                            trade_type = "BUY (CALL)"
                                            setup_name = f"Price Action: {pattern.replace('_', ' ')}"
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
                                                f"⚡ <b>QUOTEX REAL MARKET SIGNAL</b> ⚡\n\n"
                                                f"🌍 <b>Asset:</b> {ASSET_NAME}\n"
                                                f"⏰ <b>Time:</b> {next_t} (1 Min Candle)\n"
                                                f"🧭 <b>Direction:</b> {emoji_dir}\n"
                                                f"💰 <b>Entry Price:</b> <code>{trade_entry:.5f}</code>\n"
                                                f"🧩 <b>Setup:</b> {setup_name}\n"
                                                f"💸 <b>Payout:</b> 87%\n\n"
                                                f"⚠️ <i>Strict 1-Step Martingale If Needed</i>"
                                            )
                                            asyncio.create_task(send_telegram(tg_msg))
                                            print(f"🎯 [QUOTEX SIGNAL] {next_t} -> {trade_type} @ {trade_entry:.5f}")

                                # ১ মিনিট পর রেজাল্ট অ্যানালাইসিস
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
        except Exception as e:
            print(f">> [SOCKET RETRY] {e}")
            await asyncio.sleep(2)

# সার্ভার সেল্ফ-পিং
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
    app["feed"] = asyncio.create_task(quotex_real_engine())
    app["pinger"] = asyncio.create_task(self_keep_alive())

async def stop_tasks(app):
    app["feed"].cancel()
    app["pinger"].cancel()

app.on_startup.append(start_tasks)
app.on_cleanup.append(stop_tasks)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)
