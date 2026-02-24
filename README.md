# 🎙 Xisobchi Bot — Uzbek Voice Expense Tracker

Telegram bot that converts Uzbek voice and text messages into financial transactions using Google Cloud Speech-to-Text.

**🤖 Bot:** [@xisobchiman1_bot](https://t.me/xisobchiman1_bot)
**📊 Dashboard:** [xisobchi-dashboard.web.app](https://xisobchi-dashboard.web.app)

## Features

- 🎤 **Voice Input** — Send voice messages in Uzbek to record transactions
- ⌨️ **Text Input** — Type transactions directly (e.g. "Ovqatga 50 ming so'm")
- 🧠 **Google Cloud STT** — Speech-to-Text with Uzbek + Russian support
- 📊 **Smart Parsing** — Rule-based NLP understands Uzbek financial phrases
- 💰 **Multi-Currency** — Income/expense tracking in UZS and USD
- 📈 **Reports** — Daily, weekly, monthly, and full financial reports
- ✏️ **Edit & Undo** — Modify or delete transactions after saving
- 🎓 **Interactive Onboarding** — Guided walkthrough with demo mode for new users
- 📊 **Live Dashboard** — Real-time stats + admin panel on Firebase Hosting
- 📣 **Broadcast** — Send messages to all users from admin panel
- 🔒 **Privacy** — All data isolated per user, webhook secret validation

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Register & interactive onboarding |
| `/balans` | Net balance (UZS + USD) |
| `/bugun` | Today's transactions |
| `/hafta` | Last 7 days report |
| `/oy` | Monthly report by category |
| `/hisobot` | Full report (balance + monthly) |
| `/bekor` | Undo last transaction |
| `/tahrir` | Edit last transaction |
| `/export` | Export transactions as CSV |
| `/help` | Help & usage guide |

## Quick Start (Local Development)

### Prerequisites
- Python 3.10+
- ffmpeg (for audio conversion)
- Google Cloud project with Speech-to-Text API enabled

### Setup

```bash
# 1. Create virtual environment
python -m venv .venv

# 2. Activate it
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# 3. Install dependencies
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env: set BOT_TOKEN, DATABASE_URL, etc.

# 5. Place Google credentials
# Save your service account key as credentials.json in the project root

# 6. Run the bot (polling mode)
python run.py
```

## Production Deployment

### Backend (Render)
The bot runs on Render in webhook mode. Deploys automatically from GitHub.

**Required env vars on Render:**
| Variable | Description |
|----------|-------------|
| `BOT_TOKEN` | Telegram bot token from @BotFather |
| `WEBHOOK_URL` | Your Render URL (e.g. `https://telegram-xisobchi2.onrender.com`) |
| `MODE` | `webhook` |
| `DATABASE_URL` | PostgreSQL connection string |
| `GOOGLE_CREDENTIALS_JSON` | Full contents of `credentials.json` |
| `ADMIN_SECRET` | Token for admin panel access |

### Frontend Dashboard (Firebase Hosting)
```bash
npx -y firebase-tools deploy --only hosting --project xisobchi-dashboard
```

### Keep-Alive (Koyeb)
A pinger service on Koyeb prevents Render from sleeping by hitting the health endpoint every 14 minutes.

## Project Structure

```
├── app/
│   ├── config.py              # Environment-based settings
│   ├── bot.py                 # aiogram Bot + Dispatcher + router registration
│   ├── main.py                # FastAPI (webhook, stats, admin API)
│   ├── pinger.py              # Keep-alive pinger service
│   ├── constants.py           # Categories, emojis, Uzbek month names
│   ├── database/
│   │   ├── connection.py      # SQLAlchemy async engine + Alembic migrations
│   │   ├── models.py          # User, Transaction models
│   │   └── repositories/      # Repository pattern (User, Transaction)
│   ├── services/
│   │   ├── speech_service.py  # Google Cloud STT + audio conversion
│   │   ├── parser.py          # Uzbek NLP transaction parser
│   │   ├── transaction.py     # Business logic layer
│   │   └── report.py          # Formatted report generation
│   ├── handlers/
│   │   ├── onboarding.py      # /start, welcome flow, demo mode
│   │   ├── commands.py        # /balans /bugun /oy /hisobot /export
│   │   ├── voice.py           # Voice → transcribe → parse → confirm
│   │   ├── text.py            # Text → parse → confirm → save
│   │   └── edit.py            # /bekor /tahrir transaction editing
│   └── utils/
│       ├── formatting.py      # Amount formatting helpers
│       └── logger.py          # Structured logging
├── docs/
│   └── index.html             # Dashboard (deployed to Firebase)
├── migrations/                # Alembic database migrations
├── run.py                     # Entry point (webhook / polling / pinger)
├── Dockerfile                 # Container image
├── firebase.json              # Firebase Hosting config
└── railway.json               # Railway deployment config
```

## Architecture

```
Telegram User
  │ Voice / Text / Commands
  ▼
aiogram Handlers (FSM states for onboarding)
  │
  ├── Voice ──► Google Cloud STT ──► Uzbek Parser ──► Confirmation ──► Save
  │
  ├── Text  ──► Uzbek Parser ──► Confirmation ──► Save
  │
  └── Commands ──► Report Service
                       │
                       ▼
                 Repository Layer (async SQLAlchemy)
                       │
                       ▼
                 PostgreSQL (Neon)

Dashboard (Firebase Hosting) ──► FastAPI REST API ──► Same DB
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Bot Framework | aiogram 3.25 |
| Web Framework | FastAPI + uvicorn |
| Speech-to-Text | Google Cloud Speech-to-Text |
| Database | PostgreSQL (Neon) via SQLAlchemy async |
| Migrations | Alembic |
| NLP | Rule-based Uzbek/Russian parser |
| Dashboard | Vanilla HTML/JS on Firebase Hosting |
| Backend Hosting | Render (webhook mode) |
| Keep-Alive | Koyeb pinger service |

## Roadmap

- [x] PostgreSQL migration
- [x] Web dashboard
- [x] Text input support
- [x] Edit & undo transactions
- [x] Interactive onboarding with demo mode
- [x] CSV export
- [ ] Subscription system & premium features
- [ ] PDF report export
- [ ] Multi-currency exchange rates
- [ ] Budget tracking & alerts
- [ ] AI-powered financial insights

## License

Private — All rights reserved.
