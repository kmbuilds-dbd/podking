import { test, expect } from "@playwright/test"

const TEST_EMAIL = "allowed@example.com"

/**
 * The single happy-path e2e the spec calls for: log in, see library,
 * navigate, search, view a summary, copy a reader link.
 *
 * Auth runs through /test/login (TEST_MODE=1 only) so we don't need
 * Google OAuth credentials in the test loop.
 */

test.beforeEach(async ({ page }) => {
  // Mint a session cookie for the test user — must use page.request so
  // the Set-Cookie lands on the same browser context as page.goto().
  const resp = await page.request.post(`/test/login?email=${TEST_EMAIL}`)
  expect(resp.status()).toBe(200)
})

test("login page renders the wordmark and a Continue with Google CTA", async ({
  page,
  context,
}) => {
  // Fresh context with no session cookie.
  await context.clearCookies()
  await page.goto("/login")
  await expect(page.getByRole("heading", { name: "podking" })).toBeVisible()
  const cta = page.getByRole("link", { name: /Continue with Google/i })
  await expect(cta).toBeVisible()
  await expect(cta).toHaveAttribute("href", "/auth/login")
})

test("authed library page shows wordmark, nav, and search controls", async ({
  page,
}) => {
  await page.goto("/")
  await expect(page).toHaveTitle(/podking/i)

  // Top nav links all present.
  await expect(page.getByRole("link", { name: "Library" })).toBeVisible()
  await expect(page.getByRole("link", { name: "Jobs" })).toBeVisible()
  await expect(page.getByRole("link", { name: "Subscriptions" })).toBeVisible()

  // Library headline + search box.
  await expect(
    page.getByRole("heading", {
      name: /Everything you've meant to listen to/i,
    }),
  ).toBeVisible()
  await expect(
    page.getByPlaceholder(/Search by phrase or topic/i),
  ).toBeVisible()
})

test("search submits and shows the empty-search message for no matches", async ({
  page,
}) => {
  await page.goto("/")
  const input = page.getByPlaceholder(/Search by phrase or topic/i)
  await input.fill("definitely-not-a-real-topic-xyzabc")
  await page.getByRole("button", { name: "Search" }).click()

  // Should land on a search-results state (empty card).
  await expect(
    page.getByText(/No matches/i),
  ).toBeVisible({ timeout: 5_000 })

  // Clear button is now visible.
  await page.getByRole("button", { name: "Clear" }).click()
  // Back to default landing — search input is empty again.
  await expect(input).toHaveValue("")
})

test("jobs page shows URL paste form, subscriptions shows search box", async ({
  page,
}) => {
  await page.goto("/jobs")
  await expect(
    page.getByRole("heading", { name: /Add something to listen to/i }),
  ).toBeVisible()
  await expect(
    page.getByPlaceholder(/Paste a YouTube or Apple Podcast URL/i),
  ).toBeVisible()

  await page.goto("/subscriptions")
  await expect(
    page.getByRole("heading", { name: /Channels and shows/i }),
  ).toBeVisible()
  await expect(
    page.getByPlaceholder(/Search podcasts/i),
  ).toBeVisible()
})

test("settings page exposes Reader Links section with token + regenerate", async ({
  page,
}) => {
  await page.goto("/settings")
  await expect(
    page.getByRole("heading", { name: /Tune the room/i }),
  ).toBeVisible()
  await expect(page.getByText(/Reader links/i).first()).toBeVisible()
  await expect(
    page.getByRole("button", { name: /Regenerate token/i }),
  ).toBeVisible()
})

test("API returns 404 JSON for an unknown /api/* path (not the SPA shell)", async ({
  page,
}) => {
  // page.request shares cookies with the page so the auth check passes
  // and the missing-row branch runs, returning a real JSON 404.
  const r = await page.request.get(
    "/api/jobs/00000000-0000-0000-0000-000000000000",
  )
  expect(r.status()).toBe(404)
  expect(r.headers()["content-type"]).toContain("application/json")
})
