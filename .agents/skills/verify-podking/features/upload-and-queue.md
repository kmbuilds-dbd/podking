# Upload and queue

## Sub-features

- Choose an MP3, MP4, or WAV file.
- Add an optional description.
- Submit multipart form data.
- Persist one user-owned transcription record and queued worker job.

## How to get to it (user POV)

Open the Transcriptions tab in the top navigation. Choose Audio file, enter text in Description, and select Transcribe audio.

## Driving it with Playwright

Use page.getByLabel("Audio file").setInputFiles(...) with a supported fixture and fill page.getByLabel(/Description/). Submit with page.getByRole("button", { name: "Transcribe audio" }). Assert the API response has status queued and that GET /api/transcriptions returns the same filename and description.

## Gotchas

The browser must not set Content-Type for FormData; the browser owns the multipart boundary. The server validates the extension and MIME at the upload boundary and stores the file under a UUID-derived user path. Do not use a client filename as a filesystem path.
