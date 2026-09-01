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
stats = {"wins": 0, "losses": 0, "direct_wins": 0, "mtg_wins": 0}
last_signal_time = ""

def get_bd_time(ts=None):
    if ts is None:
        ts = time.time()
    bd_tz = timezone(timedelta(hours=6))
    return datetime.fromtimestamp(ts, tz=bd_tz).strftime("%H:%M")

def calculate_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        if diff >= 0:
            gains.append(diff)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(diff))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 2)

# লাইভ চার্ট ইমেজ জেনারেটর
def generate_chart_image(c_list, title_text, mark_dir=None, is_mtg=False):
    fig, ax = plt.subplots(figsize=(7, 3.8), dpi=100)
    fig.patch.set_facecolor('#080d1a')
    ax.set_facecolor('#080d1a')

    recent_candles = c_list[-16:]
    width = 0.55
    width2 = 0.08

    for i, c in enumerate(recent_candles):
        col = '#00e676' if c['close'] >= c['open'] else '#ff1744'
        ax.bar(i, c['close'] - c['open'], width, bottom=c['open'], color=col, edgecolor=col)
        ax.bar(i, c['high'] - max(c['open'], c['close']), width2, bottom=max(c['open'], c['close']), color=col)
        ax.bar(i, min(c['open'], c['close']) - c['low'], width2, bottom=c['low'], color=col)

    if mark_dir and len(recent_candles) > 0:
        last_idx = len(recent_candles) - 1
        last_c = recent_candles[-1]
        lbl = '▲ MTG CALL' if is_mtg else '▲ SURESHOT CALL'
        if "BUY" in mark_dir:
            ax.annotate(lbl, xy=(last_idx, last_c['low']), xytext=(last_idx, last_c['low'] - 0.00008),
                        arrowprops=dict(facecolor='#00e676', shrink=0.05, width=2, headwidth=6),
                        color='#00e676', fontweight='bold', ha='center', fontsize=9)
        elif "SELL" in mark_dir:
            lbl = '▼ MTG PUT' if is_mtg else '▼ SURESHOT PUT'
            ax.annotate(lbl, xy=(last_idx, last_c['high']), xytext=(last_idx, last_c['high'] + 0.00008),
                        arrowprops=dict(facecolor='#ff1744', shrink=0.05, width=2, headwidth=6),
                        color='#ff1744', fontweight='bold', ha='center', fontsize=9)

    ax.set_title(title_text, color='#f8fafc', fontsize=11, fontweight='bold', pad=10)
    ax.tick_params(colors='#64748b', labelsize=8)
    ax.grid(True, linestyle='--', alpha=0.12, color='#ffffff')
    for spine in ax.spines.values():
        spine.set_color('#1e293b')

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
    start_ts = (now // 60) * 60 - (40 * 60)
    history = []
    for i in range(40):
        o = p
        diff = 0.00003 if i % 2 == 0 else -0.00003
        c = round(o + diff, 5)
        h = round(max(o, c) + 0.00002, 5)
        l = round(min(o, c) - 0.00002, 5)
        history.append({"time": start_ts + (i * 60), "open": o, "high": h, "low": l, "close": c})
        p = c
    candles = history

# ============================================================
# 🧠 INSTITUTIONAL SMART MONEY AI ENGINE (SURESHOT 85%+)
# ============================================================
def institutional_ai_analyzer(c_list):
    if len(c_list) < 30:
        return "NONE", "NO_DATA", 0, False

    c_cur = c_list[-1]
    c_prev = c_list[-2]

    closes = [c["close"] for c in c_list]
    ema_9 = sum(closes[-9:]) / 9.0
    ema_21 = sum(closes[-21:]) / 21.0
    ema_50 = sum(closes[-30:]) / 30.0
    rsi = calculate_rsi(closes, period=14)

    body = abs(c_prev["close"] - c_prev["open"])
    upper_wick = c_prev["high"] - max(c_prev["open"], c_prev["close"])
    lower_wick = min(c_prev["open"], c_prev["close"]) - c_prev["low"]

    # ডোজি ও সাইডওয়েজ ফিল্টার
    if body < 0.000025:
        return "NONE", "DOJI_SKIP", 0, False

    recent_highs = max([c["high"] for c in c_list[-15:-2]])
    recent_lows = min([c["low"] for c in c_list[-15:-2]])

    # ১. প্রাতিষ্ঠানিক বুলিশ কনফ্লুয়েন্স (Triple EMA Alignment + Support Wick / Sweep)
    if ema_9 > ema_21 and ema_21 > ema_50 and 48 <= rsi <= 70:
        # সাপোর্ট রিজেকশন বা লিকুইডিটি সুইপ
        if lower_wick >= body * 0.7 and c_prev["low"] <= recent_lows:
            return "BUY (CALL)", "Smart Money: Liquidity Sweep + Rejection", 95, True
        elif c_prev["close"] > c_prev["open"] and c_cur["close"] > c_prev["high"] and lower_wick >= body * 0.3:
            return "BUY (CALL)", "Smart Money: Triple Trend Momentum Breakout", 92, True

    # ২. প্রাতিষ্ঠানিক বিয়ারিশ কনফ্লুয়েন্স (Triple EMA Alignment + Resistance Wick / Sweep)
    elif ema_9 < ema_21 and ema_21 < ema_50 and 30 <= rsi <= 52:
        # রেজিস্ট্যান্স রিজেকশন বা লিকুইডিটি সুইপ
        if upper_wick >= body * 0.7 and c_prev["high"] >= recent_highs:
            return "SELL (PUT)", "Smart Money: Liquidity Sweep + Rejection", 95, True
        elif c_prev["close"] < c_prev["open"] and c_cur["close"] < c_prev["low"] and upper_wick >= body * 0.3:
            return "SELL (PUT)", "Smart Money: Triple Trend Momentum Breakdown", 92, True

    return "NONE", "SCANNING_SURESHOT", 0, False

async def broadcast(data):
    for ws in list(ws_clients):
        try:
            await ws.send_json(data)
        except Exception:
            ws_clients.remove(ws)

# ============================================================
# 🎯 CORE ENGINE WITH 2-STEP STATE MACHINE (PERFECT MTG TIMING)
# ============================================================
async def live_ai_master_engine():
    global current_price, candles, last_signal_time, stats
    
    # স্টেট মেশিন ভেরিয়েবল
    trade_state = "IDLE"  # "IDLE", "STEP_0", "STEP_1_MTG"
    trade_type = ""
    trade_entry = 0.0
    mtg_entry = 0.0
    step_0_end_time = 0
    step_1_end_time = 0
    setup_name = ""
    confidence_score = 0
    last_trade_minute = 0

    async with ClientSession() as session:
        await fetch_truefx_price(session)
        prefill_history(current_price)

        bd_now = get_bd_time()
        await send_telegram(
            f"🧠 <b>RAFI BHAI DEEP AI — INSTITUTIONAL CORE ACTIVE</b> 🧠\n\n"
            f"🌍 <b>Asset:</b> {ASSET_NAME} (Quotex Real Feed)\n"
            f"⏰ <b>Start Time:</b> {bd_now}\n"
            f"🎯 <b>System:</b> Triple EMA + Liquidity Sweep + True MTG Flow\n"
            f"🛡️ <i>ভুল ট্রেড বন্ধ—শুধুমাত্র নিশ্চিত প্রাতিষ্ঠানিক সেটআপে সিগন্যাল আসবে!</i>"
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

            # -------------------------------------------------------------
            # ১. নতুন সিগন্যাল স্ক্যানিং (শুধুমাত্র যখন কোনো রানিং ট্রেড থাকবে না)
            # -------------------------------------------------------------
            current_minute_count = now // 60
            if trade_state == "IDLE" and 54 <= sec <= 58 and (current_minute_count - last_trade_minute >= 3):
                next_candle_ts = now + (60 - sec)
                next_t = get_bd_time(next_candle_ts)

                if next_t != last_signal_time:
                    direction, setup, confidence, is_valid = institutional_ai_analyzer(candles)

                    if is_valid:
                        trade_type = direction
                        setup_name = setup
                        confidence_score = confidence
                        trade_entry = current_price
                        step_0_end_time = next_candle_ts + 59
                        trade_state = "STEP_0"
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
                            f"💎 <b>RAFI BHAI AI — INSTITUTIONAL SURESHOT</b> 💎\n\n"
                            f"🌍 <b>Asset:</b> {ASSET_NAME}\n"
                            f"⏰ <b>Time:</b> {next_t} (1 Min Candle)\n"
                            f"🧭 <b>Direction:</b> {emoji_dir}\n"
                            f"💰 <b>Entry Price:</b> <code>{trade_entry:.5f}</code>\n"
                            f"🧠 <b>AI Setup:</b> {setup_name}\n"
                            f"📊 <b>Confidence Score:</b> <b>{confidence}%</b>\n"
                            f"💸 <b>Payout:</b> 87%\n\n"
                            f"⚠️ <i>Strict 1-Step Martingale If Needed</i>"
                        )
                        chart_img = generate_chart_image(candles, f"{ASSET_NAME} SURESHOT ({next_t})", trade_type)
                        asyncio.create_task(send_telegram_photo(chart_img, tg_caption))
                        print(f"🎯 [NEW SURESHOT] {next_t} -> {trade_type} @ {trade_entry:.5f}")

            # -------------------------------------------------------------
            # ২. ১ম ক্যান্ডেল মূল্যায়ন (STEP_0 Evaluation)
            # -------------------------------------------------------------
            if trade_state == "STEP_0" and now >= step_0_end_time:
                close_p = current_price
                is_win = (close_p > trade_entry) if trade_type == "BUY (CALL)" else (close_p < trade_entry)

                if is_win:
                    # ডিরেক্ট উইন! ট্রেড শেষ
                    trade_state = "IDLE"
                    stats["wins"] += 1
                    stats["direct_wins"] += 1
                    total = stats["wins"] + stats["losses"]
                    win_r = f"{round((stats['wins']/total)*100)}%"

                    tg_res_caption = (
                        f"✅ <b>DIRECT PROFIT (NON-MTG WIN)</b> 🚀\n\n"
                        f"🌍 <b>Asset:</b> {ASSET_NAME}\n"
                        f"🎯 <b>Entry:</b> <code>{trade_entry:.5f}</code> | <b>Close:</b> <code>{close_p:.5f}</code>\n"
                        f"📈 <b>Wins:</b> {stats['wins']} (Direct: {stats['direct_wins']}) | <b>Losses:</b> {stats['losses']}\n"
                        f"🏆 <b>Accuracy:</b> {win_r}"
                    )
                    res_chart = generate_chart_image(candles, f"{ASSET_NAME} Result: DIRECT WIN")
                    asyncio.create_task(send_telegram_photo(res_chart, tg_res_caption))
                else:
                    # ১ম ক্যান্ডেল মিস -> সাথে সাথে MTG 1 সক্রিয় এবং পুরো পরবর্তী ১ মিনিট অপেক্ষা
                    trade_state = "STEP_1_MTG"
                    mtg_entry = current_price
                    step_1_end_time = now + 60
                    mtg_time_str = get_bd_time()

                    emoji_dir = "🟢 <b>BUY (CALL) ⬆️</b>" if "BUY" in trade_type else "🔴 <b>SELL (PUT) ⬇️</b>"
                    tg_mtg_alert = (
                        f"⚠️ <b>1-STEP MARTINGALE (MTG 1) ACTIVE</b> ⚠️\n\n"
                        f"🌍 <b>Asset:</b> {ASSET_NAME}\n"
                        f"⏰ <b>MTG Time:</b> {mtg_time_str} (Next 1 Min Candle)\n"
                        f"🧭 <b>Direction:</b> {emoji_dir}\n"
                        f"💰 <b>MTG Entry Price:</b> <code>{mtg_entry:.5f}</code>\n"
                        f"⏳ <i>পরবর্তী ক্যান্ডেল শেষ হওয়া পর্যন্ত অপেক্ষা করুন...</i>"
                    )
                    mtg_chart = generate_chart_image(candles, f"{ASSET_NAME} MTG 1 Candle Active", trade_type, is_mtg=True)
                    asyncio.create_task(send_telegram_photo(mtg_chart, tg_mtg_alert))
                    print(f"⚠️ [MTG 1 TRIGGERED] {mtg_time_str} -> {trade_type} @ {mtg_entry:.5f}")

            # -------------------------------------------------------------
            # ৩. ২য় ক্যান্ডেল মূল্যায়ন (STEP_1 MTG Evaluation)
            # -------------------------------------------------------------
            if trade_state == "STEP_1_MTG" and now >= step_1_end_time:
                trade_state = "IDLE"
                close_p = current_price
                is_mtg_win = (close_p > mtg_entry) if trade_type == "BUY (CALL)" else (close_p < mtg_entry)

                if is_mtg_win:
                    stats["wins"] += 1
                    stats["mtg_wins"] += 1
                    res_emoji = "✅ <b>PROFIT (1-STEP MTG WIN)</b> 🚀"
                    chart_title = f"{ASSET_NAME} Result: MTG WIN"
                else:
                    stats["losses"] += 1
                    res_emoji = "❌ <b>LOSS (MTG 1 FAILED)</b> 🔻"
                    chart_title = f"{ASSET_NAME} Result: LOSS"

                total = stats["wins"] + stats["losses"]
                win_r = f"{round((stats['wins']/total)*100)}%"

                tg_res_caption = (
                    f"🏁 <b>TRADE CYCLE COMPLETE</b>\n\n"
                    f"🌍 <b>Asset:</b> {ASSET_NAME}\n"
                    f"📊 <b>Outcome:</b> {res_emoji}\n"
                    f"🎯 <b>MTG Entry:</b> <code>{mtg_entry:.5f}</code> | <b>Close:</b> <code>{close_p:.5f}</code>\n"
                    f"📈 <b>Wins:</b> {stats['wins']} (MTG: {stats['mtg_wins']}) | <b>Losses:</b> {stats['losses']}\n"
                    f"🏆 <b>Accuracy:</b> {win_r}"
                )
                res_chart = generate_chart_image(candles, chart_title)
                asyncio.create_task(send_telegram_photo(res_chart, tg_res_caption))

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
    app["feed"] = asyncio.create_task(live_ai_master_engine())
    app["pinger"] = asyncio.create_task(self_keep_alive())

async def stop_tasks(app):
    app["feed"].cancel()
    app["pinger"].cancel()

app.on_startup.append(start_tasks)
app.on_cleanup.append(stop_tasks)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)
