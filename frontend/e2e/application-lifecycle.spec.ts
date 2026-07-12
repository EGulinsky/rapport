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
    await page.waitForSelector('[data-testid="stats-bar"]', { timeout: 15_000 })
  })

  test('creates an application, changes status, rejects, and shows reasoning', async ({ page }) => {
    // ── 1. Verify the application appears ──────────────────────────────
    await expect(page.getByText(COMPANY).first()).toBeVisible({ timeout: 5_000 })
    await expect(page.getByText(ROLE).first()).toBeVisible()

    // ── 2. Open the app and change status ──────────────────────────────
    await page.getByText(ROLE).first().click()
    await page.waitForSelector('[data-testid="modal-tab-timeline"]', { timeout: 5_000 })

    await page.getByTestId('edit-application-button').click()
    await page.getByTestId('status-btn-applied').click()
    await page.getByTestId('save-application-button').click()

    // ── 3. Re-open and change to HR ────────────────────────────────────
    await page.getByTestId('edit-application-button').click()
    await page.getByTestId('status-btn-hr').click()
    await page.getByTestId('save-application-button').click()

    // ── 4. Re-open and reject ──────────────────────────────────────────
    await page.getByTestId('edit-application-button').click()
    await page.getByTestId('status-btn-rejected').click()
    await page.getByTestId('save-application-button').click()

    // ── 5. Verify rejection ────────────────────────────────────────────
    await expect(page.getByTestId('status-badge-rejected').first()).toBeVisible({ timeout: 5_000 })
  })
})
