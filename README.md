# FirstHour

**An incident-response assistant for ordinary people who have just been scammed or hacked.**

Most cybersecurity tools try to *detect* scams. FirstHour helps in the moment *after* the damage, when victims panic and often lose more money or access because they don't know what to do.

---

## The Problem

Mobile money fraud, fake "bank agent" calls, SIM swaps, fake loan apps, and account takeovers are growing in Kenya. Victims often do not know:

- What to do in the first hour
- Which institution to contact (telco, bank, DCI, ODPC)
- What evidence to keep and how to present it

As a result, reports are weak or never filed, losses grow, and authorities lack data on emerging scams. Low-income, rural, and feature-phone users are hit hardest and served least.

## Why I'm Building This

I am a computer science student at Masinde Muliro University of Science and Technology (MMUST), pursuing a career in cybersecurity. This project comes from two incidents close to me.

**The phone call.** A relative received a call from people posing as bank agents. They said his account had been hacked and that they needed his details to protect it. He trusted them, shared his banking details, and lost KSh 10,000. The scammers used fear and urgency, and by the time he realised what had happened, the money was gone. He did not know who to call or what to do next.

**The link.** A friend's WhatsApp account was taken over after she clicked a link that looked harmless. The attacker used her account to message her contacts and ask them for money, which put the people who trusted her at risk too. She had no idea how to recover her account or warn her contacts quickly.

In both cases, the loss was made worse by what happened *after*: confusion, delay, and not knowing which steps to take first. That is the gap FirstHour is built to close. I want people to have clear, local-language guidance in the first hour, when it matters most.

---

## Features

- **Guided triage:** step-by-step action plans for the first hour, in English and Swahili
- **Evidence pack:** collects transaction details and screenshots, then generates a PDF for the telco, bank, or police
- **Smart routing:** tells the user which institution to contact for their case type
- **Case tracker:** follow-up reminders and reference numbers
- **Community dashboard:** anonymized scam trends by area

## MVP Scope

The first version covers three real-world cases:

1. **Fake "bank agent" call:** the user shared bank or card details with a caller
2. **Sent money to a scammer:** mobile money or bank transfer to a fraudster
3. **Hijacked account:** WhatsApp or social media account taken over through a malicious link

Planned later: SIM swap, fake loan app harassment, leaked ID, WhatsApp and USSD interfaces.

## Project Status

MVP in progress.
- [ ] Research and verified contact sources
- [x] Triage decision engine (3 MVP cases, English and Swahili)
- [x] Evidence PDF generator
- [ ] Telegram bot
- [ ] Case tracker and dashboard
- [ ] User testing and evaluation

## Tech Stack

Python, FastAPI, MySQL, Telegram Bot API, React

## Project Structure

```
backend/    API and triage engine
bot/        Telegram bot
dashboard/  Community dashboard
docs/       Research notes, sources, report
```

## Getting Started

```bash
git clone https://github.com/Maiyola-2/firsthour.git
cd firsthour
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install fastapi uvicorn
```

## Privacy

Victim data is sensitive. FirstHour is designed to collect the minimum needed, anonymize all dashboard data, and never store secrets in the repository. Real incidents that inspired this project are described without names.

## Disclaimer

FirstHour gives guidance, not legal or financial advice. In an emergency, contact your bank, telco, or the police directly.

## Author

Maiyola-2, Computer Science student, Kenya

## License

MIT
