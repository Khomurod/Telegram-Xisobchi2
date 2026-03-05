# 🚀 Telegram Mini App — Best Practice Recommendation for Xisobchi Bot

## Why a Mini App?

Your bot already has a solid backend (FastAPI + PostgreSQL) and a working admin dashboard. A **Telegram Mini App (TWA)** would give users a **rich, visual UI** for managing their finances — right inside Telegram — without leaving the chat.

---

## Recommended Architecture

```
┌─────────────────────────────────────────────────────┐
│  Telegram Chat (Bot)                                │
│  Voice/Text input • Commands • Quick actions        │
│                                                     │
│  ┌───────────────────────────────────────────────┐  │
│  │  Telegram Mini App (WebApp)                   │  │
│  │  Rich UI: charts, transaction list, filters   │  │
│  │  Hosted on Firebase Hosting (/app)            │  │
│  └───────────────┬───────────────────────────────┘  │
└──────────────────┼──────────────────────────────────┘
                   │ REST API (JWT from initData)
                   ▼
          FastAPI Backend (Render)
                   │
                   ▼
          PostgreSQL (Neon)
```

---

## Approach: Vanilla HTML/CSS/JS (Recommended for your setup)

Given your current stack, here is the best-fit approach:

### ✅ Why Vanilla (like your dashboard)

| Factor | Reasoning |
|--------|-----------|
| **Consistency** | Your admin dashboard is already vanilla HTML/CS/JS — same patterns, no learning curve |
| **No build step** | Deploy directly to Firebase Hosting, just like today |
| **Bundle size** | ~0 KB framework overhead → instant load inside Telegram |
| **Simplicity** | No Node.js toolchain, no bundler config, easy to maintain |
| **Cost** | Firebase Hosting free tier is more than enough |

### ⚠️ When to consider React/Vue instead
Only if you plan to build **20+ interactive screens** with complex state management (e.g., multi-step forms, real-time collaboration). For an expense tracker with 4–6 screens, vanilla JS is ideal.

---

## Proposed Mini App Screens

| Screen | Purpose | API Endpoint |
|--------|---------|-------------|
| **📊 Dashboard** | Balance summary, spending pie chart, recent transactions | `GET /api/mini/dashboard` |
| **📝 Transactions** | Scrollable list with date filters, category icons | `GET /api/mini/transactions` |
| **➕ Add Transaction** | Quick-add form (type, amount, currency, category) | `POST /api/mini/transactions` |
| **📈 Reports** | Monthly/weekly charts with category breakdown | `GET /api/mini/reports` |
| **⚙️ Settings** | Profile info, currency preferences | `GET/PUT /api/mini/settings` |

---

## Key Technical Decisions

### 1. Authentication — Use Telegram `initData` (mandatory)

Telegram injects `initData` into every Mini App. **Validate it on your FastAPI backend** using HMAC-SHA256 with your bot token. This is the official, secure method — no passwords, no OAuth.

```python
# Backend: validate Telegram initData
import hashlib, hmac, urllib.parse, json

def validate_init_data(init_data: str, bot_token: str) -> dict | None:
    parsed = dict(urllib.parse.parse_qsl(init_data))
    check_hash = parsed.pop("hash", "")
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(parsed.items())
    )
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, check_hash):
        return None
    return json.loads(parsed.get("user", "{}"))
```

### 2. Hosting — Firebase Hosting (same as dashboard)

```
docs/
├── index.html         ← existing admin dashboard
├── css/styles.css
├── js/...
└── app/               ← NEW: Mini App lives here
    ├── index.html
    ├── css/
    │   └── mini.css
    └── js/
        ├── telegram.js    # Telegram WebApp SDK bridge
        ├── api.js         # API calls with initData auth
        ├── dashboard.js   # Dashboard screen
        ├── transactions.js
        ├── add.js
        └── router.js      # Simple hash-based SPA router
```

Update `firebase.json` to serve both the admin dashboard and mini app.

### 3. API Layer — New `/api/mini/` routes on FastAPI

Add dedicated mini app endpoints to `main.py` (or a new router file) that:
- Validate `initData` from the `Authorization` header
- Return JSON optimized for the mini app UI
- Reuse existing `TransactionRepository` and `ReportService`

### 4. Telegram WebApp SDK Integration

```html
<!-- In app/index.html -->
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<script>
  const tg = window.Telegram.WebApp;
  tg.ready();
  tg.expand();  // Full-screen mode

  // Theme adaptation
  document.documentElement.style.setProperty('--tg-bg', tg.themeParams.bg_color);
  document.documentElement.style.setProperty('--tg-text', tg.themeParams.text_color);

  // Send initData with every API call
  const INIT_DATA = tg.initData;
</script>
```

### 5. Bot Integration — Menu Button + Inline Keyboard

```python
# Set the Mini App as the bot's menu button
await bot.set_chat_menu_button(
    menu_button=MenuButtonWebApp(
        text="📊 Xisobchi",
        web_app=WebAppInfo(url="https://xisobchi-dashboard.web.app/app/")
    )
)
```

---

## Implementation Phases

### Phase 1: Foundation (API + Auth + Shell)
- [ ] Add `initData` validation utility to backend
- [ ] Create `/api/mini/dashboard` endpoint
- [ ] Create mini app HTML shell with Telegram SDK
- [ ] Set up hash-based SPA router
- [ ] Configure Firebase Hosting for `/app/` path

### Phase 2: Core Screens
- [ ] Dashboard screen (balance cards, recent transactions)
- [ ] Transaction list with infinite scroll + date filter
- [ ] Add transaction form with category picker
- [ ] Adapt theme to Telegram's `themeParams`

### Phase 3: Reports & Polish
- [ ] Charts (use lightweight Chart.js or vanilla canvas)
- [ ] Monthly/weekly report views
- [ ] Haptic feedback via `tg.HapticFeedback`
- [ ] Loading skeletons + error states
- [ ] Menu button registration via BotFather / code

### Phase 4: Advanced (optional)
- [ ] Settings screen (currency preference, notification toggle)
- [ ] Pull-to-refresh pattern
- [ ] Offline caching with Service Worker
- [ ] Cloud backup export (PDF)

---

## Best Practices Checklist

| Practice | Detail |
|----------|--------|
| ✅ **Always validate `initData`** | Never trust the frontend — validate HMAC on every API call |
| ✅ **Use `tg.themeParams`** | Match Telegram's light/dark theme automatically |
| ✅ **Call `tg.ready()`** | Signals Telegram the app is loaded (removes spinner) |
| ✅ **Call `tg.expand()`** | Maximizes the mini app window |
| ✅ **Use `MainButton`** | Telegram's native bottom button for primary actions (e.g., "Save Transaction") |
| ✅ **Use `BackButton`** | Native back navigation instead of custom UI |
| ✅ **Haptic feedback** | `tg.HapticFeedback.impactOccurred('light')` on button taps |
| ✅ **Keep bundle tiny** | No React/Vue overhead — vanilla JS loads in <100ms |
| ✅ **CORS for mini app origin** | Add the Firebase URL to your FastAPI CORS list |
| ✅ **Mobile-first design** | Mini apps are 99% mobile — design for small screens first |
| ✅ **Reuse existing services** | Your `ReportService`, `TransactionService`, `TransactionRepository` already do the heavy lifting |

---

## What Changes in Existing Code?

| File | Change | Impact |
|------|--------|--------|
| `app/main.py` | Add `/api/mini/*` routes + `initData` validation | New code only, no existing endpoints affected |
| `firebase.json` | Add rewrite rule for `/app/**` | Dashboard unaffected |
| `docs/app/` | New directory for mini app files | No existing files touched |
| `app/config.py` | No changes needed (bot token already available) | None |
| Database | No schema changes — same `users` + `transactions` tables | None |

> [!IMPORTANT]
> **Zero breaking changes.** The mini app adds new API routes and new frontend files. The existing bot, dashboard, and database are completely untouched.

---

## Summary

**Vanilla HTML/CSS/JS** is the best fit because:
1. It matches your existing dashboard stack — no new tooling
2. Zero framework overhead — blazing fast inside Telegram
3. Firebase Hosting serves it for free, no build step needed
4. Your backend already has the data layer — just add thin API routes
5. Telegram's WebApp SDK handles auth, theming, and native UX patterns

Would you like me to proceed with implementation? I'll start with **Phase 1** (API + auth + app shell).
