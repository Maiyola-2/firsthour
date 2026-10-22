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
from datetime import datetime, timedelta
from io import BytesIO

import httpx
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest, Forbidden, NetworkError, TimedOut
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

INSTITUTIONS = ("bank", "mobile_money", "telecom", "police", "other")
EN_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
SW_MONTHS = ["Jan", "Feb", "Mac", "Apr", "Mei", "Jun", "Jul", "Ago", "Sep", "Okt", "Nov", "Des"]

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
            "/cancel - stop what you are doing\n"
            "/skip - skip the current question\n"
            "/mycases - your saved follow-ups\n"
            "/deletemydata - erase everything saved about you"
        ),
        "error": "Something went wrong. Please send /start to try again.",
        "track_btn": "\u23F0 Track this case and set a reminder",
        "track_inst_q": "Who did you report this to? I will help you follow up.",
        "inst": {
            "bank": "Bank",
            "mobile_money": "Mobile money provider",
            "telecom": "Mobile network (SIM or line)",
            "police": "Police / DCI",
            "other": "Other",
        },
        "track_ref_q": "What reference number did they give you? Send it, or tap Skip.",
        "track_days_q": "When should I remind you to follow up?\n\n{note}",
        "days_btn": "{n} days",
        "track_saved": "Saved. I will remind you on {date}. Send /mycases any time to see your follow-ups.",
        "mycases_title": "Your follow-ups:",
        "mycases_empty": "You have no saved follow-ups yet. After an action plan, tap Track this case.",
        "status_waiting": "waiting",
        "status_resolved": "resolved",
        "fu_line": "{n}. {inst} | Ref: {ref} | Follow up: {date} | {status}",
        "no_ref": "none",
        "fu_resolved_btn": "\u2705 Resolved",
        "fu_noreply_btn": "\u274C No reply: what next?",
        "fu_snooze_btn": "\u23F0 Remind me in 3 days",
        "reminder": (
            "\u23F0 Follow-up reminder\n\nYou asked me to remind you about your report to "
            "{inst} (reference: {ref}).\n\nDid they reply?"
        ),
        "esc_title": "WHAT TO DO NEXT: {inst}",
        "esc_sources": "Official sources:",
        "esc_unverified": "Note: this is general advice, not from an official source.",
        "esc_verified": "Checked against official sources on {date}.",
        "fu_marked": "Marked as resolved. Well done for following up.",
        "fu_snoozed": "Okay. I will remind you again on {date}.",
        "not_found": "I could not find that follow-up.",
        "use_buttons": "Please tap one of the buttons above, or send /cancel.",
        "delete_confirm": "This will permanently erase everything saved about you. Continue?",
        "delete_yes": "Yes, erase everything",
        "delete_no": "No, keep it",
        "delete_done": "Done. Everything saved about you was erased ({n} follow-ups).",
        "delete_kept": "Okay, nothing was erased.",
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
            "/cancel - simamisha unachofanya\n"
            "/skip - ruka swali la sasa\n"
            "/mycases - ufuatiliaji wako uliohifadhiwa\n"
            "/deletemydata - futa kila kitu kilichohifadhiwa kukuhusu"
        ),
        "error": "Hitilafu imetokea. Tafadhali tuma /start ujaribu tena.",
        "track_btn": "\u23F0 Fuatilia kesi hii na uweke ukumbusho",
        "track_inst_q": "Uliripoti kwa nani? Nitakusaidia kufuatilia.",
        "inst": {
            "bank": "Benki",
            "mobile_money": "Mtoa huduma wa pesa za simu",
            "telecom": "Kampuni ya simu (laini au SIM)",
            "police": "Polisi / DCI",
            "other": "Nyingine",
        },
        "track_ref_q": "Walikupa nambari gani ya kumbukumbu? Itume, au bonyeza Ruka.",
        "track_days_q": "Nikukumbushe lini kufuatilia?\n\n{note}",
        "days_btn": "siku {n}",
        "track_saved": "Imehifadhiwa. Nitakukumbusha tarehe {date}. Tuma /mycases wakati wowote kuona ufuatiliaji wako.",
        "mycases_title": "Ufuatiliaji wako:",
        "mycases_empty": "Bado huna ufuatiliaji uliohifadhiwa. Baada ya mpango wa hatua, bonyeza Fuatilia kesi hii.",
        "status_waiting": "inasubiri",
        "status_resolved": "imetatuliwa",
        "fu_line": "{n}. {inst} | Kumb: {ref} | Fuatilia: {date} | {status}",
        "no_ref": "hakuna",
        "fu_resolved_btn": "\u2705 Imetatuliwa",
        "fu_noreply_btn": "\u274C Hakuna jibu: nini kifuatacho?",
        "fu_snooze_btn": "\u23F0 Nikumbushe baada ya siku 3",
        "reminder": (
            "\u23F0 Ukumbusho wa kufuatilia\n\nUliniomba nikukumbushe kuhusu ripoti yako kwa "
            "{inst} (nambari ya kumbukumbu: {ref}).\n\nWalijibu?"
        ),
        "esc_title": "FANYA HIVI BAADA YA HAPA: {inst}",
        "esc_sources": "Vyanzo rasmi:",
        "esc_unverified": "Kumbuka: huu ni ushauri wa jumla, si kutoka chanzo rasmi.",
        "esc_verified": "Imekaguliwa dhidi ya vyanzo rasmi tarehe {date}.",
        "fu_marked": "Imewekwa kuwa imetatuliwa. Hongera kwa kufuatilia.",
        "fu_snoozed": "Sawa. Nitakukumbusha tena tarehe {date}.",
        "not_found": "Sikuweza kupata ufuatiliaji huo.",
        "use_buttons": "Tafadhali bonyeza moja ya vitufe hapo juu, au tuma /cancel.",
        "delete_confirm": "Hii itafuta kabisa kila kitu kilichohifadhiwa kukuhusu. Endelea?",
        "delete_yes": "Ndiyo, futa kila kitu",
        "delete_no": "Hapana, vihifadhi",
        "delete_done": "Imekamilika. Kila kitu kilichohifadhiwa kukuhusu kimefutwa (ufuatiliaji {n}).",
        "delete_kept": "Sawa, hakuna kilichofutwa.",
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
    key = os.getenv("FIRSTHOUR_API_KEY", "")
    headers = {"X-API-Key": key} if key else {}
    return httpx.AsyncClient(base_url=API_URL, timeout=20, headers=headers)


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


async def api_post(path: str, payload: dict | None = None) -> dict:
    async with get_client() as client:
        response = await client.post(path, json=payload)
        response.raise_for_status()
        return response.json()


async def api_delete(path: str) -> dict:
    async with get_client() as client:
        response = await client.delete(path)
        response.raise_for_status()
        return response.json()


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
        [button(t["track_btn"], f"track:{data['case']}:{data['node_id']}")],
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
# Case tracker: follow-ups, reminders and escalation
# ---------------------------------------------------------------------------


def fmt_date(iso: str, lang: str) -> str:
    """Show a stored UTC time as a Kenyan (UTC+3) date."""
    moment = datetime.fromisoformat(iso) + timedelta(hours=3)
    months = SW_MONTHS if lang == "sw" else EN_MONTHS
    return f"{moment.day} {months[moment.month - 1]} {moment.year}"


def chat_id_of(update: Update) -> int:
    chat = update.effective_chat
    return chat.id if chat is not None else update.effective_user.id


def menu_markup(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[button(T[lang]["menu_btn"], "menu")]])


async def send_long(message, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    parts = chunk_text(text)
    for index, part in enumerate(parts):
        await message.reply_text(part, reply_markup=markup if index == len(parts) - 1 else None)


async def start_track(query, context: ContextTypes.DEFAULT_TYPE, case_id: str, plan_id: str) -> None:
    lang = lang_of(context)
    context.user_data.pop("ev", None)
    context.user_data["track"] = {"case": case_id, "plan": plan_id, "step": "inst"}
    await clear_buttons(query)
    rows = [[button(T[lang]["inst"][code], f"inst:{code}")] for code in INSTITUTIONS]
    await query.message.reply_text(T[lang]["track_inst_q"], reply_markup=InlineKeyboardMarkup(rows))


async def ask_reference(message, lang: str) -> None:
    markup = InlineKeyboardMarkup([[button(T[lang]["skip_btn"], "tskip")]])
    await message.reply_text(T[lang]["track_ref_q"], reply_markup=markup)


async def ask_days(message, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = lang_of(context)
    track = context.user_data["track"]
    info = await api_get(f"/tracker/escalation/{track['institution']}", lang=lang)
    track["step"] = "days"
    rows = [[button(T[lang]["days_btn"].format(n=n), f"days:{n}") for n in (3, 7, 14)]]
    await message.reply_text(
        T[lang]["track_days_q"].format(note=info["wait_note"]),
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def save_track(message, context: ContextTypes.DEFAULT_TYPE, chat_id: int, days: int) -> None:
    lang = lang_of(context)
    track = context.user_data.pop("track")
    item = await api_post(
        "/tracker/follow-ups",
        {
            "chat_id": chat_id,
            "case_id": track["case"],
            "plan_id": track["plan"],
            "institution": track["institution"],
            "reference": track.get("reference"),
            "days": days,
            "lang": lang,
        },
    )
    await message.reply_text(
        T[lang]["track_saved"].format(date=fmt_date(item["follow_up_at"], lang)),
        reply_markup=menu_markup(lang),
    )


async def show_escalation(message, lang: str, institution: str, follow_up_id: int | None = None) -> None:
    t = T[lang]
    info = await api_get(f"/tracker/escalation/{institution}", lang=lang)
    lines = [t["esc_title"].format(inst=info["label"]), ""]
    lines += [f"{number}. {step}" for number, step in enumerate(info["steps"], start=1)]
    lines.append("")
    if info.get("verified"):
        lines.append(t["esc_verified"].format(date=info["verified"]))
    else:
        lines.append(t["esc_unverified"])
    if info.get("sources"):
        lines.append(t["esc_sources"])
        lines += info["sources"]
    rows = []
    if follow_up_id is not None:
        rows.append([button(t["fu_snooze_btn"], f"fu_snz:{follow_up_id}")])
        rows.append([button(t["fu_resolved_btn"], f"fu_ok:{follow_up_id}")])
    rows.append([button(t["menu_btn"], "menu")])
    await send_long(message, "\n".join(lines), InlineKeyboardMarkup(rows))


async def show_mycases(message, chat_id: int, lang: str) -> None:
    t = T[lang]
    items = await api_get("/tracker/follow-ups", chat_id=chat_id)
    if not items:
        await message.reply_text(t["mycases_empty"], reply_markup=menu_markup(lang))
        return
    lines, rows = [t["mycases_title"], ""], []
    for number, item in enumerate(items[:8], start=1):
        lines.append(
            t["fu_line"].format(
                n=number,
                inst=t["inst"].get(item["institution"], item["institution"]),
                ref=item["reference"] or t["no_ref"],
                date=fmt_date(item["follow_up_at"], lang),
                status=t["status_" + item["status"]],
            )
        )
        if item["status"] == "waiting":
            rows.append(
                [
                    button(f"#{number} {t['fu_noreply_btn']}", f"fu_esc:{item['id']}"),
                    button(f"#{number} \u2705", f"fu_ok:{item['id']}"),
                ]
            )
    rows.append([button(t["menu_btn"], "menu")])
    await send_long(message, "\n".join(lines), InlineKeyboardMarkup(rows))


async def handle_follow_up_action(
    query, update: Update, context: ContextTypes.DEFAULT_TYPE, action: str, follow_up_id: int
) -> None:
    chat_id = chat_id_of(update)
    fallback = lang_of(context) or "en"
    try:
        item = await api_get(f"/tracker/follow-ups/{follow_up_id}", chat_id=chat_id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            await query.message.reply_text(T[fallback]["not_found"])
            return
        raise
    # The saved language wins, so reminders work even after the bot restarted.
    lang = item["lang"] if item["lang"] in T else fallback
    context.user_data.setdefault("lang", lang)
    await clear_buttons(query)
    if action == "fu_ok":
        await api_post(f"/tracker/follow-ups/{follow_up_id}/resolve", {"chat_id": chat_id})
        await query.message.reply_text(T[lang]["fu_marked"], reply_markup=menu_markup(lang))
    elif action == "fu_snz":
        updated = await api_post(f"/tracker/follow-ups/{follow_up_id}/snooze", {"chat_id": chat_id, "days": 3})
        await query.message.reply_text(
            T[lang]["fu_snoozed"].format(date=fmt_date(updated["follow_up_at"], lang)),
            reply_markup=menu_markup(lang),
        )
    else:
        await show_escalation(query.message, lang, item["institution"], follow_up_id)


async def check_due(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Runs every 30 minutes: remind people whose follow-up date has arrived."""
    try:
        items = await api_get("/tracker/due")
    except Exception as exc:
        log.warning("Reminder check failed: %s", type(exc).__name__)
        return
    for item in items:
        lang = item["lang"] if item["lang"] in T else "en"
        t = T[lang]
        text = t["reminder"].format(
            inst=t["inst"].get(item["institution"], item["institution"]),
            ref=item["reference"] or t["no_ref"],
        )
        rows = [
            [button(t["fu_resolved_btn"], f"fu_ok:{item['id']}")],
            [button(t["fu_noreply_btn"], f"fu_esc:{item['id']}")],
            [button(t["fu_snooze_btn"], f"fu_snz:{item['id']}")],
        ]
        try:
            await context.bot.send_message(
                chat_id=item["chat_id"], text=text, reply_markup=InlineKeyboardMarkup(rows)
            )
        except Forbidden:
            pass  # the user blocked the bot: do not retry forever
        except Exception as exc:
            log.warning("Could not send reminder: %s", type(exc).__name__)
            continue
        try:
            await api_post(f"/tracker/follow-ups/{item['id']}/reminded")
        except Exception as exc:
            log.warning("Could not mark reminder: %s", type(exc).__name__)


# ---------------------------------------------------------------------------
# Telegram handlers
# ---------------------------------------------------------------------------


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("ev", None)
    context.user_data.pop("track", None)
    await show_welcome(update.message)


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = lang_of(context)
    if lang is None:
        await show_welcome(update.message)
        return
    context.user_data.pop("ev", None)
    context.user_data.pop("track", None)
    await show_cases(update.message, lang)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(T[lang_of(context) or "en"]["help"])


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = lang_of(context) or "en"
    evidence = context.user_data.pop("ev", None)
    tracking = context.user_data.pop("track", None)
    if evidence is not None or tracking is not None:
        await update.message.reply_text(T[lang]["ev_cancelled"])
    else:
        await update.message.reply_text(T[lang]["hint"])


async def cmd_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = lang_of(context) or "en"
    track = context.user_data.get("track")
    if track is not None and track.get("step") == "ref":
        await ask_days(update.message, context)
        return
    if "ev" not in context.user_data:
        await update.message.reply_text(T[lang]["hint"])
        return
    await advance(update.message, context, None)


async def cmd_mycases(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_mycases(update.message, chat_id_of(update), lang_of(context) or "en")


async def cmd_deletemydata(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = lang_of(context) or "en"
    markup = InlineKeyboardMarkup(
        [[button(T[lang]["delete_yes"], "del:yes")], [button(T[lang]["delete_no"], "del:no")]]
    )
    await update.message.reply_text(T[lang]["delete_confirm"], reply_markup=markup)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = lang_of(context)
    if lang is None:
        await show_welcome(update.message)
        return
    track = context.user_data.get("track")
    if track is not None:
        if track.get("step") == "ref":
            track["reference"] = (update.message.text or "").strip()[:60] or None
            await ask_days(update.message, context)
        else:
            await update.message.reply_text(T[lang]["use_buttons"])
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

    if action in ("fu_ok", "fu_esc", "fu_snz") and len(parts) == 2 and parts[1].isdigit():
        await handle_follow_up_action(query, update, context, action, int(parts[1]))
        return

    lang = lang_of(context)
    if lang is None:  # for example the bot was restarted and forgot the language
        await show_welcome(query.message)
        return

    if action == "langmenu":
        await query.edit_message_text(WELCOME, reply_markup=language_keyboard())
    elif action == "menu":
        context.user_data.pop("ev", None)
        context.user_data.pop("track", None)
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
    elif action == "track" and len(parts) == 3:
        await start_track(query, context, parts[1], parts[2])
    elif action == "inst" and len(parts) == 2 and parts[1] in INSTITUTIONS:
        track = context.user_data.get("track")
        await clear_buttons(query)
        if track is not None:
            track["institution"] = parts[1]
            track["step"] = "ref"
            await ask_reference(query.message, lang)
    elif action == "tskip":
        track = context.user_data.get("track")
        await clear_buttons(query)
        if track is not None and track.get("step") == "ref":
            await ask_days(query.message, context)
    elif action == "days" and len(parts) == 2 and parts[1].isdigit():
        track = context.user_data.get("track")
        await clear_buttons(query)
        if track is not None and track.get("step") == "days" and 1 <= int(parts[1]) <= 60:
            await save_track(query.message, context, chat_id_of(update), int(parts[1]))
    elif action == "del" and len(parts) == 2:
        await clear_buttons(query)
        if parts[1] == "yes":
            result = await api_delete(f"/tracker/chats/{chat_id_of(update)}")
            context.user_data.pop("ev", None)
            context.user_data.pop("track", None)
            await query.message.reply_text(T[lang]["delete_done"].format(n=result["deleted"]))
        else:
            await query.message.reply_text(T[lang]["delete_kept"])
    elif action == "skip":
        if "ev" not in context.user_data:
            await clear_buttons(query)
            return
        await clear_buttons(query)
        await advance(query.message, context, None)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error = context.error
    # Network problems are safe to describe (token hidden). For anything else
    # log only the error type: messages could contain personal details.
    if isinstance(error, (NetworkError, TimedOut, httpx.HTTPError)):
        detail = str(error)
        token = getattr(getattr(context, "bot", None), "token", None)
        if token:
            detail = detail.replace(token, "XXXX")
        log.warning("Network problem (%s): %s", type(error).__name__, detail[:200])
    else:
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
    # Generous timeouts: Wi-Fi and mobile data in Kenya can be slow or patchy.
    app = (
        Application.builder()
        .token(token)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .get_updates_connect_timeout(30)
        .get_updates_read_timeout(40)
        .get_updates_write_timeout(30)
        .get_updates_pool_timeout(30)
        .build()
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("skip", cmd_skip))
    app.add_handler(CommandHandler("mycases", cmd_mycases))
    app.add_handler(CommandHandler("deletemydata", cmd_deletemydata))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_error_handler(on_error)
    if app.job_queue is not None:
        app.job_queue.run_repeating(check_due, interval=1800, first=60)
    else:
        print('Reminders are OFF. Fix with:  pip install "python-telegram-bot[job-queue]"')
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
