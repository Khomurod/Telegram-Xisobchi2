# 🎙 Xisobchi Bot — Uzbek Voice Expense Tracker

Telegram bot that converts Uzbek voice messages into financial transactions using Google Cloud Speech-to-Text.

## Features

- 🎤 **Voice Input** — Send voice messages in Uzbek to record transactions
- 🧠 **AI Speech-to-Text** — Google Cloud Speech-to-Text with Uzbek language support
- 📊 **Smart Parsing** — Understands Uzbek + Russian financial phrases
- 💰 **Balance Tracking** — Income/expense tracking with UZS and USD
- 📈 **Reports** — Daily, monthly, and full financial reports
- 🔒 **Privacy** — All data isolated per user

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Register & show instructions |
| `/balans` | Net balance (UZS + USD) |
| `/bugun` | Today's transactions |
| `/oy` | Monthly report by category |
| `/hisobot` | Full report |

## Quick Start (Local Development)

### Prerequisites
- Python 3.10+ (tested on 3.14)
- ffmpeg (for audio processing)

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
# Edit .env and set your BOT_TOKEN

# 5. Run the bot (polling mode for development)
python run.py
```

You need a Google Cloud project with Speech-to-Text API enabled and a service account key (`credentials.json`).

## Docker Deployment

```bash
# Build and run
docker-compose up -d

# View logs
docker-compose logs -f bot
```

For webhook mode, set in `.env`:
```
MODE=webhook
WEBHOOK_URL=https://your-domain.com
```

## Project Structure

```
├── app/
│   ├── config.py              # Environment-based settings
│   ├── bot.py                 # aiogram Bot + Dispatcher
│   ├── main.py                # FastAPI webhook + polling
│   ├── database/
│   │   ├── connection.py      # SQLAlchemy async engine
│   │   ├── models.py          # User, Transaction models
│   │   └── repositories/      # Repository pattern (User, Transaction)
│   ├── services/
│   │   ├── speech_service.py   # Google Cloud STT
│   │   ├── parser.py          # Uzbek NLP parser
│   │   ├── transaction.py     # Business logic
│   │   └── report.py          # Report generation
│   ├── handlers/
│   │   ├── commands.py        # /start /balans /bugun /oy /hisobot
│   │   └── voice.py           # Voice → transaction pipeline
│   └── utils/
│       └── logger.py          # Structured logging
├── .env.example               # Config template
├── requirements.txt           # Python dependencies
├── run.py                     # Entry point
├── Dockerfile                 # Container image
└── docker-compose.yml         # Container orchestration
```

## Architecture

```
Telegram User
  │ Voice / Commands
  ▼
aiogram Handlers
  │
  ├── Voice ──► Whisper STT ──► Uzbek Parser ──► Transaction Service
  │                                                    │
  └── Commands ──► Report Service ◄────────────────────┘
                        │                              │
                        ▼                              ▼
                  Repository Layer ◄──────────── Repository Layer
                        │
                        ▼
                    SQLite DB
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Bot Framework | aiogram 3 |
| Web Framework | FastAPI + uvicorn |
| Speech-to-Text | Google Cloud Speech-to-Text |
| Database | SQLite (async via SQLAlchemy) |
| NLP | Rule-based Uzbek parser |

## Future Roadmap

- [ ] PostgreSQL migration (just change `DATABASE_URL`)
- [ ] Subscription system & premium features
- [ ] Web dashboard
- [ ] PDF report export
- [ ] Multi-currency exchange rates
- [ ] Budget tracking & alerts
- [ ] AI-powered financial insights

## License

Private — All rights reserved.
