# podking

A self-hosted personal summarizer for YouTube videos and podcast episodes.
Paste a URL, get a structured AI summary in your library a few minutes later.
Search across everything semantically. Subscribe to channels and feeds, then
pick which episodes you actually want summarized. One click on any summary
copies a clean reader URL you can paste into ElevenReader (or any
read-it-later app) to listen to it.

See `docs/superpowers/specs/2026-04-22-podking-design.md` for the full design.

## Stack

- **Backend**: FastAPI · SQLAlchemy 2 (async) · asyncpg · Postgres 16 + pgvector
- **Frontend**: React + TypeScript · Vite · TanStack Query · Tailwind · shadcn/ui
- **External services**: Anthropic Claude (summaries) · ElevenLabs Scribe
  (transcription) · Voyage AI (embeddings) · Listen Notes (podcast search)
- **Auth**: Google OAuth + email allowlist
- **Deploy**: Railway (single container + managed Postgres)

## Local development

### Prereqs

- Homebrew Postgres 16 + pgvector
- [`uv`](https://docs.astral.sh/uv/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Node 20+

### One-time setup

```bash
# 1. Postgres
brew install postgresql@16 pgvector
brew services start postgresql@16
./scripts/setup-local-db.sh        # creates podking + podking_test, enables pgvector

# 2. Env file
cp .env.example .env
# Generate the secrets it asks for:
python -c "import secrets; print(secrets.token_urlsafe(32))"     # SESSION_SECRET_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # FERNET_KEY

# 3. Google OAuth (see "Auth setup" below)
#    Paste GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET into .env
#    Add your email to ALLOWED_EMAILS (comma-separated)

# 4. Install + migrate
uv sync
uv run alembic upgrade head

# 5. Frontend
cd frontend && npm install && npm run build && cd ..
```

### Run it

```bash
uv run uvicorn podking.main:app --reload
```

Open http://localhost:8000. Sign in with a Google account that's on
`ALLOWED_EMAILS`.

> **Why not `npm run dev`?** The Vite dev server runs on a different port
> than the backend. Google OAuth sets the session cookie on `:8000`, so
> the cookie won't reach Vite at `:5173`. For local development, build the
> frontend once (`npm run build`) and let FastAPI serve the bundle. Run
> `npm run dev` only if you're actively iterating on UI and don't mind
> using two terminals plus a workaround for cookies.

## Auth setup (Google OAuth)

1. **Google Cloud Console → APIs & Services → OAuth consent screen** —
   choose *External*, fill in app name, add yourself as a *Test user*.
2. **Credentials → Create credentials → OAuth client ID** — type *Web
   application*. Authorized redirect URI: `http://localhost:8000/auth/callback`
   (must match `GOOGLE_REDIRECT_URI` in `.env` exactly).
3. Copy Client ID + Client Secret into `.env`.

## API keys

Three keys are entered **per-user via the Settings page**, not via env:

- **Anthropic** — for Claude summaries (`sk-ant-…`)
- **ElevenLabs** — for transcription via Scribe
- **Voyage** — for embeddings used in semantic search

Keys are encrypted at rest with `FERNET_KEY` before storage and never
returned in API responses (just `{ set: true }`).

The fourth key (Listen Notes) is **server-side**, in `.env`:

- `LISTEN_NOTES_API_KEY` — enables the podcast search box on
  `/subscriptions`. Free tier works fine for the supported features.
  Get a key at https://www.listennotes.com/api/.

## Reader links (ElevenReader)

Every summary has a token-gated public URL at
`/reader/{token}/{summary_id}.html`. The 🎧 Listen button on each card
copies that URL to your clipboard. Paste it into ElevenReader → "Paste a
link" and the app fetches the clean HTML and narrates it. Token lives in
your user row and is rotatable from Settings (breaks any links you've
shared).

## Generated podcast feed

Each summary has a **🎙 Generate audio** button that produces a ~5–10
minute two-host conversation about the summary, published to a personal
RSS feed you can subscribe to in Apple Podcasts, Spotify, Overcast, or
any podcast app.

### One-time server setup

1. Create an empty **public** GitHub repo, e.g. `you/podking-audio`,
   and enable GitHub Pages on the `main` branch root (`/`).
2. Create a [fine-grained PAT](https://github.com/settings/personal-access-tokens/new)
   scoped to that one repo with `Contents: read/write` and
   `Pages: write`.
3. Set in `.env`:
   - `GITHUB_PAT=` your PAT
   - `GITHUB_AUDIO_REPO=you/podking-audio`
   - `GITHUB_AUDIO_BASE_URL=https://you.github.io/podking-audio`
   - `PODKING_FEED_OWNER_EMAIL=` your iTunes-owner email
4. Restart the backend. Each user now gets a personal feed at
   `${GITHUB_AUDIO_BASE_URL}/u/{feed_token}/feed.xml`.

Subscribers fetch directly from GitHub Pages, so episodes keep working
even when the podking server is offline — useful if you're running this
on a home server with intermittent uptime.

### Defaults and overrides

Two ElevenLabs voice IDs ship as `.env` defaults
(`ELEVENLABS_TTS_DEFAULT_VOICE_A` / `_B`). Users can override either or
both on the Settings page; leaving a field blank falls back to the
server default.

Retention: the feed keeps the most recent 30 episodes per user; older
episodes are pruned from the repo automatically on each publish.

## Tests

```bash
uv run pytest                   # backend (~60 tests, real Postgres)
cd frontend && npm test         # vitest, when present
```

Postgres + pgvector for tests via the local `podking_test` database.
External APIs are stubbed at the HTTP boundary with `respx` (and
`monkeypatch` for direct module-level fakes).

### Playwright e2e

A small browser-driven happy-path suite lives in `frontend/e2e/`. Auth
runs through a `/test/login` route only registered when `TEST_MODE=1`,
so e2e doesn't need real Google OAuth.

In one terminal, start a test-mode backend:

```bash
TEST_MODE=1 \
  ALLOWED_EMAILS=allowed@example.com \
  APP_BASE_URL=http://127.0.0.1:8001 \
  GOOGLE_REDIRECT_URI=http://127.0.0.1:8001/auth/callback \
  uv run uvicorn podking.main:app --host 127.0.0.1 --port 8001
```

In another, run the suite:

```bash
cd frontend && npm run e2e          # headless, ~3s for 6 tests
cd frontend && npm run e2e:ui       # interactive Playwright UI
```

`TEST_MODE=1` must NEVER be set in production — it bypasses Google OAuth.

## Deployment (Railway)

The repo includes `nixpacks.toml` and `railway.toml`. The single
container builds the frontend, then runs the backend serving the SPA
bundle. Postgres is a managed add-on; ensure the `vector` extension is
enabled (`CREATE EXTENSION vector;`).

Env vars to set in Railway:

- `DATABASE_URL` (provided by Postgres add-on)
- `SESSION_SECRET_KEY`, `FERNET_KEY` — generate fresh ones
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`
  (must match the production callback URL)
- `APP_BASE_URL` — your production URL
- `ALLOWED_EMAILS`
- `LISTEN_NOTES_API_KEY` (optional)
- `MAX_DURATION_SECONDS`, `AUDIO_STORAGE_PATH`, `LOG_LEVEL` (optional)

## Architecture at a glance

```
Browser (React SPA)
  ↓ HTTPS
FastAPI app
  ├── /auth      Google OAuth, session cookies
  ├── /api       REST: jobs, summaries, search, tags, subscriptions, settings
  ├── /events    Server-Sent Events (job progress)
  ├── /reader    Public token-gated summary HTML (no session auth)
  ├── /assets    React bundle
  ├── job worker     in-process asyncio loop
  └── schedulers     subscription poller (metadata refresh) + retention cleanup
  ↓
Postgres + pgvector
  └── users, jobs, episodes, transcripts, summaries, tags, subscriptions

External services (called from the worker):
  ├── yt-dlp           YouTube metadata + captions + audio
  ├── iTunes Search    Apple Podcast → RSS feed URL
  ├── feedparser       RSS → episode audio URL
  ├── Listen Notes     podcast search
  ├── ElevenLabs       transcription
  ├── Anthropic        summarization
  └── Voyage           embeddings
```

## Project layout

```
backend/
  podking/
    api/         FastAPI routers
    worker/      job pipeline + external clients
    models.py    SQLAlchemy ORM
    schemas.py   Pydantic request/response shapes
    main.py      app factory
  alembic/       migrations (currently 0001–0006)
frontend/
  src/
    pages/       one component per route
    components/  shared UI (TopNav, ListenButton, shadcn primitives)
    api.ts       backend client + types
    hooks/       useMe, useJobProgress
tests/           pytest suite (testcontainers Postgres)
docs/            spec + lessons
scripts/         dev helpers
```
