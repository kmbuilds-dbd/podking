import { test, expect } from "@playwright/test"

const TEST_EMAIL = "allowed@example.com"

/**
 * Audio podcast feature visibility. The full TTS happy path (Claude →
 * ElevenLabs → git push) needs network + secrets; instead, this suite
 * pins the feature-flag negative case: when the server isn't configured
 * for audio, the Generate audio button must NOT appear in the UI.
 *
 * The test backend runs with TEST_MODE=1 and (per the README) no
 * GITHUB_PAT — so audio_enabled comes back false from /api/me.
 */

test.beforeEach(async ({ page }) => {
  const resp = await page.request.post(`/test/login?email=${TEST_EMAIL}`)
  expect(resp.status()).toBe(200)
})

test("Generate audio button is hidden when the feature is disabled", async ({
  page,
}) => {
  // Confirm the server reports the feature is off.
  const me = await page.request.get("/api/me")
  expect(me.status()).toBe(200)
  expect((await me.json()).audio_enabled).toBe(false)

  // The Library page never renders the button regardless of how many
  // summary cards are present.
  await page.goto("/")
  await expect(page.getByRole("button", { name: /Generate audio/i }))
    .toHaveCount(0)
})
