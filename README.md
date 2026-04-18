# 3inkauf

A lightweight, mobile-first Progressive Web App (PWA) for collaborative grocery shopping with smart auto-categorization.

## Features

### Shopping Lists
- Create and manage multiple named shopping lists
- Share lists with other users for real-time collaborative editing
- Color-coded items showing who added each item on shared lists
- WebSocket-based real-time sync — changes appear instantly for all users

### Items & Categories
- Add items with optional quantity
- Create custom categories per list (e.g., "Obst", "Backwaren", "Getränke")
- Drag & drop to reorder items and categories (handle-based, mobile-friendly)
- Move items between categories via a quick category picker
- Check off items while shopping (tap the circle to mark as done)
- Attach photos to items (take a photo or choose from gallery)
- Clear all items button (preserves categories for reuse)

### Smart Auto-Sort
- One-tap AI button assigns uncategorized items to matching categories
- Uses multilingual sentence embeddings (paraphrase-multilingual-MiniLM-L12-v2)
- Works with German, English, and handles typos
- **Learning system**: Save your manual categorizations as hints — future sorts use your corrections for 98% accuracy on learned items
- Hints persist per user across all lists

### User Management
- Email + password registration (no other personal info required)
- Password reset via email link (SMTP configurable)
- "Remember me" option — stay logged in for up to 30 days
- Per-user display color for shared list attribution

### Mobile & PWA
- Installable as a PWA on iOS and Android
- Mobile-first responsive design with Tailwind CSS
- Offline detection with status banner
- Service worker with Workbox for app shell caching
- Touch-friendly controls (handle-based drag & drop, bottom sheet dialogs)

### Internationalization
- German and English included
- Auto-detects browser language (German-speaking locales → German, else English)
- Language switcher available on login page and in the app
- Easily extensible — add a JSON file for new languages

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python 3.12, FastAPI, uvicorn |
| Database | SQLite with WAL mode (aiosqlite) |
| ORM | SQLModel (SQLAlchemy + Pydantic) |
| Auth | JWT (PyJWT) + bcrypt |
| Email | aiosmtplib (any SMTP provider) |
| ML | fastembed (ONNX Runtime), ~120MB model |
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

# SMTP for password reset emails (optional - reset links logged to console if not configured)
SMTP_HOST=your-smtp-host
SMTP_PORT=587
SMTP_USER=your-smtp-user
SMTP_PASSWORD=your-smtp-password
SMTP_SENDER=no-reply@yourdomain.com
SMTP_USE_TLS=true

# ML model (default works out of the box)
ML_MODEL_NAME=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
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
  proxies /ws/
```

- **Frontend container**: Nginx serving the built SPA (~25MB image)
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
    fastembed numpy slowapi python-multipart jinja2
cp ../.env .
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend (separate terminal)
cd frontend
npm install
npm install svelte-dnd-action vite-plugin-pwa --legacy-peer-deps
npm run dev
```

The Vite dev server proxies `/api` and `/ws` to the backend on port 8000.

## Kubernetes Deployment

The app is designed to be k8s-ready:
- Stateless containers (only the SQLite volume needs persistence)
- Health endpoint at `GET /api/v1/health` for readiness/liveness probes
- All secrets via environment variables (use Kubernetes Secrets)
- For multi-pod scaling: migrate SQLite → PostgreSQL and add Redis for WebSocket fan-out

## API Overview

All endpoints under `/api/v1`:

| Endpoint | Description |
|----------|-------------|
| `POST /auth/register` | Create account |
| `POST /auth/login` | Login (returns JWT) |
| `POST /auth/forgot-password` | Send reset email |
| `GET /lists` | All lists (owned + shared) |
| `POST /lists` | Create list |
| `GET /lists/{id}/items` | List items |
| `POST /lists/{id}/items` | Add item |
| `PATCH /lists/{id}/items/{id}/check` | Toggle item checked |
| `POST /lists/{id}/items/{id}/image` | Upload photo |
| `POST /lists/{id}/categories` | Create category |
| `POST /lists/{id}/shares` | Share list by email |
| `POST /lists/{id}/auto-sort` | AI auto-categorize |
| `POST /lists/{id}/save-hints` | Save sort hints |
| `WS /ws/lists/{id}?token=` | Real-time sync |
| `GET /health` | Health check |

Full API docs available at `/docs` (Swagger UI) when running the backend.

## Project Structure

```
3inkauf/
├── docker-compose.yml
├── Dockerfile.backend
├── Dockerfile.frontend
├── nginx.conf
├── .env.example
├── backend/
│   └── app/
│       ├── main.py            # App entry, routers, WebSocket
│       ├── config.py          # Settings (env vars)
│       ├── database.py        # SQLite + migrations
│       ├── models/            # Database models
│       ├── schemas/           # Request/response schemas
│       ├── routers/           # API endpoints
│       ├── services/          # Business logic (email, ML)
│       └── core/              # Auth, dependencies, WebSocket manager
└── frontend/
    ├── src/
    │   ├── App.svelte         # Router + global UI
    │   ├── lib/               # API client, auth, i18n, WebSocket
    │   ├── locales/           # de.json, en.json
    │   ├── routes/            # Page components
    │   └── components/        # Shared components
    └── public/                # Icons, manifest
```

## License

MIT
