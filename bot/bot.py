"""FirstHour Telegram bot (Phase 4).

The bot talks to your FirstHour API (the backend folder), so start the API
first, then run this file:

    python bot.py

Setup: create bot/.env containing your token (never commit this file):
    TELEGRAM_BOT_TOKEN=put-your-token-here
    API_URL=http://127.0.0.1:8000
"""

import logging
import os
import re
import sys
from io import BytesIO

import httpx
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()
API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")

# Keep logs quiet: httpx logs full URLs at INFO level, and Telegram URLs
# contain the bot token.
logging.basicConfig(level=logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("firsthour.bot")

# Hijacked-account plans that get a "warn my contacts" button -> API platform
WARN_PLATFORM = {"plan_whatsapp": "whatsapp", "plan_social": "social", "plan_email": "email"}

MAX_MESSAGE = 3800  # Telegram's limit is 4096 characters

URGENCY_ICON = {"critical": "\U0001F534", "high": "\U0001F7E0", "medium": "\U0001F7E1", "low": "\U0001F7E2"}

# ---------------------------------------------------------------------------
# Text shown to the user
# ---------------------------------------------------------------------------

WELCOME = (
    "Karibu / Welcome to FirstHour.\n\n"
    "Umedukuliwa au umetapeliwa? Nitakuongoza hatua kwa hatua katika saa ya kwanza.\n"
    "Been scammed or hacked? I will guide you step by step through the first hour.\n\n"
    "Chagua lugha / Choose your language:"
)

T = {
    "en": {
        "choose_case": "What happened? Choose the option closest to your situation:",
        "menu_btn": "↩ Main menu",
        "lang_btn": "\U0001F310 Change language",
        "evidence_btn": "\U0001F4C4 Create evidence report (PDF)",
        "warn_btn": "\U0001F4E3 Message to warn my contacts",
        "warn_intro": (
            "Here is a message you can send to your contacts and groups. "
            "Press and hold it, tap Copy, then paste it into your chats:"
        ),
        "steps": "WHAT TO DO NOW",
        "report_to": "WHO TO REPORT TO",
        "evidence": "EVIDENCE TO KEEP",
        "skip_btn": "Skip",
        "ev_intro": (
            "I will ask a few short questions to build your evidence report. "
            "Answer what you know. Tap Skip for anything you don't know, "
            "or send /cancel to stop."
        ),
        "ev_bad_amount": "Please send the amount as a number, for example 10000 (or tap Skip).",
        "ev_working": "Creating your PDF...",
        "ev_done": (
            "Your evidence report is ready. Take it to your bank, mobile money provider "
            "or the police, together with your screenshots.\n\n"
            "Privacy tip: your answers were not saved by FirstHour. If you share this phone, "
            "delete this chat after you are done."
        ),
        "ev_cancelled": "Cancelled. Nothing was saved.",
        "api_down": "Sorry, the FirstHour service is not reachable right now. Please try again in a moment.",
        "hint": "Send /start to begin.",
        "help": (
            "FirstHour guides you through the first hour after a scam or hack.\n\n"
            "/start - begin or change language\n"
            "/menu - back to the main menu\n"
            "/cancel - stop the evidence report\n"
            "/skip - skip the current evidence question"
        ),
        "error": "Something went wrong. Please send /start to try again.",
    },
    "sw": {
        "choose_case": "Nini kilitokea? Chagua chaguo linalokaribia hali yako:",
        "menu_btn": "↩ Menyu kuu",
        "lang_btn": "\U0001F310 Badilisha lugha",
        "evidence_btn": "\U0001F4C4 Tengeneza ripoti ya ushahidi (PDF)",
        "warn_btn": "\U0001F4E3 Ujumbe wa kuwaonya watu wangu",
        "warn_intro": (
            "Huu hapa ujumbe unaoweza kuwatumia watu wako na makundi yako. "
            "Bonyeza na ushikilie, gusa Nakili (Copy), kisha ubandike kwenye mazungumzo yako:"
        ),
        "steps": "FANYA HIVI SASA",
        "report_to": "RIPOTI KWA NANI",
        "evidence": "USHAHIDI WA KUHIFADHI",
        "skip_btn": "Ruka",
        "ev_intro": (
            "Nitakuuliza maswali machache mafupi ili kutengeneza ripoti yako ya ushahidi. "
            "Jibu unachokijua. Bonyeza Ruka kwa usichokijua, "
            "au tuma /cancel kusimamisha."
        ),
        "ev_bad_amount": "Tafadhali tuma kiasi kama namba, mfano 10000 (au bonyeza Ruka).",
        "ev_working": "Ninatengeneza PDF yako...",
        "ev_done": (
            "Ripoti yako ya ushahidi iko tayari. Ipeleke benki, kwa mtoa huduma wako wa pesa za simu "
            "au polisi, pamoja na picha zako za skrini.\n\n"
            "Kidokezo cha faragha: majibu yako hayakuhifadhiwa na FirstHour. Ikiwa unashiriki simu hii, "
            "futa mazungumzo haya ukimaliza."
        ),
        "ev_cancelled": "Imesitishwa. Hakuna kilichohifadhiwa.",
        "api_down": "Samahani, huduma ya FirstHour haipatikani sasa hivi. Tafadhali jaribu tena baadaye kidogo.",
        "hint": "Tuma /start kuanza.",
        "help": (
            "FirstHour inakuongoza katika saa ya kwanza baada ya ulaghai au udukuzi.\n\n"
            "/start - anza au badilisha lugha\n"
            "/menu - rudi menyu kuu\n"
            "/cancel - simamisha ripoti ya ushahidi\n"
            "/skip - ruka swali la sasa la ushahidi"
        ),
        "error": "Hitilafu imetokea. Tafadhali tuma /start ujaribu tena.",
    },
}

# (field name, max length, {lang: question})  -- max lengths match the API
EV_FIELDS = [
    ("victim_name", 120, {"en": "What is your full name?", "sw": "Jina lako kamili ni nani?"}),
    ("incident_date", 40, {"en": "What date did it happen? (for example 20 Oct 2026)",
                           "sw": "Ilitokea tarehe gani? (mfano 20 Okt 2026)"}),
    ("amount_kes", 0, {"en": "How much money was lost, in KSh? (numbers only, or Skip)",
                       "sw": "Pesa kiasi gani zilipotea, kwa KSh? (namba tu, au Ruka)"}),
    ("payment_method", 80, {"en": "How was it paid or taken? (for example M-Pesa, bank transfer)",
                            "sw": "Ilitolewa au kuchukuliwa vipi? (mfano M-Pesa, uhamisho wa benki)"}),
    ("transaction_id", 60, {"en": "What is the transaction code or ID?",
                            "sw": "Nambari au msimbo wa muamala ni upi?"}),
    ("bank_or_provider", 120, {"en": "Which bank or provider is involved?",
                               "sw": "Ni benki au mtoa huduma yupi anahusika?"}),
    ("scammer_phone", 30, {"en": "What is the scammer's phone number?",
                           "sw": "Nambari ya simu ya tapeli ni ipi?"}),
    ("description", 3000, {"en": "In your own words, what happened?",
                           "sw": "Kwa maneno yako mwenyewe, nini kilitokea?"}),
]


# ---------------------------------------------------------------------------
# Talking to the FirstHour API
# ---------------------------------------------------------------------------


def get_client() -> httpx.AsyncClient:
    """One place to build the HTTP client (also makes testing easy)."""
    return httpx.AsyncClient(base_url=API_URL, timeout=20)


async def api_get(path: str, **params) -> dict | list:
    async with get_client() as client:
        response = await client.get(path, params=params)
        response.raise_for_status()
        return response.json()


async def api_pdf(payload: dict) -> bytes:
    async with get_client() as client:
        response = await client.post("/evidence/pdf", json=payload)
        response.raise_for_status()
        return response.content


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def lang_of(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    return context.user_data.get("lang")


def chunk_text(text: str, limit: int = MAX_MESSAGE) -> list[str]:
    """Split long text at line breaks so each part fits in one Telegram message."""
    parts, current = [], ""
    for line in text.split("\n"):
        while len(line) > limit:  # a single very long line
            if current:
                parts.append(current.rstrip())
                current = ""
            parts.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) + 1 > limit:
            parts.append(current.rstrip())
            current = ""
        current += line + "\n"
    if current.strip():
        parts.append(current.rstrip())
    return parts


def format_plan(data: dict, lang: str) -> str:
    t = T[lang]
    icon = URGENCY_ICON.get(data.get("urgency", ""), "")
    lines = [f"{icon} {data['title']}".strip(), "", t["steps"]]
    for number, step in enumerate(data["steps"], start=1):
        lines.append(f"{number}. {step}")
    lines += ["", t["report_to"]]
    lines += [f"• {item}" for item in data["report_to"]]
    lines += ["", t["evidence"]]
    lines += [f"• {item}" for item in data["evidence"]]
    lines += ["", data.get("disclaimer", "")]
    return "\n".join(lines).strip()


def button(label: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(label, callback_data=data)


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[button("English", "lang:en"), button("Kiswahili", "lang:sw")]])


async def clear_buttons(query) -> None:
    """Remove the buttons from the message that was just tapped."""
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except BadRequest:
        pass


async def show_welcome(message) -> None:
    await message.reply_text(WELCOME, reply_markup=language_keyboard())


async def show_cases(message, lang: str, edit: bool = False) -> None:
    cases = await api_get("/cases", lang=lang)
    rows = [[button(case["title"], f"case:{case['id']}")] for case in cases]
    rows.append([button(T[lang]["lang_btn"], "langmenu")])
    markup = InlineKeyboardMarkup(rows)
    text = T[lang]["choose_case"]
    if edit:
        try:
            await message.edit_text(text, reply_markup=markup)
            return
        except BadRequest:
            pass
    await message.reply_text(text, reply_markup=markup)


async def show_node(query, data: dict, lang: str) -> None:
    t = T[lang]
    if data["type"] == "question":
        rows = [[button(o["label"], f"node:{data['case']}:{o['next']}")] for o in data["options"]]
        rows.append([button(t["menu_btn"], "menu")])
        try:
            await query.edit_message_text(data["text"], reply_markup=InlineKeyboardMarkup(rows))
        except BadRequest:
            await query.message.reply_text(data["text"], reply_markup=InlineKeyboardMarkup(rows))
        return

    # An action plan: keep the question visible, send the plan as new message(s).
    await clear_buttons(query)
    parts = chunk_text(format_plan(data, lang))
    final_rows = []
    if data["case"] == "hijacked_account" and data["node_id"] in WARN_PLATFORM:
        final_rows.append([button(t["warn_btn"], f"warn:{data['node_id']}")])
    final_rows += [
        [button(t["evidence_btn"], f"ev:{data['case']}:{data['node_id']}")],
        [button(t["menu_btn"], "menu")],
    ]
    for index, part in enumerate(parts):
        is_last = index == len(parts) - 1
        await query.message.reply_text(
            part, reply_markup=InlineKeyboardMarkup(final_rows) if is_last else None
        )


# ---------------------------------------------------------------------------
# Evidence report conversation
# ---------------------------------------------------------------------------


async def ask_next(message, context: ContextTypes.DEFAULT_TYPE) -> None:
    ev = context.user_data["ev"]
    lang = lang_of(context)
    _, _, prompts = EV_FIELDS[ev["i"]]
    markup = InlineKeyboardMarkup([[button(T[lang]["skip_btn"], "skip")]])
    await message.reply_text(f"({ev['i'] + 1}/{len(EV_FIELDS)}) {prompts[lang]}", reply_markup=markup)


async def advance(message, context: ContextTypes.DEFAULT_TYPE, value) -> None:
    ev = context.user_data["ev"]
    key, _, _ = EV_FIELDS[ev["i"]]
    if value is not None:
        ev["data"][key] = value
    ev["i"] += 1
    if ev["i"] < len(EV_FIELDS):
        await ask_next(message, context)
    else:
        await finish_evidence(message, context)


async def finish_evidence(message, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = lang_of(context)
    ev = context.user_data.pop("ev")  # personal data is dropped from memory right here
    await message.reply_text(T[lang]["ev_working"])
    payload = {"lang": lang, "case_id": ev["case"], "plan_id": ev["plan"], **ev["data"]}
    pdf_bytes = await api_pdf(payload)
    await message.reply_document(document=BytesIO(pdf_bytes), filename="firsthour-evidence-report.pdf")
    await message.reply_text(
        T[lang]["ev_done"],
        reply_markup=InlineKeyboardMarkup([[button(T[lang]["menu_btn"], "menu")]]),
    )


def parse_amount(text: str) -> float | None:
    cleaned = re.sub(r"(?i)ksh?s?\.?|/=|,|\s", "", text)
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return value if 0 <= value <= 1_000_000_000 else None


# ---------------------------------------------------------------------------
# Telegram handlers
# ---------------------------------------------------------------------------


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("ev", None)
    await show_welcome(update.message)


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = lang_of(context)
    if lang is None:
        await show_welcome(update.message)
        return
    context.user_data.pop("ev", None)
    await show_cases(update.message, lang)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(T[lang_of(context) or "en"]["help"])


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = lang_of(context) or "en"
    if context.user_data.pop("ev", None) is not None:
        await update.message.reply_text(T[lang]["ev_cancelled"])
    else:
        await update.message.reply_text(T[lang]["hint"])


async def cmd_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = lang_of(context) or "en"
    if "ev" not in context.user_data:
        await update.message.reply_text(T[lang]["hint"])
        return
    await advance(update.message, context, None)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = lang_of(context)
    if lang is None:
        await show_welcome(update.message)
        return
    ev = context.user_data.get("ev")
    if ev is None:
        await update.message.reply_text(T[lang]["hint"])
        return

    key, max_len, _ = EV_FIELDS[ev["i"]]
    text = (update.message.text or "").strip()
    if key == "amount_kes":
        amount = parse_amount(text)
        if amount is None:
            await update.message.reply_text(T[lang]["ev_bad_amount"])
            return
        await advance(update.message, context, amount)
    else:
        await advance(update.message, context, text[:max_len] or None)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    parts = (query.data or "").split(":")
    action = parts[0]

    if action == "lang" and len(parts) == 2 and parts[1] in T:
        context.user_data["lang"] = parts[1]
        await clear_buttons(query)
        await show_cases(query.message, parts[1])
        return

    lang = lang_of(context)
    if lang is None:  # for example the bot was restarted and forgot the language
        await show_welcome(query.message)
        return

    if action == "langmenu":
        await query.edit_message_text(WELCOME, reply_markup=language_keyboard())
    elif action == "menu":
        context.user_data.pop("ev", None)
        await show_cases(query.message, lang, edit=False)
        await clear_buttons(query)
    elif action == "case" and len(parts) == 2:
        data = await api_get(f"/cases/{parts[1]}/start", lang=lang)
        await show_node(query, data, lang)
    elif action == "node" and len(parts) == 3:
        data = await api_get(f"/cases/{parts[1]}/nodes/{parts[2]}", lang=lang)
        await show_node(query, data, lang)
    elif action == "ev" and len(parts) == 3:
        context.user_data["ev"] = {"case": parts[1], "plan": parts[2], "i": 0, "data": {}}
        await clear_buttons(query)
        await query.message.reply_text(T[lang]["ev_intro"])
        await ask_next(query.message, context)
    elif action == "warn" and len(parts) == 2 and parts[1] in WARN_PLATFORM:
        data = await api_get("/templates/warn-contacts", lang=lang, platform=WARN_PLATFORM[parts[1]])
        await query.message.reply_text(T[lang]["warn_intro"])
        await query.message.reply_text(
            data["message"],
            reply_markup=InlineKeyboardMarkup([[button(T[lang]["menu_btn"], "menu")]]),
        )
    elif action == "skip":
        if "ev" not in context.user_data:
            await clear_buttons(query)
            return
        await clear_buttons(query)
        await advance(query.message, context, None)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error = context.error
    # Log the error type only: messages can contain personal details or the token.
    log.warning("Handler error: %s", type(error).__name__)
    message = None
    if isinstance(update, Update):
        message = update.effective_message
    if message is None:
        return
    lang = (context.user_data or {}).get("lang") or "en"
    key = "api_down" if isinstance(error, httpx.HTTPError) else "error"
    try:
        await message.reply_text(T[lang][key])
    except Exception:  # never let the error handler crash
        pass


def build_application(token: str) -> Application:
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("skip", cmd_skip))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_error_handler(on_error)
    return app


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token or token == "put-your-token-here":
        print("Missing token. Create a file named .env in the bot folder containing:")
        print("TELEGRAM_BOT_TOKEN=your-token-from-BotFather")
        sys.exit(1)
    print(f"FirstHour bot starting. API: {API_URL}")
    print("Press Ctrl + C to stop.")
    build_application(token).run_polling()


if __name__ == "__main__":
    main()
