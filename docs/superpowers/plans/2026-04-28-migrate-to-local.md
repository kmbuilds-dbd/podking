# Migrate podking off Railway to a home Windows server

**Goal:** Run podking entirely on a Windows server at home (Docker Desktop + Compose, WSL2 backend), exposed via an existing Cloudflare Tunnel. Drop Railway. Keep ElevenLabs Scribe for STT for now. Keep ElevenReader as the consumer (HTML reader endpoint).

**Why now:** YouTube's bot-check rejects the Railway IP regardless of cookies and Proof-of-Origin tokens. The fix is moving to a residential IP.

**Out of scope (for this migration):**
- Local transcription via faster-whisper. Tracked as a follow-up below; we keep paying ElevenLabs for now and revisit once Phase 1 is stable.
- Adding TTS / audio summaries (would use VibeVoice; separate feature, revisit later).
- Multi-user hosting beyond personal use.
- Migrating any data the user doesn't care about preserving.

---

## Decisions

Locked:

1. **Runtime: Docker Desktop on Windows with the WSL2 backend, orchestrated by `docker compose`.** Reuses the existing `Dockerfile` (app) plus `pgvector/pgvector:pg16` (db) and `cloudflare/cloudflared` (tunnel) as sibling services. No NSSM, no native uv install on the host.
2. **STT: stay on ElevenLabs Scribe.** Local transcription is deferred — see "Follow-up: local Whisper" below.
3. **Database migration: fresh start.** Nothing from Railway's Postgres is preserved — no `pg_dump`/`pg_restore` step. The first sign-in on the new instance creates a fresh user row; subscriptions and summaries get re-added by hand.
4. **Cloudflare hostname: `podking.athinkingpmat.work`.** Drives `APP_BASE_URL` and the OAuth redirect URI.
5. **Audio cache on Windows: `C:\Users\Nvidia_Gaming\Documents\claude\podking\audio`.** Bind-mounted into the `app` container at `/data/audio`. Compose creates the directory on first up if it doesn't exist; the retention scheduler TTLs files after ~7 days.

---

## Phase 1 — infra move, no feature changes

Goal: same app, same pipeline (still using ElevenLabs), running on Windows under Docker Compose, behind the existing Cloudflare Tunnel.

- [ ] Install Docker Desktop with the WSL2 backend. → verify: `docker run --rm hello-world` succeeds from PowerShell.
- [ ] Author `docker-compose.yml` at the repo root with three services:
  - `app` — built from the existing `Dockerfile`, port `8000` published to localhost only, `restart: unless-stopped`, env from `.env`, bind-mount the audio cache host path to `/data/audio`.
  - `db` — `pgvector/pgvector:pg16`, named volume `podking-db`, env `POSTGRES_USER/PASSWORD/DB=podking`. No published port; only `app` connects over the compose network.
  - `cloudflared` — `cloudflare/cloudflared:latest`, command `tunnel --no-autoupdate run --token ${CLOUDFLARE_TUNNEL_TOKEN}`, `restart: unless-stopped`. Tunnel ingress points at `http://app:8000`.
  - → verify: `docker compose config` parses cleanly; `docker compose up -d` brings all three to `running`.
- [ ] Configure the Cloudflare Tunnel route in the dashboard: `https://podking.athinkingpmat.work` → `http://app:8000` (using the named tunnel whose token we set above). → verify: `https://podking.athinkingpmat.work/healthz` returns 200 from off-network (e.g. phone on cell data).
- [ ] Update Google Cloud Console OAuth client: add `https://podking.athinkingpmat.work/auth/callback` to Authorized redirect URIs. Leave the Railway URI in place until cutover is done; remove afterward.
- [ ] Create `.env` at the repo root (consumed by Compose):
  - `DATABASE_URL=postgresql://podking:<pw>@db:5432/podking` (note: hostname `db`, not `localhost`).
  - `APP_BASE_URL=https://podking.athinkingpmat.work`
  - `GOOGLE_REDIRECT_URI=https://podking.athinkingpmat.work/auth/callback`
  - `AUDIO_STORAGE_PATH=/data/audio` (in-container path; host path `C:\Users\Nvidia_Gaming\Documents\claude\podking\audio` is set in the compose bind mount).
  - `SESSION_SECRET_KEY`, `FERNET_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `LISTEN_NOTES_API_KEY` — copied from Railway.
  - `YT_DLP_COOKIES_FILE` or `YT_DLP_COOKIES` — keep for now; cookies on residential IPs help with rate limits even when not strictly required.
  - `CLOUDFLARE_TUNNEL_TOKEN` — from the Cloudflare dashboard; only consumed by the `cloudflared` service.
  - **`YT_DLP_POT_PROVIDER_URL` — leave unset.** No longer needed without a datacenter IP.
- [ ] Migrations run automatically on `app` boot (existing `Dockerfile` CMD does `alembic upgrade head` before uvicorn). → verify: `docker compose logs app` shows the alembic output, then `docker compose exec db psql -U podking -d podking -c '\dt'` lists the expected tables.
- [ ] Sign in via Google through the tunnel. → verify: `/api/me` returns the expected user.
- [ ] Submit the YouTube link that's been failing on Railway. → verify: job reaches `done`, summary visible.
- [ ] Submit a podcast episode. → verify: job reaches `done`.
- [ ] Confirm survival across reboot: stop Docker Desktop / restart the host, ensure `restart: unless-stopped` on `app`, `db`, and `cloudflared` brings everything back without manual steps. Docker Desktop itself needs to be set to "Start on login".
- [ ] Decommission Railway: pause/delete `podking`, `bgutil-ytdlp-pot-provider`, and the Postgres service. Keep the project around for one week as insurance, then delete.

**Phase 1 success criteria:** Two end-to-end jobs (one YouTube, one podcast) succeed on the home server, exposed via Cloudflare Tunnel. ElevenReader can fetch a `/reader/<token>/<id>.html` URL and read the summary. Railway services are paused. Stack survives a host reboot without intervention.

---

## Phase 2 — Railway/POT cleanup

Things that exist only because Railway was the deploy target. Pure code change, no infra impact.

- [ ] Delete `railway.toml`.
- [ ] Remove the `bgutil-ytdlp-pot-provider` dep from `pyproject.toml` and the POT branch in `worker/youtube.py::_auth_args`. Drop the `yt_dlp_pot_provider_url` setting from `config.py`.
- [ ] Strip POT- and Railway-specific notes from `.env.example`.
- [ ] Trim the `Dockerfile`: it stays (Compose builds from it), but the comments referencing Railway's ephemeral filesystem and `${PORT:-8000}` fallback can go — Compose pins the port, and the named volume / bind mount handles persistence.
- [ ] README: rewrite the "Deployment (Railway)" section. Replace with "Deployment (home server)": Docker Desktop + Compose + Cloudflare Tunnel, link to this plan.

**Phase 2 success criteria:** `grep -r 'railway\|bgutil\|pot_provider' backend/ frontend/ docs/ .env.example` returns only legitimate references (e.g. README history, CHANGELOG, this plan doc itself).

---

## Follow-up: local Whisper (deferred)

We keep paying ElevenLabs for now. Once Phase 1 is stable and we have answers for GPU model + VRAM, revisit this. Sketch — left here so we don't re-derive it later:

- Add `faster-whisper>=1.1` to `pyproject.toml`. CTranslate2 wheel handles CPU/GPU.
- New `backend/podking/worker/whisper_client.py` with a module-level lazy `WhisperModel`, public `async def transcribe(audio_path: Path) -> dict[str, object]` matching `elevenlabs_client.transcribe`'s shape, model call wrapped in `asyncio.to_thread`.
- Settings on `config.py`: `whisper_model_size` (default `medium`), `whisper_device` (default `cuda` once we know the GPU works), `whisper_compute_type`.
- In `runner.py`, swap the three `from podking.worker.elevenlabs_client import transcribe` imports (currently around `runner.py:287`, `:371`, `:426`) for `whisper_client`. Remove the three `_require_key(settings.elevenlabs_api_key_encrypted, "ElevenLabs")` calls.
- Settings UI: hide the ElevenLabs API key field (frontend only — backend column stays until we confirm nothing else reads it).
- Container side: switch `app` to a CUDA base image (`nvidia/cuda:12.4.0-cudnn-runtime-ubuntu22.04`), enable GPU passthrough in compose with `deploy.resources.reservations.devices` (Compose v3.8+) or top-level `gpus: all`. Requires NVIDIA Container Toolkit installed inside Docker Desktop's WSL2 distro.
- Reference STT-model tradeoffs:
  - `small` (~1 GB VRAM, 2 GB RAM): fast, weaker on multilingual.
  - `medium` (~2 GB VRAM, 5 GB RAM): the sweet spot for podcasts.
  - `large-v3` (~5 GB VRAM, 10 GB RAM): best quality, GPU recommended.
  CPU-only fallback: ~0.3–0.5× realtime for `medium`. Modern NVIDIA GPU: ~5–10× realtime.

Success criteria when we do this: same two test jobs from Phase 1 complete with `ELEVENLABS_API_KEY` unset; transcript quality spot-checks comparable on a 30-min episode.

---

## Risk / fallback notes

- **Docker Desktop autostart:** Compose's `restart: unless-stopped` only fires once the Docker daemon is up. Set Docker Desktop to "Start on login" (Settings → General) or the stack stays down until someone logs into the Windows box.
- **Cloudflare Tunnel cold-start:** first request after the Windows box wakes can be slow. The `cloudflared` container reconnects on its own; just accept the first-request delay.
- **Google OAuth on a tunneled hostname:** OAuth requires HTTPS, which Cloudflare Tunnel provides. If using Cloudflare Access in front of the tunnel, the OAuth flow needs to be exempted from Access challenges (it can't replay a third-party login behind a first-party gate).
- **Audio cache bind mount:** the host path needs to be a directory Docker Desktop has permission to share (Settings → Resources → File sharing on older versions; the WSL2 backend exposes the whole drive). If the mount silently fails, downloads succeed but the retention scheduler won't find files later.
- **Power / network outages at home:** unlike Railway, home reliability is on you. Compose `restart: unless-stopped` handles container crashes; UPS handles brief power blips; the tunnel reconnects on its own. Prolonged outages just mean podking is unreachable until home is back.
- **Local Whisper deferral:** while we keep ElevenLabs in the loop, `ELEVENLABS_API_KEY` outages or quota issues take the pipeline down. Acceptable for a personal app; revisit if it becomes a problem.
