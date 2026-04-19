# 3inkauf

A mobile-first Progressive Web App (PWA) for collaborative grocery shopping. Features AI-powered auto-categorization, paper-list & fridge photo scanning, single-item photo identification, voice commands, recipe suggestions from list items or free-text queries, loyalty-card storage, and an admin interface with temporary runtime model overrides.

You can see it live in action using https://einkauf.kernkraft.io 

## Features

### Shopping Lists
- Create and manage multiple named shopping lists
- Share lists with other users for real-time collaborative editing
- Leave a shared list at any time without deleting it (owner can re-invite)
- Color-coded items showing who added each item on shared lists
- Duplicate item names within a list are rejected (case-insensitive)
- Duplicate list names per owner are rejected (other users can still have a list with the same name)
- WebSocket-based real-time sync — changes appear instantly for all users (including the originator)

### Items & Categories
- Add items with optional quantity
- **Add items by photo** — tap the camera next to `+`, snap a single product, AI identifies the name + package size and adds it uncategorized. The captured photo is automatically attached to the item as its thumbnail.
- Create custom categories per list (e.g., "Obst", "Backwaren", "Getränke")
- Drag & drop to reorder items and categories (handle-based, mobile-friendly, 6-dot grip icon with a generous tap target to avoid fat-finger collisions with the checkbox)
- Move items between categories via a quick category picker
- Check off items while shopping (tap the circle to mark as done)
- Attach photos to items (take a photo or choose from gallery, client-side compressed)
- Clear all items button (moved to the far-right of the toolbar for safer muscle memory)

### Paper List Scanning (Ollama vision)
- Camera button next to the "New list" input — photograph a handwritten or printed list
- **Scan-first flow**: the title field is empty by default; take the photo first, then enter the list name in the preview modal before saving
- Backend sends the image to the configured OCR model (defaults to `gemma4:31b-cloud` which is near-perfect on handwriting), returns structured items + proposed categories
- Preview dialog lets the user tick/untick items and enter the list name; accepted items and their categories are then created on the new list
- Categories are returned in the user's locale (German or English)
- Button only appears if Ollama is configured (checked via `/health`)

### Fridge Scan (identify groceries from a fridge interior photo)
- Second camera-style button (fridge icon) next to the paper-list scan
- User photographs the inside of their fridge → AI identifies every visible grocery item, assigns categories, and flags a per-item confidence (high / medium / low)
- Preview modal mirrors the paper-scan flow: low-confidence items default unchecked so stray detections never sneak in without review
- Title defaults to "Kühlschrank" / "Fridge contents" and is editable in the preview
- Backed by a cloud vision model (default `qwen3.5:397b-cloud`) — the local 12 GB GPU is not involved

### Recipe Generation
- Orange chef-hat button on the list toolbar opens a two-tab dialog:
  - **From my list** — AI picks 3 concrete named dishes the user could cook from what is already on the list, including additional typical ingredients they would still need. Each recipe returns name, description, servings, prep/cook time, 5-10 ingredients (flagged `already_have` vs. missing, server re-verified), 4-8 numbered preparation steps, and an optional tip — all in one response so repeated views are instant and consistent.
  - **Recipe by name** — free-text input ("Spaghetti bolognese for 4 people"); same structured output with steps included, quantities scaled to requested servings.
- Each recipe card has a magnifier icon that expands into a full recipe view with numbered steps, timing, tips, and a **"✉ Email to me"** button that sends a formatted HTML email to the current user's address. Button transitions from idle → sending (spinner) → sent (green confirmation) so the user always knows the state.

### Voice Control (Web Speech + Ollama)
- Microphone button in the navbar; tap once to enter continuous listening mode, tap again to stop
- Uses the browser's Web Speech API for zero-infra speech-to-text (Chrome/Edge/Safari; Firefox unsupported)
- Transcript sent to the backend `/voice/intent` endpoint which uses the configured audio model (default `gemma4:e2b`) to parse a structured command
- Supported intents: `create_list`, `add_items` (multi-item with quantities), `check_item`, `uncheck_item`, `delete_item`, `clear_list`, `unknown`
- Reasoning-mode models are handled correctly: the request pins `think: false` and uses a dedicated conservative sampling profile (`temperature=0.2`, `top_p=0.9`, `top_k=40`) to prevent small models from emitting just `<eos>` on short commands
- Multi-item commands are per-item tolerant — duplicates or unrecognised fragments are skipped, the rest go through
- Context-aware: on the list overview only `create_list` works; inside a list the full vocabulary is available
- Fuzzy item matching for check/uncheck/delete (handles articles, inflections)

### Smart Auto-Sort
- One-tap AI button assigns uncategorized items to matching categories
- **Two AI modes** (backend configuration, transparent to users):
  - **Simple**: Built-in multilingual sentence embeddings (fastembed/ONNX, works offline, no external dependencies)
  - **Advanced**: Ollama LLM integration via the configured `OLLAMA_MODEL` — near-perfect accuracy for any language, strong food taxonomy
- If `OLLAMA_URL` is configured, advanced mode is used automatically; otherwise falls back to simple
- **Learning system**: Save your manual categorizations as hints — future sorts use your corrections first (98% confidence)
- Hints are per-user, per-list and work with both AI modes

### Admin Interface (`/admin`)
- Protected by HTTP Basic auth via `ADMIN_USERNAME` / `ADMIN_PASSWORD` env vars (admin is disabled if either is empty).
- Single-page dashboard with four tabs:
  - **Stats**: total users / lists / items / bonus cards plus live "active users right now" (WebSocket-connected across list rooms).
  - **Users**: list, edit (display name / email / locale / color), delete (cascades owned lists, shares, hints, bonus cards), and reset password. Password reset generates a strong random password and always displays it to the admin; optionally also delivers it by email (honest about delivery status — if SMTP fails, the admin can hand it over manually).
  - **Lists**: all lists with owner attribution and counts. Drill-down view allows reordering and deleting items and categories per list, or deleting the whole list.
  - **Runtime Config**: shows each effective Ollama model alongside its env-sourced value and current override. Set or clear per-model overrides — in-memory, resets on backend restart. A yellow banner reminds the operator that these are temporary so the `.env` / secret remains the source of truth.

### Bonus Cards (Bonuskarten)
- Dedicated page for loyalty / bonus cards (Payback, Shell ClubSmart, etc.)
- Add cards with name, optional description, and a photo (camera or gallery upload)
- Share individual cards with other users (view-only) by email
- "Leave" a shared card at any time — the owner can re-share later
- Owner-only controls: edit photo, delete card, manage shares
- Images stored as SQLite BLOBs alongside item photos

### User Management
- Email + password registration (no other personal info required)
- Password reset via email link (SMTP configurable)
- "Remember me" option — stay logged in for up to 30 days
- Per-user display color for shared list attribution; auto-assigned from a distinct palette on registration (manual colour choice is honoured and preserved across any future migrations)
- Re-roll at share time: if an invitee hasn't customised their colour and would collide with the owner or other recipients, their colour is swapped to a distinct palette value automatically

### Mobile & PWA
- Installable as a PWA on iOS and Android
- Mobile-first responsive design with Tailwind CSS
- Offline detection with status banner
- Service worker with Workbox for app shell caching
- Touch-friendly controls (handle-based drag & drop, bottom sheet dialogs)
- **Force-update on deploy**: `skipWaiting` + `clientsClaim` + `cleanupOutdatedCaches` in Workbox, `controllerchange` auto-reload on the client, `Cache-Control: no-cache` on `index.html` / `sw.js` / `registerSW.js` / `manifest.webmanifest` in nginx — a new deploy takes effect on the next page load without manual hard refresh

### Internationalization
- German and English included
- Auto-detects browser language (German-speaking locales → German, else English)
- Flag-based language picker in the navbar
- Easily extensible — add a JSON file for new languages

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python 3.12, FastAPI, uvicorn |
| Database | SQLite with WAL mode (aiosqlite) |
| ORM | SQLModel (SQLAlchemy + Pydantic) |
| Auth | JWT (PyJWT) + bcrypt |
| Email | aiosmtplib (any SMTP provider) |
| ML (simple) | fastembed (ONNX Runtime), ~120MB model, built-in |
| ML (advanced + vision + voice + recipes) | Ollama API — six per-feature model slots (see below) |
| Speech-to-text | Web Speech API (browser-native, no server dependency) |
| Frontend | Svelte 5, Vite |
| CSS | Tailwind CSS |
| Real-time | WebSockets (FastAPI native) |
| PWA | vite-plugin-pwa + Workbox |
| Containers | Docker Compose (Nginx + uvicorn) |

## Quick Start (Docker Compose)

### Prerequisites
- Docker and Docker Compose plugin
- Git

### Deploy

```bash
git clone https://github.com/flyersa/3inkauf.git
cd 3inkauf

# Create environment file
cp .env.example .env
# Edit .env with your settings (secret key, SMTP credentials, etc.)

# Build and start
docker compose build
docker compose up -d

# App is now running on http://localhost:80
```

### Environment Variables

Create a `.env` file in the project root:

```env
SECRET_KEY=your-random-secret-key-here
BASE_URL=http://your-domain-or-ip
DATABASE_URL=sqlite+aiosqlite:////data/grocery.db

# SMTP for password reset, recipe email, and admin-triggered password resets.
# Optional — if absent, reset links are logged to the console instead of sent.
SMTP_HOST=email-smtp.eu-central-1.amazonaws.com
SMTP_PORT=587
SMTP_USER=your-smtp-user
SMTP_PASSWORD=your-smtp-password
SMTP_SENDER=no-reply@yourdomain.com
SMTP_USE_TLS=true

# ML model for simple auto-sort (default works out of the box)
ML_MODEL_NAME=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2

# Ollama — if set, enables all AI-backed features (scan, voice, recipes, fridge,
# item-from-photo, advanced auto-sort). Without OLLAMA_URL the AI-specific
# buttons are hidden and simple auto-sort still works.
OLLAMA_URL=http://your-ollama-host:11434

# Per-feature model slots. Each is independently overridable; empty values fall
# back down the chain shown in the comment.
OLLAMA_MODEL=gemma4:e4b                   # auto-sort (text) + base fallback for all slots below
OLLAMA_OCR_MODEL=gemma4:31b-cloud         # paper-list scan (handwriting OCR + categorize). empty -> OLLAMA_MODEL
OLLAMA_AUDIO_MODEL=gemma4:e2b             # voice intent parsing. empty -> OLLAMA_MODEL
OLLAMA_RECIPE_MODEL=gemma4:e2b            # recipe generation (ingredients + steps). empty -> OLLAMA_MODEL
OLLAMA_FRIDGE_MODEL=qwen3.5:397b-cloud    # fridge interior scan. empty -> OLLAMA_OCR_MODEL -> OLLAMA_MODEL
OLLAMA_ITEM_MODEL=qwen3.5:397b-cloud      # single-item photo → list entry. empty -> OLLAMA_FRIDGE_MODEL -> OLLAMA_MODEL

# Admin interface — when both are set, /admin is enabled with HTTP Basic auth.
# Leave either empty to disable the admin endpoints entirely.
ADMIN_USERNAME=admin
ADMIN_PASSWORD=some-strong-random-password
```

Generate a secret key:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Container Architecture

```
[Nginx :80] --> [FastAPI :8000] --> [SQLite on volume /data]
     |                 |
  serves SPA      REST API + WebSocket
  proxies /api/   ML model loaded at startup
  proxies /ws/    Ollama calls (vision + text) over HTTP
```

- **Frontend container**: Nginx serving the built SPA (~26MB image)
- **Backend container**: Python + FastAPI + ML model (~450MB image)
- **Data volume**: SQLite database + uploaded images (stored as BLOBs)

## Development Setup

```bash
# Backend
cd backend
python3 -m venv venv
source venv/bin/activate
pip install fastapi[standard] uvicorn[standard] sqlmodel aiosqlite alembic \
    pyjwt "passlib[bcrypt]" "bcrypt==4.3.0" aiosmtplib pydantic-settings \
    fastembed numpy slowapi python-multipart jinja2 requests
cp ../.env .
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend (separate terminal)
cd frontend
npm install
npm install svelte-dnd-action vite-plugin-pwa --legacy-peer-deps
npm run dev
```

The Vite dev server proxies `/api` and `/ws` to the backend on port 8000.

> **Voice & microphone**: the Web Speech API requires HTTPS. When testing from a mobile device, either use `localhost` forwarding or put the dev host behind TLS (e.g., via a Cloudflare Tunnel). On plain HTTP the browser will silently refuse microphone access.

## Docker Hub

Pre-built images are available on Docker Hub:

- **Backend**: `flyersa/3inkauf:backend-latest`
- **Frontend**: `flyersa/3inkauf:frontend-latest`

## Kubernetes Deployment

A complete k8s manifest is included in `k8s.yaml`. It deploys the app with a single command.

### Prerequisites
- A Kubernetes cluster with an ingress controller
- A storage class that supports `ReadWriteOnce` PVCs
- `kubectl` configured for your cluster

### Steps

1. **Edit `k8s.yaml`** — update these values for your environment:
   - `Secret` → set your own `SECRET_KEY`, `BASE_URL`, SMTP credentials, and optionally `OLLAMA_URL` / `OLLAMA_MODEL`
   - `PersistentVolumeClaim` → change `storageClassName` to match your cluster (default: `openebs-lvmpv`)
   - `Ingress` → change `ingressClassName` and `host` to match your setup

2. **Apply the manifest:**
   ```bash
   kubectl apply -f k8s.yaml
   ```

3. **Verify the deployment:**
   ```bash
   kubectl -n 3inkauf get pods,pvc,ingress
   ```

   You should see both pods `Running`, the PVC `Bound`, and the ingress with your host assigned.

4. **Check backend health:**
   ```bash
   kubectl -n 3inkauf exec deploy/frontend -- curl -s http://backend:8000/api/v1/health
   ```

### What gets created

| Resource | Name | Purpose |
|----------|------|---------|
| Namespace | `3inkauf` | Isolation |
| Secret | `3inkauf-secrets` | Env vars (JWT key, SMTP, DB path, Ollama URL/model) |
| PVC | `3inkauf-data` | 50Gi volume for SQLite + image BLOBs |
| Deployment | `backend` | FastAPI + ML model (1 replica, Recreate strategy, 4 CPU / 4 Gi limit) |
| Deployment | `frontend` | Nginx serving SPA (1 replica) |
| Service | `backend` | ClusterIP :8000 |
| Service | `frontend` | ClusterIP :80 |
| Ingress | `3inkauf` | Routes external traffic to frontend |

### Architecture on k8s

```
[Ingress] → [frontend Service :80] → [Nginx pod]
                                         ├── serves SPA (static files)
                                         ├── proxies /api/* → [backend Service :8000]
                                         └── proxies /ws/*  → [backend Service :8000]

[backend pod] → [PVC /data] → SQLite database + image BLOBs
                    └── ML model loaded in memory at startup
                    └── outbound → Ollama host (vision + text intent)
```

### Notes

- **Ollama integration**: Add `OLLAMA_URL` and `OLLAMA_MODEL` to the Secret to enable advanced AI sort, paper-list scanning, and voice-intent parsing. The Ollama instance must be reachable from the backend pod.
- **Single replica** for the backend is required since SQLite doesn't support concurrent writes from multiple processes. If you need horizontal scaling, migrate to PostgreSQL.
- **Recreate strategy** on the backend deployment ensures the PVC is unmounted before a new pod starts (SQLite file locking).
- All data (database + uploaded images) is stored in the PVC. Back up the PVC to preserve data.
- The ML model (~120MB) is baked into the backend Docker image and loaded into memory on startup. First startup takes ~30 seconds.

## API Overview

All endpoints under `/api/v1`:

| Endpoint | Description |
|----------|-------------|
| `POST /auth/register` | Create account (random palette color assigned) |
| `POST /auth/login` | Login (returns JWT) |
| `POST /auth/forgot-password` | Send reset email |
| `PATCH /auth/me` | Update display name / color / locale |
| `GET /lists` | All lists (owned + shared, with owner attribution) |
| `POST /lists` | Create list (rejects duplicate name for owner) |
| `PATCH /lists/{id}` | Rename list (rejects duplicate name for owner) |
| `DELETE /lists/{id}/shares/me` | Leave a shared list |
| `GET /lists/{id}/items` | List items |
| `POST /lists/{id}/items` | Add item (rejects duplicate name within list) |
| `PATCH /lists/{id}/items/{id}/check` | Toggle item checked |
| `POST /lists/{id}/items/{id}/image` | Upload photo |
| `POST /lists/{id}/categories` | Create category |
| `POST /lists/{id}/shares` | Share list by email (auto-reroll invitee colour on conflict) |
| `POST /lists/{id}/auto-sort` | AI auto-categorize |
| `POST /lists/{id}/save-hints` | Save sort hints |
| `POST /lists/scan` | Upload a photo of a paper list → proposed items + categories |
| `POST /lists/scan-fridge` | Upload a photo of a fridge interior → detected groceries with per-item confidence |
| `POST /lists/{id}/items/from-photo` | Photograph one product → AI-identified item added to the list (photo also attached as the item's image) |
| `POST /voice/intent` | Parse a spoken transcript into a structured command |
| `POST /lists/{id}/recipes/from-items` | Suggest 3 full recipes (with steps) based on what's on the list |
| `POST /recipes/from-query` | Expand a free-text recipe request into a structured recipe (ingredients + steps) |
| `POST /recipes/full` | Fallback: expand a recipe title into a full recipe (rarely needed — `from-items` / `from-query` already include steps) |
| `POST /recipes/email` | Email the rendered recipe to the current user's address |
| `GET  /admin/stats` | Total user / list / item counts plus live WebSocket-connected users (HTTP Basic) |
| `GET  /admin/users` / `PATCH` / `DELETE /admin/users/{id}` | User management (HTTP Basic) |
| `POST /admin/users/{id}/reset-password` | Generate a new password, optionally email it, always return it to the admin (HTTP Basic) |
| `GET  /admin/lists` / `DELETE` + reorder/delete items & categories | List management (HTTP Basic) |
| `GET/POST/DELETE /admin/runtime-config` | Read or temporarily override Ollama model slots until backend restart (HTTP Basic) |
| `GET /bonus-cards` | List your bonus cards + cards shared with you |
| `POST /bonus-cards` | Create a new bonus card |
| `POST /bonus-cards/{id}/image` | Upload a card photo |
| `POST /bonus-cards/{id}/shares` | Share a bonus card by email (view-only) |
| `DELETE /bonus-cards/{id}/shares/me` | Leave a shared bonus card |
| `WS /ws/lists/{id}?token=` | Real-time sync |
| `GET /health` | Health check — reports `model_loaded` and `ollama_enabled` |

Full API docs available at `/docs` (Swagger UI) when running the backend.

## Project Structure

```
3inkauf/
├── docker-compose.yml
├── Dockerfile.backend
├── Dockerfile.frontend
├── nginx.conf                # force-refresh headers on index/SW
├── .env.example
├── backend/
│   └── app/
│       ├── main.py           # App entry, routers, WebSocket
│       ├── config.py         # Settings (env vars)
│       ├── database.py       # SQLite + one-shot migrations (incl. user-colour randomiser)
│       ├── models/           # Database models (incl. BonusCard, BonusCardShare)
│       ├── schemas/          # Request/response schemas
│       ├── routers/
│       │   ├── auth.py, lists.py, categories.py, items.py (incl. /items/from-photo), sharing.py, ml.py, images.py
│       │   ├── bonus_cards.py       # CRUD + sharing + leave
│       │   ├── lists_scan.py        # POST /lists/scan (paper OCR) + /lists/scan-fridge (fridge interior)
│       │   ├── voice.py             # POST /voice/intent
│       │   ├── recipes.py           # /recipes/{from-items,from-query,full,email}
│       │   └── admin.py             # HTTP Basic-gated /admin endpoints (stats, users, lists, runtime-config)
│       ├── services/
│       │   ├── ml_service.py        # fastembed + Ollama (sort, scan, fridge, voice-intent, recipes, item-from-photo)
│       │   └── email_service.py     # aiosmtplib with 15s timeout
│       └── core/
│           ├── security.py, deps.py, websocket.py
│           ├── admin_auth.py        # HTTP Basic dependency using ADMIN_USERNAME / ADMIN_PASSWORD
│           ├── runtime_config.py    # in-memory per-model overrides with deterministic fallback chain
│           └── palette.py           # distinct-colour palette for auto-assignment
└── frontend/
    ├── src/
    │   ├── App.svelte        # Router + global UI
    │   ├── main.js           # SW registration + auto-reload on controller change
    │   ├── lib/
    │   │   ├── api.js, auth.js, i18n.js, store.js, ws.js
    │   │   ├── voice.js              # Web Speech wrapper (continuous session)
    │   │   └── voice_dispatch.js     # Intent → REST call dispatcher
    │   ├── locales/          # de.json, en.json
    │   ├── routes/           # Page components (incl. BonusCards.svelte, Admin.svelte)
    │   └── components/       # Shared (Navbar, ShareDialog, AutoSortDialog, RecipeDialog, Spinner, VoiceButton)
    └── public/               # Icons, manifest
```

## License

MIT
