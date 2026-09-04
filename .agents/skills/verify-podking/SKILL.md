---
name: verify-podking
description: Verify podking's authenticated React audio-transcription surface with a real FastAPI instance, Playwright, and persisted Postgres state.
---

# Verify podking

Use this skill after changing the upload, transcription worker, history, or text-download flow. It drives the built React app through the authenticated browser path and checks the backend boundary with the project's Postgres test database.

## Launch

Run the helper from the repository root:

    .agents/skills/verify-podking/verify.sh

The helper builds frontend/dist, applies Alembic migrations to the configured test database, starts FastAPI on 127.0.0.1:8011 with TEST_MODE=1, and runs the full Playwright suite. Readiness is curl -fsS http://127.0.0.1:8011/healthz returning a successful health response. The server log is saved under verification-artifacts/podking/.

The helper uses AUDIO_STORAGE_PATH under a process-specific temporary directory and podking_test by default. Set TEST_DATABASE_URL when another isolated Postgres test database is required. Do not point this run at production.

## Doctor

With the helper running, confirm the exact process and port it started:

    kill -0 "$(cat /tmp/podking-verify-8011.pid)"
    curl -fsS http://127.0.0.1:8011/healthz

The first command checks the recorded process, not a process-name match. The second checks the running app and database response. If either fails, read verification-artifacts/podking/server.log before driving the browser.

## Drive

The browser harness is Playwright Chromium. Run the mapped transcription feature directly:

    cd frontend
    E2E_BASE_URL=http://127.0.0.1:8011 npx playwright test e2e/transcriptions.spec.ts

The spec uses /test/login?email=allowed@example.com, navigates to /transcriptions, locates the labelled Audio file input, the Description textarea, the Transcribe audio button, and the Generated history heading. It selects a real in-memory unsupported file to prove the UI rejects it before network submission. Backend tests separately drive supported MP3, MP4, and WAV uploads, the queued worker path, ownership checks, and the completed text download.

Stable user-facing selectors are:

- getByRole("link", { name: "Transcriptions" })
- getByRole("heading", { name: /Turn a recording into/i })
- getByLabel("Audio file")
- getByLabel(/Description/)
- getByRole("button", { name: "Transcribe audio" })
- getByRole("heading", { name: "Generated history" })
- getByRole("link", { name: "Download text" })

## Evidence

The helper leaves these proof artifacts in verification-artifacts/podking/:

- run.log contains the launch, doctor, browser actions, and exit codes.
- server.log contains the FastAPI process output.
- Playwright output confirms the accessible upload form and client-side rejection result.
- Backend test output confirms persisted rows, worker completion, MIME propagation, ownership isolation, and attachment body and headers.

An acceptable proof exercises the real authenticated page and the actual multipart API route. It checks the Postgres row and the response body alongside the visible state. The ElevenLabs HTTP call is mocked only at the existing worker/elevenlabs_client.py provider boundary, so no secret or external request is required. A test-only login route is used only to establish the normal session cookie.

## Cleanup

The helper records its exact server PID in /tmp/podking-verify-8011.pid, waits for that process to exit, and removes only its process-specific temporary audio directory and PID file. It never kills by process name. Evidence under verification-artifacts/podking/ survives cleanup.

If a run fails, invoke the helper's cleanup trap by allowing it to exit, inspect the preserved logs, fix the issue, and rerun the helper. Remove stale PID files only after checking the recorded process with kill -0.

## Helpers

The executable helper is .agents/skills/verify-podking/verify.sh. It accepts no arguments:

    .agents/skills/verify-podking/verify.sh

The helper creates the evidence directory, starts one isolated server, runs the browser spec and focused backend tests, records all output, and tears down the PID it started.
