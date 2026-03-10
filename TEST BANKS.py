import yfinance as yf
import telebot
from telebot import types
import requests
import warnings

warnings.filterwarnings("ignore")

# ─── CONFIGURATION (משתני סביבה מאובטחים) ──────────────────
# הקוד ימשוך את הערכים האלו מה-GitHub Secrets בזמן הריצה
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GM_TOKEN = os.getenv("GM_TOKEN")

PLAY_STORE_URL = "https://play.google.com/store/apps/details?id=com.leumi.iLeumiTrade.UI"

# בדיקה בסיסית שהסודות נטענו
if not BOT_TOKEN or not CHAT_ID:
    print("❌ Critical Error: Missing Telegram Secrets!")
    # במחשב האישי שלך אתה יכול לשים את הטוקן פה זמנית לבדיקה, 
    # אבל לעולם אל תעלה אותו ל-GitHub ככה!
    # BOT_TOKEN = "כאן הטוקן שלך רק לבדיקה מקומית"

bot = telebot.TeleBot(BOT_TOKEN)

BANKS = {
    "POLI.TA": {"name": "Hapoalim", "weight": 0.335},
    "LUMI.TA": {"name": "Leumi",    "weight": 0.285},
    "MZTF.TA": {"name": "Mizrahi", "weight": 0.175},
    "DSCT.TA": {"name": "Discount", "weight": 0.135},
    "FIBI.TA": {"name": "First Intl","weight": 0.070},
}

# ─── המודלים הנכונים לפי התשובה מגוגל ───────────────────────
GEMINI_MODELS = [
    "gemini-2.5-flash",   # הכי חדש וחינמי
    "gemini-2.0-flash",   # גיבוי
    "gemini-1.5-flash",   # גיבוי ישן
]


def call_gemini(prompt: str) -> str | None:
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 500, "temperature": 0.85},
    }

    for model in GEMINI_MODELS:
        url = (
            f"https://generativelanguage.googleapis.com"
            f"/v1beta/models/{model}:generateContent"
            f"?key={GEMINI_API_KEY}"
        )
        try:
            print(f"⏳ Trying: {model}")
            resp = requests.post(url, headers=headers, json=payload, timeout=20)

            if resp.status_code == 200:
                data = resp.json()
                text = (
                    data.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "")
                    .strip()
                )
                if text:
                    print(f"✅ Success with: {model}")
                    return text

            elif resp.status_code == 404:
                print(f"❌ 404 on {model}, trying next...")
                continue
            else:
                print(f"❌ {resp.status_code}: {resp.text[:150]}")
                continue

        except requests.exceptions.Timeout:
            print(f"⏱️ Timeout on {model}")
            continue
        except Exception as e:
            print(f"❌ Exception: {e}")
            continue

    return None


def get_gemini_analysis(bank_results: list, trend: float) -> str | None:
    summary = ", ".join([f"{b['name']} {b['change']:.2f}%" for b in bank_results])
    prompt = (
        f"You are a senior Wall Street analyst covering Israeli equities. "
        f"Today the Israeli banking sector moved {trend:+.2f}% overall. "
        f"Individual moves: {summary}. "
        f"Write 2 sentences of institutional-grade analysis. "
        f"DO NOT use any numbers, percentages, or digits in your response. "
        f"Mention which bank led losses by name, suggest a macro cause, end with outlook. "
        f"Bloomberg terminal style. End with a period."
    )
    return call_gemini(prompt)


def get_accurate_change(symbol: str):
    try:
        df = yf.download(symbol, period="7d", interval="1d", progress=False)
        if len(df) >= 2:
            current_close = float(df["Close"].iloc[-1])
            prev_close    = float(df["Close"].iloc[-2])
            change = ((current_close - prev_close) / prev_close) * 100
            return current_close, change
    except Exception as e:
        print(f"⚠️ yfinance error for {symbol}: {e}")
    return None, None


def run():
    print("🚀 Starting Israel Banking Sector Bot...")
    results, weighted_sum = [], 0.0

    for symbol, info in BANKS.items():
        price, change = get_accurate_change(symbol)
        if price is not None:
            results.append({"name": info["name"], "change": change})
            weighted_sum += change * info["weight"]

    if not results:
        print("❌ No data. Aborting.")
        return

    ai_insight = get_gemini_analysis(results, weighted_sum)

    if not ai_insight:
        leader = max(results, key=lambda x: abs(x["change"]))
        direction = "advances" if weighted_sum > 0 else "declines"
        ai_insight = (
            f"The Israeli banking sector {direction} {weighted_sum:+.2f}% "
            f"with {leader['name']} leading at {leader['change']:+.2f}%, "
            f"reflecting broader market sentiment shifts."
        )

    # ניקוי תווים שמשברים Markdown של Telegram
    for ch in ["_", "*", "`", "["]:
        ai_insight = ai_insight.replace(ch, "")

    icon = "🟢" if weighted_sum > 0 else "🔴"
    lines = [
        "🏛 *ISRAEL BANKING SECTOR: INTELLIGENCE REPORT*",
        f"📊 Market Trend: *{weighted_sum:+.2f}%* {icon}",
        "──────────────────",
    ]
    for b in results:
        b_icon = "🟢" if b["change"] > 0 else "🔴"
        lines.append(f"{b_icon} {b['name']}: `{b['change']:+.2f}%`")

    lines += [
        "──────────────────",
        "🤖 *AI STRATEGIC INSIGHT (Gemini 2.5):*",
        f"{ai_insight}",
    ]

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🚀 Open Leumi Trade", url=PLAY_STORE_URL))

    try:
        bot.send_message(CHAT_ID, "\n".join(lines), parse_mode="Markdown", reply_markup=markup)
        print("✅ Message sent!")
    except Exception as e:
        print(f"❌ Telegram Error: {e}")


if __name__ == "__main__":
    run()
