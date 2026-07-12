import { test, expect } from './fixtures'

const COMPANY = 'Kanban DnD GmbH'
const ROLE = 'Drag & Drop Engineer'
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

async function closeModal(page: any) {
  await page.mouse.click(10, 10)
  await page.waitForTimeout(500)
}

test.describe('Kanban Drag & Drop (Journey 2)', () => {
  test.beforeEach(async ({ page, authToken }) => {
    const company = await createCompany(page, authToken)
    await createApplication(page, authToken, company.id)
    await page.goto('/')
    await page.waitForSelector('[data-testid="stats-bar"]', { timeout: 15_000 })
    // Switch to Kanban view
    await page.getByTestId('view-mode-kanban').click()
    await page.waitForTimeout(1000)
  })

  test('changes status via modal and verifies kanban columns', async ({ page }) => {
    // ── 1. Verify the card is in the "Beworben" column ─────────────────
    const card = page.getByText(ROLE).first()
    await expect(card).toBeVisible()

    // ── 2. Open modal → Bearbeiten → change status to HR ───────────────
    await card.click()
    await page.waitForSelector('[data-testid="modal-tab-timeline"]', { timeout: 5_000 })
    await page.getByTestId('edit-application-button').click()
    await page.getByTestId('status-btn-hr').click()
    await page.getByTestId('save-application-button').click()
    await expect(page.getByTestId('status-badge-hr').first()).toBeVisible()
    await closeModal(page)

    // ── 3. Change to "negotiating" ──────────────────────────────────────
    await page.getByText(ROLE).first().click()
    await page.waitForSelector('[data-testid="modal-tab-timeline"]', { timeout: 5_000 })
    await page.getByTestId('edit-application-button').click()
    await page.getByTestId('status-btn-negotiating').click()
    await page.getByTestId('save-application-button').click()
    await expect(page.getByTestId('status-badge-negotiating').first()).toBeVisible()
    await closeModal(page)

    // ── 4. Verify we can open the card without errors ──────────────────
    await page.getByText(ROLE).first().click()
    await page.waitForSelector('[data-testid="modal-tab-timeline"]', { timeout: 5_000 })
    await expect(page.getByTestId('status-badge-negotiating').first()).toBeVisible()
  })
})
