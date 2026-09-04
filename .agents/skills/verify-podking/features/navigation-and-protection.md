# Navigation and protected access

## Sub-features

- Reach the new page through the top navigation.
- Keep the route inside the existing authenticated shell.
- Return JSON 401 for API access without a session.

## How to get to it (user POV)

Sign in, select Transcriptions, and see the upload form and generated history. A signed-out user is redirected to the existing login page.

## Driving it with Playwright

Assert getByRole("link", { name: "Transcriptions" }), the heading /Turn a recording into/i, and getByRole("heading", { name: "Generated history" }). Clear cookies and navigate to /transcriptions to verify the existing auth redirect. Use page.request.get("/api/transcriptions") without a session to assert 401.

## Gotchas

The normal e2e backend must run with TEST_MODE=1 only for the allowlisted test login route. Never enable that setting in production. Direct navigation needs the built frontend served by FastAPI.
