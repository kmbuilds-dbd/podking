# Podking — Two-host TTS audio + personal podcast feed

Date: 2026-05-15
Status: Design approved; pending implementation plan

## Goal

Give podking the two features from the local `personalized-podcast` skill that
fit a self-hosted summarizer:

1. **Two-host TTS generation.** Turn an existing summary into a NotebookLM-style
   conversation between two AI hosts (~5–10 min MP3), on demand, per summary.
2. **Personal podcast feed.** Publish each generated episode to a per-user RSS
   feed reachable from Apple Podcasts, Spotify, Overcast, etc.

The implementation borrows the skill's recipes (script prompt, TTS+ffmpeg
stitching, iTunes RSS template) but wires them into podking's existing job
pipeline, per-user encrypted API keys, and feed-token URL pattern. Hosting
goes through GitHub Pages so the feed stays reachable even when the home
Windows server (target of the in-progress Railway migration) is offline.

## Non-goals

- Daily/scheduled digest episodes. Per-summary on demand only.
- Per-user GitHub auth. One shared server-owned repo, paths keyed by
  `feed_token`.
- Per-user voice picker UI. Two default voice IDs ship from `.env`; users
  can override theirs with two text inputs in Settings.
- Per-user prompt customization. One built-in script prompt for v1.
- Using the original transcript for richer scripts. Summary content only.
- Listening from podking's own UI before publishing. Audio link == GitHub
  Pages URL. (Existing 🎧 Listen flow stays as-is for reader text.)

## User flow

1. User visits Library, opens a summary card.
2. Card shows a new **Generate audio** button next to the 🎧 / Copy buttons.
3. Click → `POST /api/summaries/{id}/audio` creates a `Job(kind='tts')` and
   returns the job id. UI opens the existing SSE progress stream.
4. Worker runs three stages, surfaced as live progress messages:
   - `scripting` (5–25%): Claude writes a two-host script.
   - `speaking` (25–80%): ElevenLabs synthesizes each segment; pydub
     stitches with 300ms silence + 500ms fade-in / 1s fade-out.
   - `publishing` (80–100%): server clones the shared `podking-audio` repo,
     drops the MP3 under `u/{feed_token}/episodes/`, regenerates the
     user's `feed.xml`, prunes anything past the 30-episode cap, commits,
     pushes.
5. SSE `done` event carries the public MP3 URL. The card's button label
   flips to **Regenerate**.
6. The first time a user generates audio, the UI shows the personal feed
   URL `https://{owner}.github.io/podking-audio/u/{feed_token}/feed.xml`
   plus the existing skill's "How to subscribe in app X" table.

A subsequent **Regenerate** click soft-archives the prior `audio_episodes`
row (drops it from the feed and unlinks the MP3 in the next publish
commit) and queues a fresh job.

## Architecture

### Data model

**New table `audio_episodes`:**

```
id              uuid pk
user_id         uuid fk users on delete cascade
summary_id      uuid fk summaries on delete cascade
job_id          uuid fk jobs on delete set null
title           text not null            -- "{episode.title} — podking"
description     text not null            -- summary.tldr snapshot
script          jsonb not null           -- [{speaker:'A'|'B', text:str}, ...]
mp3_filename    text not null            -- "{id}.mp3"
mp3_path        text not null            -- absolute path under AUDIO_STORAGE_PATH
duration_sec    int not null
size_bytes      bigint not null
voice_a_id      text not null            -- snapshotted at generation time
voice_b_id      text not null
published_url   text                     -- null until publish succeeds
archived_at     timestamptz              -- set when retention prunes
created_at      timestamptz not null default now()
```

Unique partial index: `(user_id, summary_id) where archived_at is null`.
One live audio per summary; regenerate replaces it.

**Changes to existing tables:**

- `Job.kind` check constraint: add `'tts'`.
- `Job.status` check constraint: add `'scripting'`, `'speaking'`,
  `'publishing'`.
- `Job`: new nullable column `summary_id uuid fk summaries on delete set
  null` — TTS jobs reference the summary, not just the episode.
- `UserSettings`: add `tts_voice_a_id text`, `tts_voice_b_id text`, both
  nullable. NULL falls back to `ELEVENLABS_TTS_DEFAULT_VOICE_*` from env.

### File layout

```
backend/podking/
  worker/
    tts/
      __init__.py
      prompt.md             # vendored, lightly edited from skill PROMPT.md
      scripter.py           # write_script(summary, anthropic_key) -> Segments
      speaker.py            # synthesize(segments, voices, eleven_key) -> Path
      publisher.py          # publish(audio_episode, feed_token) -> url
      feed_template.xml     # vendored from skill
    runner.py               # +_run_tts_job; kind switch picks it up
  api/
    summaries.py            # +POST /api/summaries/{id}/audio
    audio.py                # new: GET /api/audio_episodes
  models.py                 # +AudioEpisode, Job.summary_id, UserSettings.tts_voice_*
  schemas.py                # +AudioEpisodeOut, +TtsJobOut

alembic/versions/0007_tts_audio_episodes.py

frontend/src/
  pages/Library.tsx         # +GenerateAudioButton per card
  pages/Settings.tsx        # +voice override inputs
  components/GenerateAudioButton.tsx
  api.ts                    # +generateAudio(summaryId), +listAudioEpisodes()
```

### Worker stages (in `_run_tts_job`)

1. **scripting**
   - Load `Summary` (with episode for title/author).
   - Render `prompt.md` with the summary content (tldr, key_points, quotes).
   - Call Claude via `worker/claude_client.py` using the user's decrypted
     Anthropic key.
   - Validate response is a JSON array of
     `{"speaker": "A"|"B", "text": str}` using a pydantic schema.
   - On invalid JSON: retry once with stricter "JSON only" reminder.
     Second failure → fail job, store raw response in `error`.
   - Persist segments to `audio_episodes.script`.

2. **speaking**
   - Resolve voice IDs: `UserSettings.tts_voice_*` or env defaults.
   - For each segment, POST to ElevenLabs TTS
     (`https://api.elevenlabs.io/v1/text-to-speech/{voice_id}`) with the
     model id `eleven_turbo_v2_5` and the standard voice_settings
     (stability 0.5, similarity_boost 0.75).
   - On 401: fail job with "ElevenLabs key invalid".
   - On 404/voice_not_found: fail job with "Voice ID not found".
   - On 429/quota: stop, fail job with
     "Generated N of M segments — ElevenLabs quota exhausted".
   - On other 5xx: 3-attempt exponential backoff (existing pattern in
     `worker/elevenlabs_client.py`).
   - Stitch chunks with `pydub`: 300ms silence between segments, 500ms
     fade-in, 1000ms fade-out. Export 128k mp3 to
     `{AUDIO_STORAGE_PATH}/audio/{audio_episode_id}.mp3`.
   - Capture duration_sec and size_bytes; insert `audio_episodes` row.

3. **publishing** (wrapped in a process-level `asyncio.Lock`)
   - Shallow-clone `GITHUB_AUDIO_REPO` (via `gh repo clone … -- --depth 1`).
   - Copy the new MP3 to `u/{feed_token}/episodes/{audio_episode_id}.mp3`.
   - Reconcile the working tree against the DB for this user:
     1. Load all `audio_episodes` rows for this user (including the just-
        archived one a regenerate produces, plus any soft-deleted via
        the API). Anything with `archived_at is not null` → unlink its
        MP3 from `u/{feed_token}/episodes/` if present.
     2. Of the remaining live rows ordered by `created_at desc`, mark
        anything past row 30 as `archived_at = now()` and unlink its
        MP3 too.
   - Render `feed_template.xml` with the ≤30 kept episodes and write
     `u/{feed_token}/feed.xml`. Parse output with
     `xml.etree.ElementTree.fromstring` — bail if malformed.
   - `git add .`, commit (`"Audio: {title}"`), push.
   - On non-fast-forward (HTTP 422): pull --rebase, retry push up to 3
     times.
   - On success: update `audio_episodes.published_url` and complete the job.

### Auth and security

- **GitHub PAT**: one fine-grained PAT in env (`GITHUB_PAT`), scoped to
  the single `podking-audio` repo with `Contents: read/write` and
  `Pages: write`. Never stored in the DB. Never returned from any API.
- **Per-user privacy**: each user's path is keyed by their existing
  `feed_token`. The repo is public (Apple Podcasts requires anonymous
  fetch), but paths are not enumerable because tokens are random 32-byte
  URL-safe strings — same threat model the existing
  `/reader/{token}/{id}.html` already accepts.
- **Token rotation**: when a user rotates `feed_token` (existing
  Settings action), the next publish moves their episodes to the new
  path and deletes the old folder in the same commit. Subscribers must
  re-subscribe; the rotation banner in Settings already warns about
  this.
- **Per-user API keys**: Anthropic and ElevenLabs both come from
  `UserSettings.*_api_key_encrypted` (same Fernet-encrypted pattern as
  today). No new key types.

### Env additions

```
# TTS defaults (used when UserSettings.tts_voice_* is null)
ELEVENLABS_TTS_DEFAULT_VOICE_A=21m00Tcm4TlvDq8ikWAM
ELEVENLABS_TTS_DEFAULT_VOICE_B=AZnzlk1XvdvUeBnXmlld
ELEVENLABS_TTS_MODEL_ID=eleven_turbo_v2_5

# Personal podcast feed (GitHub Pages)
GITHUB_PAT=
GITHUB_AUDIO_REPO=user/podking-audio
GITHUB_AUDIO_BASE_URL=https://user.github.io/podking-audio
PODKING_FEED_OWNER_EMAIL=
```

ffmpeg is already a deployment dependency (yt-dlp uses it). `gh` CLI must
be installed on the server — same precondition the skill assumes.

### Dependencies added to `pyproject.toml`

- `pydub` — audio stitching and fades.
- `Jinja2` — feed template rendering. Already pulled in transitively via
  FastAPI/Starlette; pin explicitly to make the dependency intent
  obvious.

No new GitHub-API library: shell out to `git` and `gh`, matching the
skill's approach.

### API surface

`POST /api/summaries/{id}/audio` → queues a TTS job.
- Returns `409 Conflict` with the existing `audio_episode` if one exists
  for this summary and the request omits `?regenerate=true`.
- Returns `201 { job_id, audio_episode_id }` otherwise.

`GET /api/audio_episodes` → list of `AudioEpisodeOut` for the current
user, joined with summary + episode for display.

`GET /api/audio_episodes/{id}` → single row.

`DELETE /api/audio_episodes/{id}` → soft-archive (sets `archived_at`).
The next publish trigger (regenerate of *any* summary) cleans up the
working tree. This is a v2 concern; v1 just keeps it on disk if the
user soft-deletes.

The existing `DELETE /api/jobs/{id}` cancellation already works; the TTS
job honors cancel between segments (i.e. before each ElevenLabs call).

### Frontend

- **`GenerateAudioButton`** on each summary card. States:
  - "Generate audio" (no `audio_episode` exists)
  - "Generating… {progress_message}" (job in-flight, hooked to SSE)
  - "▶ Listen / Regenerate" (audio published) — the ▶ link points at
    `audio_episode.published_url` (a GitHub Pages MP3 URL) and opens in
    a new tab. podking itself does not stream audio; the link goes
    straight to GitHub Pages.
  - "Failed — retry" (job.status === 'failed', with hover tooltip
    showing `job.error`)
- **First-publish modal** (only first time a user successfully publishes)
  showing the feed URL + the subscribe table from the skill's SKILL.md.
- **Settings page** gains optional `tts_voice_a_id` / `tts_voice_b_id`
  text inputs, with a small "Browse voices →
  https://elevenlabs.io/app/voice-library" link. Empty means "use
  server defaults".

## Failure modes and edge cases

| Failure | Behavior |
| --- | --- |
| Anthropic returns invalid JSON | One stricter retry; then job fails with raw response in `error` |
| ElevenLabs 401 | Fail job with key-invalid message |
| ElevenLabs 404 / voice_not_found | Fail job, hint to update voice IDs |
| ElevenLabs 429 / quota | Stop, fail job: "Generated N of M segments" |
| ffmpeg missing | Fail job with brew/apt install hint |
| Malformed feed.xml | Bail before commit; job fails. Live feed untouched |
| git push non-fast-forward | `pull --rebase` + retry up to 3 times |
| User rotates feed_token mid-flight | Acceptable: next publish writes to new path; old path cleaned up same commit |
| User deletes a summary | `audio_episodes` row cascades; weekly `scheduler.py` orphan-prune removes stale MP3s from repo |
| Concurrent regenerate clicks | `asyncio.Lock` on publish; jobs run sequentially anyway |
| Long summaries → long scripts | Script is bounded by the prompt (target ~1500 words). Cost ≈ 7500 chars TTS. Surfaced in SSE message at start of speaking stage |
| Home server offline | Already-published episodes keep working in subscribers' apps (GitHub Pages serves them) |

## Testing strategy

- **scripter.py**: stub Claude client, return canned JSON. Assert parsed
  segments, error path for invalid JSON.
- **speaker.py**: `respx` mocks ElevenLabs to return fixed mp3 bytes per
  voice. Assert output MP3 exists, duration ≈ sum(chunks) + silences ±
  fade allowance.
- **publisher.py**: local bare git repo as remote
  (`GITHUB_AUDIO_REPO=file:///tmp/bare.git`). Run publish, then
  `git clone` the bare repo and assert tree contains the MP3 and a
  parseable `feed.xml` with the right item. Also test retention prune
  with 31 pre-existing episodes.
- **`_run_tts_job`**: integration test with all three external surfaces
  stubbed; assert Job status transitions `queued → scripting → speaking
  → publishing → done` and `audio_episodes` row lands with the right
  fields.
- **API**: pytest TestClient hits `POST /api/summaries/{id}/audio`,
  asserts 201 + job_id, then 409 on second call without `?regenerate`,
  then 201 with `?regenerate=true`.
- **Frontend (Playwright)**: existing test harness; click Generate
  audio, fake the SSE progression, assert button flips to "Regenerate"
  and the published URL renders.

## Migration / rollout

1. Ship behind no flag; the new button just doesn't appear until the
   user provides an ElevenLabs key + the server has `GITHUB_PAT` set.
2. Empty-state behavior: if `GITHUB_PAT` is unset, the API returns
   `503 Service Unavailable` with a clear admin-side message; the
   frontend hides the button accordingly via a small bit on `GET
   /api/me` (`{ audio_enabled: bool }`).

## Open questions (intentionally deferred)

- Per-user prompt customization → revisit if v1 feels too rigid.
- Daily digest mode → revisit after v1 is in use.
- Spotify submission → covered by the skill's existing "warn about
  public discoverability" copy; we can paste it into the
  first-publish modal verbatim when adding Spotify-specific support.
- Token rotation old-folder cleanup → v1 leaves it for the next
  publish; v2 can do it eagerly on rotation.

## References

- Skill source: `~/.claude/skills/personalized-podcast/` —
  `SKILL.md`, `PROMPT.md`, `scripts/speak.py`, `scripts/publish.py`,
  `templates/feed_template.xml`.
- Existing podking design: `docs/superpowers/specs/2026-04-22-podking-design.md`.
