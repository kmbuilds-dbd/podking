# History and text download

## Sub-features

- Poll active transcription history until the worker finishes.
- Show description, original filename, status, and transcript preview.
- Download completed transcript text.
- Keep incomplete and failed rows visibly distinct.

## How to get to it (user POV)

Open Transcriptions, wait for a submitted row to show done, then select its Download text link.

## Driving it with Playwright

Use page.getByRole("link", { name: "Download text" }) and inspect the download response. Assert the response is text/plain, the Content-Disposition filename ends in .txt, and the body equals the persisted transcript. Backend coverage uses tests/test_transcriptions.py and stubs only the existing ElevenLabs HTTP boundary.

## Gotchas

The download endpoint is session-protected and user-scoped. It returns 409 until the backing job is done. The response filename is sanitized and includes the transcription UUID, so path traversal in the original filename cannot escape the download contract.
