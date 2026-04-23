# podking

Personal YouTube and Apple Podcast summarizer with hybrid search and auto-ingest from followed channels/feeds.

See `docs/superpowers/specs/2026-04-22-podking-design.md` for the full design.

## Local development

Prereqs: Homebrew Postgres 16 + pgvector, `uv` (install: `curl -LsSf https://astral.sh/uv/install.sh | sh`), Node 20+.

```bash
brew install postgresql@16 pgvector
brew services start postgresql@16
./scripts/setup-local-db.sh   # creates podking + podking_test DBs and enables vector
cp .env.example .env
# edit .env — generate FERNET_KEY and SESSION_SECRET_KEY, add Google OAuth creds
uv sync
uv run alembic upgrade head
uv run uvicorn podking.main:app --reload
```

In a second shell:
```bash
cd frontend
npm install
npm run dev
```
