# podking — Requirements & Design

**Status:** Draft
**Date:** 2026-04-22
**Owner:** Kunal Morparia
**Repo:** `podking` (GitHub, public)

## 1. Summary

A self-hosted web app that ingests YouTube videos and Apple Podcast episodes, produces structured AI summaries with tags, stores them in a searchable personal library, and auto-processes new episodes from followed channels and feeds.

- Transcription: ElevenLabs Scribe (fallback to YouTube captions when available).
- Summarization: Anthropic Claude.
- Embeddings (semantic search): Voyage AI.
- Storage: PostgreSQL with `pgvector`.
- Deployment: Railway (single Docker container + managed Postgres).
- Auth: Google OAuth, restricted to an email allowlist.

## 2. Goals and non-goals

### Goals (v1)

- Submit a YouTube or Apple Podcast URL; get a structured summary within minutes, with live progress.
- Follow YouTube channels and podcast RSS feeds; new episodes are detected and processed automatically.
- Search the personal library with hybrid (full-text + semantic) search and tag filters.
- Re-summarize an existing transcript with the current system prompt (one click).
- Editable system prompt in settings; LLM auto-suggests tags on each summary.
- Multi-user via Google OAuth with an email allowlist; per-user data isolation.

### Non-goals (v1)

- Morning digest email. Designed for but deferred to phase 2.
- Audio clips / "best parts" highlights. Schema leaves room, deferred to a later phase.
- Mobile app. Web UI is responsive; no native client.
- Shared/public summaries, social or community features.
- Admin UI for the allowlist; managed via an `ALLOWED_EMAILS` env var.
- Sentry / APM. Railway logs only.
- Rate limiting or abuse protection beyond allowlist.

## 3. User stories

1. As a user, I paste a YouTube link. The app checks for captions; if missing, it downloads audio and transcribes via ElevenLabs. I see a progress bar. When done, I see a structured summary with tags.
2. As a user, I paste an Apple Podcast episode URL. The app resolves the feed, matches the episode by GUID, downloads the enclosure, transcribes, summarizes, tags.
3. As a user, I follow a YouTube channel and a podcast RSS feed. New episodes are ingested automatically without me pasting links.
4. As a user, I search "stoicism and grief" and get summaries that mention the concept even if the literal words aren't present (semantic). I narrow by the `#philosophy` tag.
5. As a user, I update my system prompt and hit "Re-summarize" on an old episode; a new summary row is created with the new prompt, leaving old history intact.
6. As a user, I add and remove tags on any summary. The LLM-suggested tags are distinguishable from my manual ones.
7. As a user, I sign in with Google. If my email isn't on the allowlist, I get a clear "not allowed" page.

## 4. Architecture

Single FastAPI service, single Postgres database, React SPA served as static files by the same service.

```
Browser (React SPA)
    │  HTTPS
    ▼
FastAPI app  ─────────────────────────────────────
    ├── /auth         Google OAuth, session cookies
    ├── /api          REST (jobs, summaries, search, tags, subscriptions, settings)
    ├── /events       Server-Sent Events for job progress
    ├── /static       React bundle
    ├── job worker    In-process asyncio loop
    └── schedulers    Subscription poller, retention cleanup
    │
    ▼
Postgres + pgvector
    ├── users, jobs, episodes, transcripts, summaries
    ├── tags, summary_tags, subscriptions
    └── user_settings

External services (called from the job worker):
    ├── yt-dlp              YouTube audio + captions probe
    ├── iTunes Search API   Apple Podcast URL → RSS feed URL
    ├── feedparser          RSS feed → episode audio URL
    ├── ElevenLabs Scribe   audio → transcript
    ├── Anthropic Claude    transcript → structured summary + tags
    └── Voyage AI           summary → embedding vector

Local volume (Railway):
    └── /data/audio/        raw audio files, 7-day TTL
```

**Why these picks:**

- **Single service (job worker in-process)**: for a personal app at ~1–5 users, a separate worker + Redis adds cost and complexity without meaningful benefit. Restart-safety is handled by marking interrupted jobs failed on boot; users re-run.
- **pgvector over a separate vector DB**: already on Postgres, no extra service, performant for thousands of summaries.
- **Voyage AI over OpenAI embeddings**: Anthropic's recommended embedding provider, pairs cleanly with Claude.
- **SSE over WebSockets**: one-way progress updates need one-way transport; SSE is simpler, works through proxies, auto-reconnects natively.

## 5. Tech stack

**Backend:**
- Python 3.12, FastAPI, Uvicorn
- `authlib` for Google OAuth
- `itsdangerous` + Starlette sessions for cookies
- `sqlalchemy` 2.x (async) + `asyncpg`
- `alembic` for migrations
- `pgvector` extension
- `yt-dlp` for YouTube download and caption extraction
- `feedparser` for RSS
- `httpx` for external API calls
- `anthropic`, `elevenlabs`, `voyageai` SDKs
- `cryptography.fernet` for per-user API key encryption
- `structlog` for structured logging
- `pytest`, `respx`, `testcontainers` for tests

**Frontend:**
- React 18 + TypeScript + Vite
- TanStack Query (server state)
- `react-router`
- Tailwind CSS + `shadcn/ui`
- `vitest` + Playwright for tests

**Infrastructure:**
- Docker (single image: multi-stage build with Node for frontend, Python for backend)
- `docker-compose.yml` for local dev (app + Postgres+pgvector)
- Railway for production (app service + managed Postgres add-on with `pgvector` enabled)
- GitHub Actions for CI

## 6. Data model

Postgres. Timestamps are `timestamptz`. All foreign keys on delete cascade unless noted.

```sql
users
  id             uuid PRIMARY KEY
  email          text UNIQUE NOT NULL
  google_sub     text UNIQUE NOT NULL   -- Google's stable user id
  display_name   text
  created_at     timestamptz NOT NULL DEFAULT now()

user_settings
  user_id                       uuid PRIMARY KEY REFERENCES users(id)
  system_prompt                 text NOT NULL
  anthropic_api_key_encrypted   bytea
  elevenlabs_api_key_encrypted  bytea
  voyage_api_key_encrypted      bytea
  updated_at                    timestamptz NOT NULL DEFAULT now()

jobs
  id                uuid PRIMARY KEY
  user_id           uuid NOT NULL REFERENCES users(id)
  kind              text NOT NULL CHECK (kind IN ('youtube','podcast','resummarize'))
  source_url        text
  episode_id        uuid REFERENCES episodes(id)
  status            text NOT NULL CHECK (status IN
                      ('queued','fetching','transcribing','summarizing','embedding','done','failed'))
  progress_pct      int NOT NULL DEFAULT 0
  progress_message  text
  error             text
  created_at        timestamptz NOT NULL DEFAULT now()
  updated_at        timestamptz NOT NULL DEFAULT now()
  started_at        timestamptz
  finished_at       timestamptz

episodes
  id                 uuid PRIMARY KEY
  user_id            uuid NOT NULL REFERENCES users(id)
  source_type        text NOT NULL CHECK (source_type IN ('youtube','podcast'))
  source_url         text NOT NULL
  external_id        text NOT NULL   -- youtube video id or podcast <guid>
  title              text
  author             text
  published_at       timestamptz
  duration_seconds   int
  thumbnail_url      text
  audio_path         text            -- local path; nulled after TTL cleanup
  audio_expires_at   timestamptz
  created_at         timestamptz NOT NULL DEFAULT now()
  UNIQUE (user_id, source_type, external_id)

transcripts
  id          uuid PRIMARY KEY
  episode_id  uuid NOT NULL UNIQUE REFERENCES episodes(id)
  source      text NOT NULL CHECK (source IN ('youtube_captions','elevenlabs'))
  text        text NOT NULL
  segments    jsonb   -- timestamped segments if provider returned them
  created_at  timestamptz NOT NULL DEFAULT now()

summaries
  id             uuid PRIMARY KEY
  episode_id     uuid NOT NULL REFERENCES episodes(id)
  user_id        uuid NOT NULL REFERENCES users(id)
  system_prompt  text NOT NULL          -- snapshot used for this summary
  model          text NOT NULL          -- e.g. 'claude-sonnet-4-6'
  content        jsonb NOT NULL         -- structured: {tldr, key_points, quotes, suggested_tags}
  embedding      vector(1024)           -- Voyage voyage-3; nullable if embedding failed
  created_at     timestamptz NOT NULL DEFAULT now()

tags
  id       uuid PRIMARY KEY
  user_id  uuid NOT NULL REFERENCES users(id)
  name     text NOT NULL
  UNIQUE (user_id, name)

summary_tags
  summary_id  uuid NOT NULL REFERENCES summaries(id)
  tag_id      uuid NOT NULL REFERENCES tags(id)
  source      text NOT NULL CHECK (source IN ('llm','user'))
  PRIMARY KEY (summary_id, tag_id)

subscriptions
  id                     uuid PRIMARY KEY
  user_id                uuid NOT NULL REFERENCES users(id)
  kind                   text NOT NULL CHECK (kind IN ('youtube_channel','podcast_feed'))
  feed_url               text NOT NULL   -- YouTube channel RSS or podcast RSS
  title                  text
  last_checked_at        timestamptz
  last_seen_external_id  text            -- highest external_id ingested so far
  active                 boolean NOT NULL DEFAULT true
  created_at             timestamptz NOT NULL DEFAULT now()
  UNIQUE (user_id, feed_url)
```

**Indexes:**
- `jobs (user_id, created_at DESC)` — list recent jobs.
- `jobs (status) WHERE status IN ('queued','fetching','transcribing','summarizing','embedding')` — worker pickup.
- `summaries (user_id, created_at DESC)` — library list.
- GIN index on `summaries.tsv` (a `GENERATED ALWAYS AS (to_tsvector('english', content_text)) STORED` column, where `content_text` is a sibling generated text column that flattens `tldr`, `key_points` joined by newline, and `quotes` text).
- GIN index on `transcripts.text` via `to_tsvector('english', text)`.
- HNSW index on `summaries.embedding` (`vector_cosine_ops`) for ANN search.
- `subscriptions (active, last_checked_at)` — scheduler pickup.

**Design points:**

- **Episodes scoped per user.** Same video by two users stores twice. Simpler than dedup; revisit if cost matters.
- **Summaries versioned by creation.** Re-summarize inserts a new row; UI shows the latest. History is free.
- **System prompt snapshotted per summary** so changing the prompt later doesn't retroactively misrepresent old summaries.
- **API keys encrypted at rest** using Fernet with a per-deployment `FERNET_KEY`. Returned from API as `{"set": true|false}` only.
- **Structured summary content** as JSONB: `{tldr, key_points[], quotes[{text, speaker}], suggested_tags[]}`. Search indexes the text fields.
- **Embedding vector is nullable.** If Voyage fails, summary still saves; a background task re-embeds later. Full-text search still works.
- **Future clips table** will reference `episodes(id)` + `start_ms` / `end_ms` / `audio_path`. No schema changes needed now.

## 7. Job pipeline

The worker loop runs inside the FastAPI app. Every 2 seconds:
```sql
UPDATE jobs SET status='fetching', started_at=now()
WHERE id = (
  SELECT id FROM jobs WHERE status='queued'
  ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED
) RETURNING *;
```
On app startup, any job in a non-terminal non-queued status is marked `failed` with error `interrupted by restart`.

**Concurrency:** one job at a time per app instance. Trivial to bump to N task loops later.

### YouTube job

1. Parse video id from URL. → 5%
2. Probe captions via `yt-dlp --list-subs --skip-download`.
   - If captions exist, fetch them and normalize to plain text. Skip to step 6 with `source='youtube_captions'`.
3. Fetch metadata first (`yt-dlp --dump-json --skip-download`); if `duration > MAX_DURATION_SECONDS`, fail with "Video exceeds configured max duration". Otherwise download audio: `yt-dlp -f bestaudio --extract-audio --audio-format m4a` to `/data/audio/{episode_id}.m4a`. → 10–40%
4. Persist `episodes` row (or reuse if unique key matches); set `audio_expires_at = now() + 7 days`.
5. Transcribe with ElevenLabs Scribe. Progress estimated by audio duration; update every ~10%. → 40–80%
6. Persist `transcripts` row.
7. Claude summary: single call returns JSON with `tldr`, `key_points`, `quotes`, `suggested_tags`. → 80–95%
8. Voyage embedding of `tldr + key_points` concatenated. → 95–99%
9. Insert `summaries` row + `summary_tags` (source=`llm`). → 100%, status `done`.

### Podcast job

1. Parse Apple Podcast URL: extract podcast `id` and episode id (`?i=` parameter).
2. iTunes lookup: `https://itunes.apple.com/lookup?id={id}` → `feedUrl`.
3. `feedparser(feedUrl)`; find `<item>` whose `<guid>` or `<itunes:episodeGuid>` matches the episode id. If no match, fail with "Episode not found in feed".
4. Read `<itunes:duration>` from the feed item; if greater than `MAX_DURATION_SECONDS`, fail with "Episode exceeds configured max duration". Otherwise download the `<enclosure>` MP3 to `/data/audio/{episode_id}.mp3`. Same as YouTube step 4 from here.
5–9. Same as YouTube job steps 5–9.

### Resummarize job

1. Load existing `transcripts.text` for the episode.
2. Claude summary with the **current** `user_settings.system_prompt`.
3. Voyage embedding.
4. Insert new `summaries` row + tags. (Previous summary rows are preserved.)

### Progress reporting

`update_progress(job_id, pct, message)` writes to the job row and publishes to an in-memory pub/sub (`asyncio.Queue` per subscriber). `/events/{job_id}` SSE endpoint:

1. Sends the current state from DB as the first event (so reconnects aren't out of sync).
2. Subscribes to the pub/sub for that `job_id`.
3. Emits events until the job reaches a terminal status; then sends a final event and closes.

## 8. Subscriptions scheduler

Two scheduler tasks run in the FastAPI app alongside the worker:

**Feed poller** — every 30 minutes per active subscription (not all at once; spread via `last_checked_at`):
1. For `youtube_channel`: feed URL is `https://www.youtube.com/feeds/videos.xml?channel_id=<id>`; parse with `feedparser`.
2. For `podcast_feed`: direct RSS parse.
3. Find items with `external_id > last_seen_external_id` (YouTube `<yt:videoId>`, podcast `<guid>`).
4. For each new item, enqueue a `youtube` or `podcast` job. Update `last_seen_external_id` and `last_checked_at`.

**Retention cleanup** — daily at 03:00 UTC:
1. `DELETE FROM audio files WHERE audio_expires_at < now()` (unlink from disk, null `audio_path`).
2. Delete `jobs` rows older than 30 days.

**Subscription onboarding:**
- User pastes a YouTube channel URL or podcast RSS URL.
- Backend resolves: for YouTube channel URL, extract channel id (handle `@handle`, `/channel/ID`, `/c/name` forms via yt-dlp); build feed URL.
- On first check, set `last_seen_external_id` to the **latest** current episode's id (don't backfill the entire history; user can manually ingest back-catalog items they want).

## 9. API surface

All routes require an authenticated session cookie except `/auth/*` and `/healthz`. All responses JSON. All requests scoped to the session user.

```
POST   /auth/login              Redirects to Google
GET    /auth/callback           Google OAuth callback
POST   /auth/logout             Clears session

GET    /api/me                  { email, display_name, allowed: true }
GET    /api/settings            { system_prompt, anthropic_key: {set}, elevenlabs_key: {set}, voyage_key: {set} }
PATCH  /api/settings            { system_prompt?, anthropic_key?, elevenlabs_key?, voyage_key? }

POST   /api/jobs                { source_url }  →  { job_id }   (kind auto-detected)
POST   /api/jobs/resummarize    { episode_id }  →  { job_id }
GET    /api/jobs                [{ id, kind, status, progress_pct, progress_message, created_at, ... }]
GET    /api/jobs/{id}           { ... }
GET    /events/{job_id}         SSE stream

GET    /api/summaries           ?limit&cursor&tag=  →  [{ id, episode: {...}, content: {...}, tags: [...], created_at }]
GET    /api/summaries/{id}      Full summary + transcript reference
DELETE /api/summaries/{id}      Hard-delete summary row; transcript retained so re-summarize still works
GET    /api/episodes/{id}/transcript  { text, segments }

POST   /api/summaries/{id}/tags       { add?: [names], remove?: [names] }
GET    /api/tags                      [{ name, count }]

GET    /api/search              ?q&tag=  →  [{ summary_id, score, matched_fields: [...], episode: {...} }]
                                            # Hybrid: full-text rank + vector cosine similarity merged via
                                            # Reciprocal Rank Fusion (k=60). Results capped at 50.

GET    /api/subscriptions       [{ id, kind, feed_url, title, last_checked_at, active }]
POST   /api/subscriptions       { url }  (server resolves kind + feed_url)
DELETE /api/subscriptions/{id}
PATCH  /api/subscriptions/{id}  { active }

GET    /healthz                 { db: "ok" }
```

## 10. Frontend

**Stack:** React + TypeScript + Vite + TanStack Query + Tailwind + shadcn/ui + `react-router`.

**Screens:**

```
/login           Google sign-in button.
/                Home: URL paste + "Process" button, active jobs with live progress,
                 recent summaries grid.
/summary/:id     Structured view (TL;DR / Key Points / Quotes / Tags / Transcript collapsible),
                 re-summarize button, delete.
/search          Hybrid search box, tag filter pills, result cards with relevance score.
/subscriptions   List of followed channels/feeds, add via URL, toggle active, remove.
/settings        Editable system prompt, API key fields (write-only — display "•••• set"),
                 view-only allowlist.
```

**State:**
- TanStack Query for all server state.
- `useJobProgress(jobId)` hook subscribes to SSE and feeds updates into the query cache.
- No Redux/Zustand.

**Auth UX:** httpOnly session cookie. Frontend checks `/api/me`; 401 → redirect to `/login`. If user authenticates but isn't allowlisted, backend renders a 403 HTML page rather than redirecting (the user never gets a session).

**Summary rendering:** summary JSON is rendered into semantic sections. Tags are editable chips (add/remove via `/api/summaries/:id/tags`). LLM-source tags are visually distinguishable (subtle icon or tone).

**Responsive:** mobile-first via Tailwind defaults; no separate mobile build.

## 11. Auth & secrets

**OAuth:** `authlib` against Google, scope `openid email profile`, fixed redirect URI configured in Google Console. On callback, email is compared to `ALLOWED_EMAILS` (comma-separated env var). Non-allowlisted emails get a 403 page; no user row is created.

**Session:** Starlette `SessionMiddleware` with `SESSION_SECRET_KEY`. Cookie: httpOnly, Secure, SameSite=Lax, 30-day rolling expiry. Contains `user_id` only.

**Per-user API keys:** stored in `user_settings` encrypted with Fernet using a per-deployment `FERNET_KEY`. Decrypted in the worker only when needed. Never returned in API responses; never logged.

**Env vars:**
```
DATABASE_URL
SESSION_SECRET_KEY
FERNET_KEY
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
GOOGLE_REDIRECT_URI
ALLOWED_EMAILS                  # comma-separated
APP_BASE_URL                    # for OAuth redirect construction
MAX_DURATION_SECONDS            # default 14400 (4 hours)
AUDIO_STORAGE_PATH              # default /data/audio
```

`.env.example` in repo lists every var with fake values. `.env` is gitignored.

**CSRF:** same-origin + SameSite=Lax cookies; no tokens needed for v1.

## 12. Error handling & observability

**Philosophy:** surface real errors; no silent fallbacks.

| Stage | Failure | Behavior |
|---|---|---|
| URL resolution | Invalid / unsupported host | Reject at API (400) before job creation |
| Captions probe | Network error | Retry once; fall through to audio download |
| yt-dlp download | Geo/private/age-gated | Fail fast with yt-dlp stderr |
| iTunes lookup | 404 | Fail with "Apple Podcast ID not found" |
| RSS parse | GUID mismatch | Fail with "Episode not found in feed" |
| Audio download | Network/5xx | Retry 2× with exponential backoff |
| ElevenLabs | 5xx / network | Retry 2× |
| ElevenLabs | 4xx | Fail immediately, surface error |
| Claude | 5xx / retryable rate-limit | Retry 2× |
| Claude | 4xx | Fail immediately, surface error |
| Voyage | Any | Retry 2×; on persistent failure, save summary without embedding and log warning; background re-embed task retries later |
| Restart during job | Detected on startup | Mark failed, user re-runs |

**Retention:**
- Audio: 7-day TTL, daily cleanup.
- Transcripts, summaries: forever.
- Jobs: 30 days.
- Account deletion: manual SQL for now (single operator).

**Observability:**
- `structlog` JSON to stdout; Railway captures.
- Fields: `user_id`, `job_id`, `stage`, `duration_ms`, `error`.
- Redaction filter strips anything matching an API-key pattern.
- FastAPI middleware logs method/path/status/latency/user_id.
- `/healthz` returns 200 with `{db: "ok"}` after a `SELECT 1`. Railway uses it for restart policy.
- Failed jobs expose their `error` field in the UI.
- No Sentry / APM in v1.

## 13. Cost estimate (per user, 30 episodes/month, 90 min avg)

| Service | Usage | Cost |
|---|---|---|
| ElevenLabs Scribe | 45 hrs audio @ $0.30/hr | ~$13.50/mo |
| Claude Sonnet 4.6 | 30 summaries, ~20k in / 2k out each | ~$2.40/mo |
| Voyage voyage-3 | negligible | <$0.10/mo |
| Railway (app + Postgres) | Hobby + Postgres add-on | ~$10/mo |
| **Total** | | **~$26/mo** |

## 14. Testing

**Philosophy:** test where bugs live. Real Postgres, real pgvector; external services stubbed at the HTTP boundary.

**Integration tests (majority):**
- `testcontainers-python` spins Postgres with pgvector.
- FastAPI `TestClient` for API.
- `respx` mocks external HTTP (ElevenLabs, Claude, Voyage, iTunes, YouTube, RSS).
- Each test wrapped in a transaction, rolled back after.

Example tests:
```
test_create_youtube_job_fetches_captions_first
test_youtube_job_falls_back_to_audio_when_no_captions
test_podcast_job_resolves_feed_and_matches_guid
test_resummarize_uses_current_prompt_and_inserts_new_row
test_hybrid_search_ranks_semantic_above_fulltext_for_fuzzy_query
test_allowlist_rejects_unknown_email
test_job_marked_failed_on_worker_restart
test_audio_ttl_cleanup_deletes_file_and_nulls_path
test_subscription_scheduler_enqueues_only_new_episodes
test_embedding_failure_still_saves_summary
test_api_keys_never_returned_in_settings_response
```

**Unit tests:** URL parsing, Fernet round-trip, hybrid-search score merge, duration parsing.

**Frontend:** `vitest` for URL-type-detection and SSE-reducer hooks. One Playwright e2e: login → paste URL → watch progress → view summary → search.

**CI:** GitHub Actions, `pytest -m "not slow"` on push; full suite on merge to main. Railway auto-deploys on merge after CI passes.

**TDD:** new features start with an integration test against the seam (API endpoint or worker boundary). Enforced via the superpowers test-driven-development skill during implementation.

## 15. Phased delivery

**Phase 1 (MVP, this spec):** everything above.

**Phase 2 (deferred):**
- Morning digest email.
- Audio clips / "best parts" highlight storage and playback.
- Account self-service (delete, export).
- Admin UI for allowlist and subscription overview.

## 16. Open questions / known risks

- **yt-dlp legal/ToS posture.** Downloading YouTube audio is gray-legal. Personal-use self-hosted app mitigates; still, any public distribution of this service would be a concern.
- **Apple Podcast URL format drift.** If Apple changes the `?i=` parameter scheme, episode resolution breaks. Mitigation: wrap the parser in a test with a fixture set; update when breakage is observed.
- **Very long episodes (4+ hours).** Scribe accepts them; Claude context may require chunking. `MAX_DURATION_SECONDS` env var guards the pathological case. If needed, a simple chunk-then-merge summarizer is a later add.
- **ElevenLabs pricing changes** would shift the cost estimate. Spec assumes current public pricing.
- **Railway Postgres pgvector availability.** Must verify the extension is available on the Railway Postgres add-on; fallback is the Railway Docker Compose template for self-hosted Postgres with pgvector.
