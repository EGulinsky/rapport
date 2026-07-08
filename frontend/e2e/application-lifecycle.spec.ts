import { test, expect } from './fixtures'

const COMPANY = 'E2E Testfirma GmbH'
const ROLE = 'Senior Test Engineer'
const API_BASE = process.env.E2E_API_URL ?? 'http://localhost:8001'

async function createCompany(page: any, token: string) {
  const res = await page.request.post(`${API_BASE}/api/companies`, {
    data: { name: COMPANY },
    headers: { Authorization: `Bearer ${token}` },
  })
  return res.json()
}

async function createApplication(page: any, token: string, companyId: number) {
  const res = await page.request.post(`${API_BASE}/api/applications/`, {
    data: { firma: COMPANY, rolle: ROLE, main_status: 'applied', company_profile_id: companyId },
    headers: { Authorization: `Bearer ${token}` },
  })
  return res.json()
}

test.describe('Application Lifecycle (Journey 1)', () => {
  test.beforeEach(async ({ page, authToken }) => {
    const company = await createCompany(page, authToken)
    await createApplication(page, authToken, company.id)
    await page.goto('/')
    await page.waitForSelector('text=Anbahnung', { timeout: 15_000 })
  })

  test('creates an application, changes status, rejects, and shows reasoning', async ({ page }) => {
    // ── 1. Verify the application appears ──────────────────────────────
    await expect(page.getByText(COMPANY).first()).toBeVisible({ timeout: 5_000 })
    await expect(page.getByText(ROLE).first()).toBeVisible()

    // ── 2. Open the app and change status ──────────────────────────────
    await page.getByText(ROLE).first().click()
    await page.waitForSelector('text=Verlauf', { timeout: 5_000 })

    await page.getByRole('button', { name: 'Bearbeiten' }).click()
    await page.getByRole('button', { name: 'Beworben', exact: true }).click()
    await page.getByRole('button', { name: 'Speichern' }).click()

    // ── 3. Re-open and change to HR ────────────────────────────────────
    await page.getByRole('button', { name: 'Bearbeiten' }).click()
    await page.getByRole('button', { name: 'Gespräch HR/HH' }).last().click()
    await page.getByRole('button', { name: 'Speichern' }).click()

    // ── 4. Re-open and reject ──────────────────────────────────────────
    await page.getByRole('button', { name: 'Bearbeiten' }).click()
    await page.getByRole('button', { name: 'Absage', exact: true }).click()
    await page.getByRole('button', { name: 'Speichern' }).click()

    // ── 5. Verify rejection ────────────────────────────────────────────
    await expect(page.getByText('Abgesagt').first()).toBeVisible({ timeout: 5_000 })
  })
})
