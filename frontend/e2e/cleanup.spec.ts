import { test, expect } from './fixtures'

const COMPANY = 'Cleanup Test GmbH'
const ROLE = 'Trainee Cleanup'
const API_BASE = process.env.E2E_API_URL ?? 'http://localhost:8001'

async function createCompany(page: any, token: string) {
  const res = await page.request.post(`${API_BASE}/api/companies`, {
    data: { name: COMPANY },
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok()) throw new Error(`createCompany failed: ${res.status()} ${await res.text()}`)
  return res.json()
}

async function createApp(page: any, token: string, companyId: number) {
  const res = await page.request.post(`${API_BASE}/api/applications/`, {
    data: { firma: COMPANY, rolle: ROLE, main_status: 'applied', company_profile_id: companyId },
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok()) throw new Error(`createApp failed: ${res.status()} ${await res.text()}`)
  return res.json()
}

test.describe('Cleanup (Journey 4)', () => {

  test('preview detects duplicates, then executes cleanup via UI', async ({ page, authToken }) => {
    // ── 1. Create duplicates: 2 apps with same firma + rolle ────────────
    const company = await createCompany(page, authToken)
    const app1 = await createApp(page, authToken, company.id)
    const app2 = await createApp(page, authToken, company.id)
    console.log(`Created apps ${app1.id} and ${app2.id}`)

    // ── 2. Navigate to main view ──────────────────────────────────────
    await page.goto('/')
    await page.waitForSelector('[data-testid="stats-bar"]', { timeout: 15_000 })

    // ── 3. Click "Bereinigen" ──────────────────────────────────────────
    await page.getByTestId('cleanup-button').click()

    // Wait for the modal preview to load → execute-cleanup button
    await page.waitForSelector('[data-testid="cleanup-execute-button"]', { timeout: 15_000 })

    // ── 4. Click it to execute cleanup ──────────────────────────────────
    await page.getByTestId('cleanup-execute-button').click()

    // Wait for cleanup result
    await expect(
      page.getByTestId('cleanup-done-title')
    ).toBeVisible({ timeout: 25_000 })

    // ── 5. Close modal ─────────────────────────────────────────────────
    await page.getByTestId('cleanup-close-button').click()
    await page.waitForTimeout(500)

    // ── 6. Verify at least one app remains ─────────────────────────────
    await expect(page.getByText(ROLE).first()).toBeVisible({ timeout: 5_000 })
  })
})
