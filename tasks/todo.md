# Prompt styles implementation

## Audio transcription feature

- [x] Read the Poteto Mode Principles section in full.
- [x] Inspect the current app, update local `main` from `origin/main`, and establish a clean baseline without overwriting the user's summaries edit.
- [x] Complete the required `how` and `architect` design passes for the transcription flow.
- [x] Throughput checkpoint: run blocking checks before fan-out.
- [x] Throughput checkpoint: identify independent workstreams across backend, frontend, and verification assets.
- [x] Throughput checkpoint: isolate shared mutable state before parallel work.
- [x] Throughput checkpoint: choose the smallest safe decomposition and record why.
- [x] Implement upload, ElevenLabs transcription, persisted history, descriptions, and text downloads.
- [x] Build the project-local verification skill and feature map.
- [x] Run backend, frontend, and real browser verification against the finished app.
- [x] Review the diff, commit the feature, and merge the verified changes to `main`.

### Feature review

- `98 passed, 1 warning` in the full Postgres-backed backend suite.
- The project-local verification helper passed the full nine-test Playwright suite and nine focused transcription tests. It preserved `verification-artifacts/podking/run.log` and `server.log` after cleanup.
- Frontend production build passed. Frontend lint retains the three pre-existing errors in `GenerateAudioButton.tsx`, `button.tsx`, and `Settings.tsx`. Changed frontend files add no lint errors.
- Changed Python files are Ruff-clean. Repository-wide Ruff retains the eleven pre-existing findings recorded in `tasks/lessons.md`.
- Independent comment review found no actionable comment or suppression findings. The configured independent Comment Sicko profile was unavailable, so the generic read-only review was the fallback.
- Integration: commit `905e144` is pushed to `origin/main`.

### Transcription design decision

- Candidate A uses a new `transcriptions` row plus a `Job(kind="transcription")` row. The worker stores an upload under the configured audio directory, calls the existing ElevenLabs Scribe client, and writes the transcript back to the transcription row.
- Candidate B uses separate request and result tables plus a second worker. It was rejected because the extra persistence and worker lifecycle add no user-visible value for this first release.
- Chosen shape: a dedicated `Transcription` aggregate keyed to the user. Upload metadata and transcript result live there. The backing `Job.status` is the single lifecycle authority for `queued`, `transcribing`, `done`, and `failed`.
- API boundary: `POST /api/transcriptions` accepts multipart audio and a description, `GET /api/transcriptions` lists the authenticated user's history, and `GET /api/transcriptions/{id}/download` returns `text/plain` with a safe `.txt` filename.
- Frontend state: the new `/transcriptions` route owns selected file, description, submission state, and history query. Completed rows expose transcript preview and a native download link.
- Shared writes are serialized through the existing single worker and per-row database updates. Upload files use user-scoped names derived from UUIDs, so concurrent users never share a path.

- [x] Add prompt-style schema/model and migration backfill.
- [x] Add prompt-style and subscription assignment APIs.
- [x] Snapshot selected prompts when jobs are queued and use them in the worker.
- [x] Update Settings and subscription detail UI.
- [x] Add and run backend/frontend verification.
- [x] Prevent subscription episode queueing while prompt-style assignment is saving.
- [x] Verify prompt-style regression coverage after the queueing-flow fix.

## Review

- Baseline backend: `75 passed`.
- Baseline frontend build: passed.
- Baseline frontend lint: 3 pre-existing errors in `GenerateAudioButton.tsx`, `button.tsx`, and `Settings.tsx`.

## Final review

- Backend suite: `80 passed`, 1 existing Authlib deprecation warning.
- Changed backend/test files: Ruff clean.
- Frontend production build: passed.
- Frontend lint: same 3 pre-existing errors; no new lint findings from the feature.
- `AGENTS.md` remains untracked and untouched.

## Prompt-style queueing follow-up

- Reported issue: a podcast job could be queued while the subscription prompt-style PATCH was still in flight.
- Fix: disable episode queue actions during assignment and update the cached subscription from the PATCH response.
- Verification: full backend suite `80 passed, 1 warning`; frontend production build passed.

## Re-summarize prompt follow-up

- [x] Reproduce the re-summarize path falling back to `general`.
- [x] Preserve the source summary's prompt when queuing re-summarization.
- [x] Run full verification before integrating the fix to `origin/main`.

- Red/green regression: expected custom guidance, initially received `Summarize this.`, then passed after the fix.
- Verification: `81 passed, 1 warning`; Ruff and diff checks passed.

## Railway migration healthcheck incident

- [x] Inspect the latest failed deployment and migration state.
- [x] Trace the migration lock to long-lived SSE database transactions.
- [x] Add a regression test proving the SSE route releases its transaction.
- [x] Run focused and full verification.
- [ ] Push the root-cause fix to `origin/main` and verify Railway health.

### Review

- Deployment `09aac3ac-96c6-4b31-ba81-f76d8cd8a145` blocked while running migration `0010`.
- Production showed `/events/{job_id}` sessions idle in transaction and blocking `ALTER TABLE` locks.
- The route now snapshots the initial event and rolls back before opening the long-lived stream.
- Verification: regression test passed; full backend suite `83 passed, 1 warning`; changed Python files are Ruff-clean.
- Repository-wide Ruff still reports 11 unrelated, pre-existing findings in audio worker tests/files.
