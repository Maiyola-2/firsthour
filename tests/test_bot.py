import asyncio
import os
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "bot_test.db")
os.environ.pop("FIRSTHOUR_API_KEY", None)

import httpx
from telegram import Update

sys.path.insert(0, "backend")
sys.path.insert(0, "bot")
import bot  # noqa: E402
from main import app  # noqa: E402

# Point the bot at the real FastAPI app in memory.
bot.get_client = lambda: httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


class Chat:
    """Fake Telegram chat that records everything the bot says."""

    def __init__(self, chat_id=111):
        self.chat_id = chat_id
        self.sent = []  # (kind, text_or_filename, markup)
        self.user_data = {}

    def message(self):
        m = MagicMock()

        async def reply_text(text, reply_markup=None, **kw):
            self.sent.append(("text", text, reply_markup))

        async def reply_document(document, filename=None, **kw):
            self.sent.append(("doc", (filename, document.getvalue()), None))

        async def edit_text(text, reply_markup=None, **kw):
            self.sent.append(("edit", text, reply_markup))

        m.reply_text, m.reply_document, m.edit_text = reply_text, reply_document, edit_text
        return m

    def ctx(self):
        return SimpleNamespace(user_data=self.user_data, error=None)

    def text_update(self, text):
        u = MagicMock(spec=Update)
        u.message = self.message()
        u.message.text = text
        u.effective_chat = SimpleNamespace(id=self.chat_id)
        return u

    def tap(self, data):
        u = MagicMock(spec=Update)
        q = MagicMock()
        q.data = data
        q.answer = AsyncMock()
        q.edit_message_reply_markup = AsyncMock()
        msg = self.message()
        q.message = msg

        async def edit_message_text(text, reply_markup=None, **kw):
            self.sent.append(("edit", text, reply_markup))

        q.edit_message_text = edit_message_text
        u.callback_query = q
        u.effective_chat = SimpleNamespace(id=self.chat_id)
        return u

    def last(self, kind=None):
        items = [s for s in self.sent if kind is None or s[0] == kind]
        return items[-1]

    def buttons(self, entry):
        markup = entry[2]
        return [b.callback_data for row in markup.inline_keyboard for b in row] if markup else []


def run(coro):
    return asyncio.run(coro)


def ok(label, cond):
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        raise SystemExit(1)


async def flow():
    c = Chat()
    ctx = c.ctx()

    await bot.cmd_start(c.text_update("/start"), ctx)
    ok("welcome shows language buttons", c.buttons(c.last()) == ["lang:en", "lang:sw"])

    await bot.on_callback(c.tap("lang:sw"), ctx)
    last = c.last()
    ok("swahili case menu", "Nini kilitokea" in last[1] and "case:sent_money" in c.buttons(last))
    ok("language remembered", ctx.user_data["lang"] == "sw")

    await bot.on_callback(c.tap("case:sent_money"), ctx)
    ok("question shown with node buttons", "node:sent_money:q_mobile_provider" in c.buttons(c.last()))

    await bot.on_callback(c.tap("node:sent_money:q_mobile_provider"), ctx)
    ok("provider question shown", "node:sent_money:plan_safaricom" in c.buttons(c.last()))

    await bot.on_callback(c.tap("node:sent_money:plan_safaricom"), ctx)
    plan_msgs = [s for s in c.sent if s[0] == "text" and "FANYA HIVI SASA" in s[1]]
    ok("safaricom steps include verified channels", "456" in plan_msgs[0][1] and "0722000100" in plan_msgs[0][1] and "333" in plan_msgs[0][1])
    ok("plan shown in swahili", len(plan_msgs) == 1)
    ok("plan has evidence + menu buttons", c.buttons(c.last()) == ["ev:sent_money:plan_safaricom", "track:sent_money:plan_safaricom", "share:sent_money:plan_safaricom", "menu"])
    ok("urgency icon + disclaimer present", "\U0001F534" in plan_msgs[0][1] and "FirstHour hutoa mwongozo" in plan_msgs[0][1])

    await bot.on_callback(c.tap("ev:sent_money:plan_safaricom"), ctx)
    ok("evidence conversation started", "(1/8)" in c.last()[1] and ctx.user_data["ev"]["i"] == 0)

    await bot.on_text(c.text_update("Test User"), ctx)
    await bot.on_text(c.text_update("20 Okt 2026"), ctx)
    await bot.on_text(c.text_update("abc"), ctx)
    ok("bad amount rejected", "namba" in c.last()[1] and ctx.user_data["ev"]["i"] == 2)
    await bot.on_text(c.text_update("KSh 10,000"), ctx)
    ok("amount parsed", ctx.user_data["ev"]["data"]["amount_kes"] == 10000.0)
    await bot.on_text(c.text_update("M-Pesa"), ctx)
    await bot.on_callback(c.tap("skip"), ctx)  # skip transaction id
    await bot.on_text(c.text_update("Some Bank"), ctx)
    await bot.cmd_skip(c.text_update("/skip"), ctx)  # skip scammer phone via command
    await bot.on_text(c.text_update("Mtu alinipigia simu " * 5), ctx)

    docs = [s for s in c.sent if s[0] == "doc"]
    ok("PDF delivered", len(docs) == 1 and docs[0][1][1][:5] == b"%PDF-" and docs[0][1][0].endswith(".pdf"))
    ok("personal data cleared after PDF", "ev" not in ctx.user_data)
    ok("done message with menu button", c.buttons(c.last()) == ["menu"])

    # Menu returns to cases
    await bot.on_callback(c.tap("menu"), ctx)
    ok("menu works", "case:bank_agent_call" in c.buttons(c.last()))

    # /cancel mid-flow
    await bot.on_callback(c.tap("ev:sent_money:plan_safaricom"), ctx)
    await bot.cmd_cancel(c.text_update("/cancel"), ctx)
    ok("cancel clears state", "ev" not in ctx.user_data and "Imesitishwa" in c.last()[1])

    # Stray text with no flow active
    await bot.on_text(c.text_update("hello"), ctx)
    ok("stray text gives hint", "/start" in c.last()[1])

    # Forgotten language (bot restarted)
    c2 = Chat()
    await bot.on_callback(c2.tap("case:sent_money"), c2.ctx())
    ok("missing language re-asks", c2.buttons(c2.last()) == ["lang:en", "lang:sw"])

    # English path through a two-level question
    c3 = Chat(); ctx3 = c3.ctx()
    await bot.on_callback(c3.tap("lang:en"), ctx3)
    await bot.on_callback(c3.tap("case:bank_agent_call"), ctx3)
    await bot.on_callback(c3.tap("node:bank_agent_call:q_shared"), ctx3)
    ok("nested question buttons", "node:bank_agent_call:plan_remote_access" in c3.buttons(c3.last()))
    await bot.on_callback(c3.tap("node:bank_agent_call:plan_remote_access"), ctx3)
    ok("english plan", any("WHAT TO DO NOW" in s[1] for s in c3.sent if s[0] == "text"))

    # Contact-warning button on hijacked-account plans only
    c5 = Chat(); ctx5 = c5.ctx(); ctx5.user_data["lang"] = "sw"
    await bot.on_callback(c5.tap("node:hijacked_account:plan_whatsapp"), ctx5)
    ok("warn button on hijacked plan", "warn:plan_whatsapp" in c5.buttons(c5.last()))
    await bot.on_callback(c5.tap("warn:plan_whatsapp"), ctx5)
    ok("warning message sent in swahili", "TAHADHARI YA HARAKA" in c5.last()[1] and "WhatsApp" in c5.last()[1])
    c6 = Chat(); ctx6 = c6.ctx(); ctx6.user_data["lang"] = "en"
    await bot.on_callback(c6.tap("node:sent_money:plan_bank_transfer"), ctx6)
    ok("no warn button on money plans", not any(b.startswith("warn:") for b in c6.buttons(c6.last())))
    await bot.on_callback(c6.tap("warn:plan_bank_transfer"), ctx6)
    ok("bad warn id ignored", len(c6.sent) == 1 or "URGENT" not in c6.last()[1])

    # Every plan in every case, both languages, fits Telegram limits
    for lang in ("en", "sw"):
        cases = await bot.api_get("/cases", lang=lang)
        for case in cases:
            start = await bot.api_get(f"/cases/{case['id']}/start", lang=lang)
            case_obj = __import__("main").DATA["cases"][case["id"]]
            for node_id, node in case_obj["nodes"].items():
                if node["type"] != "plan":
                    continue
                data = await bot.api_get(f"/cases/{case['id']}/nodes/{node_id}", lang=lang)
                for part in bot.chunk_text(bot.format_plan(data, lang)):
                    assert len(part) <= 4096
    ok("all plans fit Telegram message limits", True)

    # Chunking logic
    long = "\n".join(["x" * 900] * 10)
    parts = bot.chunk_text(long)
    ok("chunking splits long text", len(parts) > 1 and all(len(p) <= bot.MAX_MESSAGE for p in parts))

    # ---------------- Case tracker ----------------
    from datetime import timedelta
    import tracker

    ok("fmt_date shifts UTC to Kenya time", bot.fmt_date("2026-10-22T22:30:00", "en") == "23 Oct 2026"
       and bot.fmt_date("2026-10-22T22:30:00", "sw") == "23 Okt 2026")

    t = Chat(chat_id=222); tctx = t.ctx(); tctx.user_data["lang"] = "en"
    await bot.on_callback(t.tap("track:sent_money:plan_safaricom"), tctx)
    ok("institution question", "inst:mobile_money" in t.buttons(t.last()))
    await bot.on_text(t.text_update("hello"), tctx)
    ok("text ignored while choosing institution", "tap one of the buttons" in t.last()[1])
    await bot.on_callback(t.tap("inst:mobile_money"), tctx)
    ok("reference asked with skip", "reference number" in t.last()[1] and t.buttons(t.last()) == ["tskip"])
    await bot.on_text(t.text_update("  QWE123  "), tctx)
    ok("days asked with wait note", t.buttons(t.last()) == ["days:3", "days:7", "days:14"] and "7 days" in t.last()[1])
    await bot.on_callback(t.tap("days:999"), tctx)
    ok("invalid days ignored", "track" in tctx.user_data)
    await bot.on_callback(t.tap("days:7"), tctx)
    ok("follow-up saved", "Saved. I will remind you on" in t.last()[1] and "track" not in tctx.user_data)
    await bot.cmd_mycases(t.text_update("/mycases"), tctx)
    ok("mycases lists it", all(x in t.last()[1] for x in ("Mobile money provider", "QWE123", "waiting")))
    items = await bot.api_get("/tracker/follow-ups", chat_id=222)
    fid = items[0]["id"]
    ok("mycases buttons", f"fu_esc:{fid}" in t.buttons(t.last()))
    await bot.on_callback(t.tap(f"fu_esc:{fid}"), tctx)
    ok("escalation steps shown", "WHAT TO DO NEXT: Mobile money provider" in t.last()[1] and "Central Bank of Kenya" in t.last()[1]
       and "Checked against official sources on 2026-10-22" in t.last()[1])
    ok("escalation offers snooze + resolve", t.buttons(t.last()) == [f"fu_snz:{fid}", f"fu_ok:{fid}", "menu"])

    with tracker.SessionLocal() as db:
        row = db.get(tracker.FollowUp, fid); row.follow_up_at = tracker.utcnow() - timedelta(hours=1); db.commit()
    sent = []
    async def fake_send(chat_id, text, reply_markup=None):
        sent.append((chat_id, text, reply_markup))
    jctx = SimpleNamespace(bot=SimpleNamespace(send_message=fake_send))
    await bot.check_due(jctx)
    ok("reminder sent to the right chat", len(sent) == 1 and sent[0][0] == 222 and "Follow-up reminder" in sent[0][1] and "QWE123" in sent[0][1])
    await bot.check_due(jctx)
    ok("reminder sent only once", len(sent) == 1)

    # Swahili user whose bot restarted (no language in memory): language comes from the saved item
    created = await bot.api_post("/tracker/follow-ups", {"chat_id": 333, "case_id": "sent_money", "institution": "bank",
                                                         "reference": "BK9", "days": 1, "lang": "sw"})
    s = Chat(chat_id=333); sctx = s.ctx()
    await bot.on_callback(s.tap(f"fu_esc:{created['id']}"), sctx)
    ok("reminder buttons work after restart", "FANYA HIVI BAADA YA HAPA: Benki" in s.last()[1])
    await bot.on_callback(s.tap(f"fu_snz:{created['id']}"), sctx)
    ok("snooze in swahili", "Sawa. Nitakukumbusha tena tarehe" in s.last()[1])
    await bot.on_callback(s.tap(f"fu_ok:{created['id']}"), sctx)
    ok("resolve in swahili", "Imewekwa kuwa imetatuliwa" in s.last()[1])
    await bot.cmd_mycases(s.text_update("/mycases"), sctx)
    ok("swahili status label", "imetatuliwa" in s.last()[1])
    o = Chat(chat_id=999); octx = o.ctx()
    await bot.on_callback(o.tap(f"fu_ok:{created['id']}"), octx)
    ok("cannot touch another user's follow-up", "I could not find" in o.last()[1])
    forged = await bot.api_get("/tracker/follow-ups", chat_id=999)
    ok("other user sees none of it", forged == [])

    # Skip paths, and cancel
    t2 = Chat(chat_id=444); c2 = t2.ctx(); c2.user_data["lang"] = "sw"
    await bot.on_callback(t2.tap("track:hijacked_account:plan_whatsapp"), c2)
    await bot.on_callback(t2.tap("inst:telecom"), c2)
    await bot.on_callback(t2.tap("tskip"), c2)
    ok("skip reference goes to days", t2.buttons(t2.last()) == ["days:3", "days:7", "days:14"])
    await bot.on_callback(t2.tap("days:3"), c2)
    saved = await bot.api_get("/tracker/follow-ups", chat_id=444)
    ok("saved without reference", "Imehifadhiwa" in t2.last()[1] and saved[0]["reference"] is None)
    await bot.on_callback(t2.tap("track:hijacked_account:plan_whatsapp"), c2)
    await bot.on_callback(t2.tap("inst:police"), c2)
    await bot.cmd_skip(t2.text_update("/skip"), c2)
    ok("/skip works on the reference step", t2.buttons(t2.last()) == ["days:3", "days:7", "days:14"])
    await bot.cmd_cancel(t2.text_update("/cancel"), c2)
    ok("cancel stops tracking", "track" not in c2.user_data and "Imesitishwa" in t2.last()[1])
    await bot.on_callback(t2.tap("days:7"), c2)
    ok("days tap after cancel does nothing", len(await bot.api_get("/tracker/follow-ups", chat_id=444)) == 1)

    # Privacy: erase my data
    await bot.cmd_deletemydata(t.text_update("/deletemydata"), tctx)
    ok("delete asks confirmation", t.buttons(t.last()) == ["del:yes", "del:no"])
    await bot.on_callback(t.tap("del:no"), tctx)
    ok("declining keeps data", "nothing was erased" in t.last()[1] and len(await bot.api_get("/tracker/follow-ups", chat_id=222)) == 1)
    await bot.on_callback(t.tap("del:yes"), tctx)
    ok("confirming erases data", "erased" in t.last()[1] and await bot.api_get("/tracker/follow-ups", chat_id=222) == [])
    ok("other users' data survives erase", len(await bot.api_get("/tracker/follow-ups", chat_id=333)) == 1)
    await bot.cmd_mycases(t.text_update("/mycases"), tctx)
    ok("empty mycases message", "no saved follow-ups" in t.last()[1])

    # ---------------- Anonymous sharing ----------------
    import community
    from sqlalchemy import select as _select
    from tracker import SessionLocal as _SL
    sh = Chat(chat_id=555); shctx = sh.ctx(); shctx.user_data["lang"] = "en"
    await bot.on_callback(sh.tap("share:hijacked_account:plan_whatsapp"), shctx)
    first = sh.last()
    ok("share explains what is stored", "ONLY three things" in first[1])
    btns = sh.buttons(first)
    ok("all 47 counties offered, plus a skip option", len([b for b in btns if b.startswith("cty:") and b != "cty:none"]) == 47 and btns[-1] == "cty:none")
    ok("nothing saved before consent is given", _SL().scalars(_select(community.IncidentReport)).first() is None)
    idx = community.COUNTIES.index("Kakamega")
    await bot.on_callback(sh.tap(f"cty:{idx}"), shctx)
    ok("thanks shown", "anonymous report was added" in sh.last()[1])
    rows = _SL().scalars(_select(community.IncidentReport)).all()
    ok("only case, plan, county and week were stored", len(rows) == 1 and rows[0].county == "Kakamega" and rows[0].plan_id == "plan_whatsapp"
       and rows[0].case_id == "hijacked_account" and rows[0].is_demo is False)
    await bot.on_callback(sh.tap("share:hijacked_account:plan_whatsapp"), shctx)
    ok("same incident cannot be shared twice in a session", "already shared" in sh.last()[1] and len(_SL().scalars(_select(community.IncidentReport)).all()) == 1)
    await bot.on_callback(sh.tap("cty:3"), shctx)
    ok("stray county tap after sharing does nothing", len(_SL().scalars(_select(community.IncidentReport)).all()) == 1)

    sk = Chat(chat_id=556); skctx = sk.ctx(); skctx.user_data["lang"] = "sw"
    await bot.on_callback(sk.tap("share:sent_money:plan_safaricom"), skctx)
    ok("share intro in swahili", "vitu VITATU TU" in sk.last()[1])
    await bot.on_callback(sk.tap("cty:none"), skctx)
    rows = _SL().scalars(_select(community.IncidentReport)).all()
    ok("county can be skipped", len(rows) == 2 and rows[1].county is None and "Asante" in sk.last()[1])
    await bot.on_callback(sk.tap("cty:9999"), skctx)
    ok("forged county index ignored", len(_SL().scalars(_select(community.IncidentReport)).all()) == 2)

    # API down -> friendly message through the error handler
    bot.get_client = lambda: httpx.AsyncClient(base_url="http://127.0.0.1:9", timeout=2)
    c4 = Chat(); ctx4 = c4.ctx(); ctx4.user_data["lang"] = "en"
    upd = c4.tap("case:sent_money")
    upd.effective_message = c4.message()
    try:
        await bot.on_callback(upd, ctx4)
    except httpx.HTTPError as exc:
        ctx4.error = exc
        await bot.on_error(upd, ctx4)
    ok("api down message", "not reachable" in c4.last()[1])


async def amounts():
    ok("parse_amount variants", [bot.parse_amount(x) for x in ("10000", "10,000", "KSh 5000", "ksh.250", "abc", "-5")]
       == [10000.0, 10000.0, 5000.0, 250.0, None, None])


run(flow())
run(amounts())
app_obj = bot.build_application("123456:TEST-TOKEN")
ok("application builds with all handlers", len(app_obj.handlers[0]) == 9)
print("ALL TESTS PASSED")
