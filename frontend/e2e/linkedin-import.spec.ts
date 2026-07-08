import { test, expect } from './fixtures'

const COMPANY = 'LinkedIn Import GmbH'
const ROLE = 'Senior LinkedIn Engineer'
const SOURCE = 'LinkedIn'
const COMMENT = 'Gefunden via LinkedIn – spannendes Startup im KI-Bereich'
const LI_URL = 'https://www.linkedin.com/jobs/view/123456789'

const MOCKED_RESPONSE = {
  firma: COMPANY,
  rolle: ROLE,
  quelle: SOURCE,
  is_headhunter: false,
  zielfirma_bei_hh: null,
  kommentar: COMMENT,
  stellenanzeige_url: LI_URL,
  company_profile_id: null,
}

test.describe('LinkedIn Import (Journey 3)', () => {

  test.beforeEach(async ({ page, authToken }) => {
    await page.goto('/')
    await page.waitForSelector('text=Anbahnung', { timeout: 15_000 })
  })

  test('imports a LinkedIn link, prefills form, and saves application', async ({ page }) => {
    // ── 1. Mock backend extract endpoint ────────────────────────────────
    await page.route('**/api/applications/extract-from-linkedin-url', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCKED_RESPONSE),
      })
    })

    // ── 2. "Neu" → "Aus LinkedIn importieren" ──────────────────────────
    await page.getByRole('button', { name: /Neu/ }).click()
    await page.getByText('Aus LinkedIn importieren').click()
    await expect(page.getByText('Aus LinkedIn importieren').first()).toBeVisible({ timeout: 5_000 })

    // ── 3. Paste a LinkedIn job URL ─────────────────────────────────────
    await page.locator('input[type="url"]').fill(LI_URL)

    // ── 4. Click "Importieren" ──────────────────────────────────────────
    await page.getByRole('button', { name: 'Importieren' }).click()

    // ── 5. Verify NewApplicationModal opens with pre-filled data ────────
    await expect(page.getByText('Neue Bewerbung').first()).toBeVisible({ timeout: 8_000 })

    // Company picker should show the pre-filled company name
    await expect(page.getByText(COMPANY).first()).toBeVisible()

    // Role, source, and comment should be pre-filled
    await expect(page.locator('input[placeholder="Rolle *"]')).toHaveValue(ROLE)
    await expect(page.locator('input[placeholder="Quelle (LinkedIn, XING, …)"]')).toHaveValue(SOURCE)
    await expect(page.locator('textarea[placeholder="Kommentar (optional)"]')).toHaveValue(COMMENT)

    // ── 6. Submit the form ──────────────────────────────────────────────
    await page.getByRole('button', { name: 'Anlegen' }).click()

    // ── 7. Verify the application appears in the kanban board ───────────
    await expect(page.getByText(COMPANY).first()).toBeVisible({ timeout: 5_000 })
    await expect(page.getByText(ROLE).first()).toBeVisible()
  })

})
