# podking feature map

This map covers the user-facing surfaces that prove audio transcription works.

| Feature | Surface | Proof |
| --- | --- | --- |
| [Upload and queue](upload-and-queue.md) | /transcriptions | A supported file creates a queued owned record and job. |
| [History and text download](history-and-download.md) | /transcriptions | A completed record shows its description and returns a UTF-8 .txt attachment. |
| [Navigation and protected access](navigation-and-protection.md) | React Router and FastAPI auth | The tab is reachable for an authenticated user and protected without a session. |
