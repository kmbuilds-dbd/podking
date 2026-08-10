# Prompt styles implementation

- [x] Add prompt-style schema/model and migration backfill.
- [x] Add prompt-style and subscription assignment APIs.
- [x] Snapshot selected prompts when jobs are queued and use them in the worker.
- [x] Update Settings and subscription detail UI.
- [x] Add and run backend/frontend verification.

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
