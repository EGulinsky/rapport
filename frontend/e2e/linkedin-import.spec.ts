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
    await page.waitForSelector('[data-testid="stats-bar"]', { timeout: 15_000 })
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
    await page.getByTestId('new-menu-button').click()
    await page.getByTestId('new-menu-import-linkedin').click()
    await expect(page.getByTestId('linkedin-import-title')).toBeVisible({ timeout: 5_000 })

    // ── 3. Paste a LinkedIn job URL ─────────────────────────────────────
    await page.locator('input[type="url"]').fill(LI_URL)

    // ── 4. Click "Importieren" ──────────────────────────────────────────
    await page.getByTestId('linkedin-import-submit-button').click()

    // ── 5. Verify NewApplicationModal opens with pre-filled data ────────
    await expect(page.getByTestId('new-application-title')).toBeVisible({ timeout: 8_000 })

    // Company picker should show the pre-filled company name
    await expect(page.getByText(COMPANY).first()).toBeVisible()

    // Role, source, and comment should be pre-filled
    await expect(page.getByPlaceholder('Rolle *')).toHaveValue(ROLE)
    await expect(page.getByPlaceholder('Quelle (LinkedIn, XING, …)')).toHaveValue(SOURCE)
    await expect(page.getByPlaceholder('Kommentar (optional)')).toHaveValue(COMMENT)

    // ── 6. Submit the form ──────────────────────────────────────────────
    await page.getByTestId('new-application-submit-button').click()

    // ── 7. Verify the application appears in the kanban board ───────────
    await expect(page.getByText(COMPANY).first()).toBeVisible({ timeout: 5_000 })
    await expect(page.getByText(ROLE).first()).toBeVisible()
  })

})
