import { test, expect } from "@playwright/test"

const TEST_EMAIL = "allowed@example.com"

test.beforeEach(async ({ page }) => {
  const response = await page.request.post(`/test/login?email=${TEST_EMAIL}`)
  expect(response.status()).toBe(200)
})

test("transcriptions tab exposes the upload form and generated history", async ({ page }) => {
  await page.goto("/transcriptions")

  await expect(page.getByRole("link", { name: "Transcriptions" })).toBeVisible()
  await expect(
    page.getByRole("heading", { name: /Turn a recording into/i }),
  ).toBeVisible()
  await expect(page.getByLabel("Audio file")).toBeVisible()
  await expect(page.getByLabel(/Description/)).toBeVisible()
  await expect(page.getByRole("heading", { name: "Generated history" })).toBeVisible()
  await expect(
    page.getByRole("button", { name: "Transcribe audio" }),
  ).toBeDisabled()
})

test("transcriptions tab rejects unsupported files before upload", async ({ page }) => {
  await page.goto("/transcriptions")
  await page.getByLabel("Audio file").setInputFiles({
    name: "notes.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("not audio"),
  })

  await expect(page.getByRole("alert")).toHaveText("Use an MP3, MP4, or WAV file.")
  await expect(
    page.getByRole("button", { name: "Transcribe audio" }),
  ).toBeDisabled()
})
