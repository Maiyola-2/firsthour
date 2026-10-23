# FirstHour

**An incident-response assistant for ordinary people who have just been scammed or hacked.**

Most cybersecurity tools try to *detect* scams. FirstHour helps in the moment *after* the damage, when victims panic and often lose more money or access because they don't know what to do. It runs as a Telegram bot in English and Swahili.

---

## The Problem

Mobile money fraud, fake "bank agent" calls, SIM swaps, fake loan apps, and account takeovers are growing in Kenya. Victims often do not know:

- What to do in the first hour
- Which institution to contact (telco, bank, DCI, ODPC)
- What evidence to keep and how to present it
- What to do when nobody replies

As a result, reports are weak or never filed, losses grow, and authorities lack data on emerging scams. Low-income, rural, and feature-phone users are hit hardest and served least.

## Why I'm Building This

I am a computer science student at Masinde Muliro University of Science and Technology (MMUST), pursuing a career in cybersecurity. This project comes from two incidents close to me.

**The phone call.** A relative received a call from people posing as bank agents. They said his account had been hacked and that they needed his details to protect it. He trusted them, shared his banking details, and lost KSh 10,000. The scammers used fear and urgency, and by the time he realised what had happened, the money was gone. He did not know who to call or what to do next.

**The link.** A friend's WhatsApp account was taken over after she clicked a link that looked harmless. The attacker used her account to message her contacts and ask them for money, which put the people who trusted her at risk too. She had no idea how to recover her account or warn her contacts quickly.

In both cases, the loss was made worse by what happened *after*: confusion, delay, and not knowing which steps to take first. That is the gap FirstHour is built to close.

---

## Features

| Feature | What it does |
|---|---|
| **Guided triage** | Asks what happened and gives a different action plan for each situation, in English and Swahili |
| **Provider-specific steps** | For Safaricom M-PESA, shows the exact official reversal and reporting channels |
| **Evidence report (PDF)** | Collects the details through short questions and produces one clean PDF to hand to the bank, provider or police |
| **Contact-warning message** | After a hijacked account, writes a ready-to-send message to warn contacts and groups |
| **Case tracker** | Saves who the victim reported to, the reference number and a follow-up date, then sends a reminder |
| **Escalation guidance** | If nobody replies, shows where to go next (bank, then the Central Bank of Kenya; M-PESA, then the Central Bank; telecom, then the Communications Authority) |
| **Erase my data** | `/deletemydata` permanently removes everything stored about the user |
| **Anonymous sharing** | Optional. The victim can share only the type of incident, an optional county and the week, to help warn the community |
| **Community dashboard** | A public web page (English and Swahili) showing anonymised trends: scam types, counties and weekly counts, with small groups hidden |

### Cases covered by the MVP

1. **Fake "bank agent" call:** the user shared bank or card details with a caller
2. **Sent money to a scammer:** M-PESA or another mobile money service, bank transfer, or other payment
3. **Hijacked account:** WhatsApp, social media or email taken over, often through a malicious link

Planned later: SIM swap, fake loan app harassment, leaked ID, a WhatsApp interface, a USSD/SMS interface for feature phones, and verified guidance for Airtel Money and individual banks.

## Project Status

- [ ] Research and verified contact sources (in progress, see `docs/sources.md`)
- [x] Triage decision engine (3 MVP cases, English and Swahili)
- [x] Evidence PDF generator
- [x] Telegram bot
- [x] Contact-warning generator
- [x] Case tracker with reminders and escalation guidance
- [x] Community dashboard (anonymised)
- [ ] User testing and evaluation

---

## Tech Stack

- **Backend:** Python, FastAPI, SQLAlchemy
- **Database:** SQLite by default; MySQL supported through the `DATABASE_URL` setting
- **Bot:** python-telegram-bot (with job queue for reminders)
- **PDF:** fpdf2
- **Dashboard:** plain HTML and JavaScript served by the API (no build step needed)

## Project Structure

```
backend/
  main.py            API: triage, evidence PDF, contact warning
  tracker.py         Case tracker, reminders data, escalation endpoint
  community.py       Anonymous reports and privacy-protected statistics
  seed_demo.py       Optional: labelled SYNTHETIC demo data for presentations
  evidence.py        PDF evidence report generator
  warn.py            Contact-warning message generator
  triage_data.json   Decision trees and action plans (English and Swahili)
  escalation.json    Escalation steps per institution, with sources
  requirements.txt
bot/
  bot.py             Telegram bot
dashboard/
  index.html         Community dashboard page, served at /dashboard
tests/               Automated tests (API, privacy rules and the bot)
docs/
  sources.md         Verified official sources and the date each was checked
```

## Getting Started

You need Python 3.11 or newer.

```bash
git clone https://github.com/Maiyola-2/firsthour.git
cd firsthour
python -m venv venv
venv\Scripts\activate        # Linux/Mac: source venv/bin/activate
pip install -r backend/requirements.txt
```

**1. Create a Telegram bot.** In Telegram, message `@BotFather`, send `/newbot`, and copy the token it gives you.

**2. Store the token safely.** Create a file named `.env` inside the `bot` folder:

```
TELEGRAM_BOT_TOKEN=your-token-here
API_URL=http://127.0.0.1:8000
```

Never commit this file. It is excluded by `.gitignore`.

**3. Start the API** (first terminal):

```bash
cd backend
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000/docs` to try the API in your browser.

**4. Start the bot** (second terminal):

```bash
cd bot
python bot.py
```

**5. Open your bot in Telegram** and send `/start`.

**6. Open the community dashboard** at `http://127.0.0.1:8000/dashboard`. It stays empty until people share reports, because groups with fewer than 3 reports are hidden by design.

For a presentation you can load clearly labelled **synthetic** demo data. It never mixes with real data and the page shows a DEMO DATA banner:

```bash
cd backend
python seed_demo.py            # add demo data, then open /dashboard?demo=1
python seed_demo.py --clear    # remove it
```

Always say that demo figures are synthetic. Never present them as real incidents.

### Running the tests

From the project root, with the virtual environment active:

```bash
python tests/test_tracker_api.py
python tests/test_community_api.py
python tests/test_bot.py
```

The tests use a temporary database and do not touch your real data or the Telegram network.

### Optional settings (backend/.env)

```
DATABASE_URL=mysql+pymysql://user:password@localhost:3306/firsthour
FIRSTHOUR_API_KEY=a-long-random-secret
```

If `FIRSTHOUR_API_KEY` is set, the tracker endpoints require it, and the bot sends it automatically when it is also set in `bot/.env`.

---

## Privacy by Design

Victim data is sensitive, so FirstHour is built to collect as little as possible.

- **Evidence reports are never stored.** The PDF is generated in memory and sent straight back. Answers are dropped from memory as soon as the PDF is made.
- **The tracker stores only:** the Telegram chat ID, case type, institution, an optional reference number, dates, status and language. No names, amounts, phone numbers or message text.
- **Users can erase everything** at any time with `/deletemydata`.
- **Community sharing is optional and anonymous.** Only the incident type, an optional county and the week (not the exact time) are stored, with no chat ID or any link back to the person. The dashboard hides every group smaller than 3 and merges small groups into an "Other" row, so no individual can be singled out. Figures show only what people chose to report, so they are indicative, not official statistics.
- **Secrets stay out of the repository.** The bot token and database file are excluded by `.gitignore`.
- **Logs avoid personal data.** Errors are logged by type, and the bot token is hidden.
- The bot does **not** read call logs, SMS, contacts or anything else on the user's phone.
- Real incidents that inspired this project are described without names.

## Sources and Accuracy

Action plans are based on official pages (Safaricom, the Central Bank of Kenya and the Communications Authority of Kenya). Each source and the date it was checked are recorded in `docs/sources.md`. Where no official source was found, the bot says so rather than guessing. Contact details change, so always confirm with the institution.

## Disclaimer

FirstHour gives general guidance, not legal or financial advice. In an emergency, contact your bank, mobile network, or the police directly.

## Development Note

Built with AI assistance (Claude) for code and drafting. Sources are verified and recorded in `docs/sources.md`.

## Author

Maiyola-2, Computer Science student, MMUST, Kenya

## License

MIT
