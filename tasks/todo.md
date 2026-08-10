# Prompt styles implementation

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
