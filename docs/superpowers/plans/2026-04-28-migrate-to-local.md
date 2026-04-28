# Migrate podking off Railway to a home Windows server

**Goal:** Run podking entirely on a Windows server at home, exposed via an existing Cloudflare Tunnel. Drop Railway. Replace ElevenLabs Scribe (cloud STT) with a local Whisper variant. Keep ElevenReader as the consumer (HTML reader endpoint).

**Why now:** YouTube's bot-check rejects the Railway IP regardless of cookies and Proof-of-Origin tokens. The fix is moving to a residential IP. While we're at it, the cloud STT API becomes unnecessary expense once we have the hardware locally.

**Out of scope:**
- Adding TTS / audio summaries (would use VibeVoice; separate feature, revisit later).
- Multi-user hosting beyond personal use.
- Migrating any data the user doesn't care about preserving.

---

## Decisions to lock before starting

These shape Phase 1. Capture answers in a follow-up commit to this file before kicking off work.

1. **Server hardware:** CPU model, RAM, GPU model + VRAM. Determines feasible Whisper model size and whether we need the CUDA build of CTranslate2.
2. **Runtime:** Docker Desktop on Windows (reuse existing Dockerfile mostly as-is) **or** native Python via `uv` running as a Windows Service (lighter, no Docker license). Default: **native via NSSM** unless GPU passthrough is easier in Docker.
3. **Database migration:** is anything in Railway's Postgres worth keeping (subscriptions, summaries, user settings)? If yes, add a `pg_dump` / `pg_restore` step. If no, fresh DB.
4. **Cloudflare hostname:** the public DNS name podking will live at, e.g. `podking.example.com`. Needed for OAuth and `APP_BASE_URL`.
5. **STT model:** default **faster-whisper, `medium`**. Tradeoffs:
   - `small` (~1 GB VRAM, 2 GB RAM): fast, weaker on multilingual.
   - `medium` (~2 GB VRAM, 5 GB RAM): the sweet spot for podcasts.
   - `large-v3` (~5 GB VRAM, 10 GB RAM): best quality, GPU recommended.
   On CPU only, expect ~0.3–0.5× realtime for `medium`. On a modern NVIDIA GPU, ~5–10× realtime.

---

## Phase 1 — infra move, no feature changes

Goal: same app, same pipeline (still using ElevenLabs), running at home behind the tunnel.

- [ ] Install Postgres 16 on Windows. Create `podking` DB + user.
- [ ] (If keeping data) `pg_dump --no-owner` from Railway → `pg_restore` locally. Verify row counts match for `users`, `subscriptions`, `episodes`, `summaries`.
- [ ] Install `cloudflared` on the Windows server. Add a tunnel route `https://<hostname> → http://localhost:8000`.
- [ ] Update Google Cloud Console OAuth client: add `https://<hostname>/auth/callback` to Authorized redirect URIs. Leave the Railway URI in place until cutover is done; remove afterward.
- [ ] Create `.env` on the server:
  - `DATABASE_URL=postgresql://podking:<pw>@localhost:5432/podking`
  - `APP_BASE_URL=https://<hostname>`
  - `GOOGLE_REDIRECT_URI=https://<hostname>/auth/callback`
  - `AUDIO_STORAGE_PATH=C:\podking\audio` (path Windows can write to)
  - `SESSION_SECRET_KEY`, `FERNET_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `LISTEN_NOTES_API_KEY` — copied from Railway.
  - `YT_DLP_COOKIES_FILE` or `YT_DLP_COOKIES` — keep for now; cookies on residential IPs help with rate limits even when not strictly required.
  - **`YT_DLP_POT_PROVIDER_URL` — leave unset.** No longer needed without a datacenter IP.
- [ ] Boot the app: `uv run alembic upgrade head && uv run uvicorn podking.main:app --port 8000`. Confirm it starts cleanly. → verify: `curl https://<hostname>/healthz` returns 200.
- [ ] Sign in via Google through the tunnel. → verify: `/api/me` returns the expected user.
- [ ] Submit the YouTube link that's been failing on Railway. → verify: job reaches `done`, summary visible.
- [ ] Submit a podcast episode. → verify: job reaches `done`.
- [ ] Wrap the Python process so it survives reboots. Options:
  - **NSSM** (Non-Sucking Service Manager) wrapping `uv run uvicorn ...` as a Windows Service. Recommended for native runtime.
  - **Docker Desktop** with `restart: unless-stopped` if running containerized.
- [ ] Decommission Railway: pause/delete `podking`, `bgutil-ytdlp-pot-provider`, and the Postgres service. Keep the project around for one week as insurance, then delete.

**Phase 1 success criteria:** Two end-to-end jobs (one YouTube, one podcast) succeed on the home server, exposed via Cloudflare Tunnel. ElevenReader can fetch a `/reader/<token>/<id>.html` URL and read the summary. Railway services are paused.

---

## Phase 2 — drop ElevenLabs, switch to faster-whisper

Pure code change, no infra impact.

- [ ] Add `faster-whisper>=1.1` to `pyproject.toml`. CTranslate2 wheel handles CPU/GPU.
- [ ] New file `backend/podking/worker/whisper_client.py`:
  - Module-level singleton `WhisperModel` loaded lazily on first call.
  - Public `async def transcribe(audio_path: Path) -> dict[str, object]` returning `{"text": str, "segments": list | None}` — same shape as `elevenlabs_client.transcribe`.
  - Run the model in a thread with `asyncio.to_thread` so the event loop isn't blocked.
- [ ] Auto-detect device: `cuda` if `torch.cuda.is_available()` returns true, else `cpu` with `compute_type="int8"`.
- [ ] Add settings to `config.py`:
  - `whisper_model_size: str = "medium"`
  - `whisper_device: str = "auto"`
  - `whisper_compute_type: str = "auto"`
- [ ] In `runner.py`, replace the three `from podking.worker.elevenlabs_client import transcribe` imports with `from podking.worker.whisper_client import transcribe`.
- [ ] Remove the three `_require_key(settings.elevenlabs_api_key_encrypted, "ElevenLabs")` calls.
- [ ] Settings UI: hide the ElevenLabs API key field (front-end only — backend column stays for now to avoid a migration).
- [ ] Delete `backend/podking/worker/elevenlabs_client.py` once nothing imports it.
- [ ] Update `tests/` for any direct `elevenlabs_client` references.

**Phase 2 success criteria:** Same two test jobs from Phase 1 complete with `ELEVENLABS_API_KEY` unset and the user's saved key blanked out. Transcript content quality is comparable (spot-check a 30-min episode).

---

## Phase 3 — cleanup

Things that exist only because Railway was the deploy target.

- [ ] Delete `railway.toml`.
- [ ] Remove the `bgutil-ytdlp-pot-provider` dep from `pyproject.toml` and the POT branch in `worker/youtube.py::_auth_args`. Drop the `yt_dlp_pot_provider_url` setting.
- [ ] Strip POT- and Railway-specific notes from `.env.example`.
- [ ] Trim Dockerfile if keeping it: drop the `/data/audio` mkdir + Railway-flavored CMD. (Keep the Dockerfile if Docker Desktop is the chosen runtime; otherwise it's optional.)
- [ ] README: rewrite the "Deployment" section. Cloudflare Tunnel + NSSM (or Docker Desktop) replaces Railway.
- [ ] Drop `elevenlabs_api_key_encrypted` column with an Alembic migration **only if** no other code path references it.

**Phase 3 success criteria:** `grep -r 'railway\|elevenlabs\|bgutil\|pot_provider' backend/ frontend/ docs/ .env.example` returns only legitimate references (e.g. README history, CHANGELOG).

---

## Risk / fallback notes

- **CUDA wheels on Windows:** `faster-whisper` via CTranslate2 supports Windows + CUDA, but driver/toolkit version mismatches are common. If GPU setup is painful, ship Phase 2 on CPU first; GPU acceleration is a follow-up.
- **Cloudflare Tunnel cold-start:** first request after the Windows box wakes can be slow. Consider a `cloudflared` keep-alive or just accept the first-request delay.
- **Google OAuth on a tunneled hostname:** OAuth requires HTTPS, which Cloudflare Tunnel provides. If using Cloudflare Access in front of the tunnel, the OAuth flow needs to be exempted from Access challenges (it can't replay a third-party login behind a first-party gate).
- **Power / network outages at home:** unlike Railway, home reliability is on you. NSSM auto-restart handles process crashes; UPS handles brief power blips; tunnel reconnects on its own. Prolonged outages will simply mean podking is unreachable until home is back.
