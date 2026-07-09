import { test, expect } from './fixtures'

const COMPANY = 'Merge Test GmbH'
const ROLE = 'Merge Candidate'
const API_BASE = process.env.E2E_API_URL ?? 'http://localhost:8001'

async function createCompany(page: any, token: string) {
  const res = await page.request.post(`${API_BASE}/api/companies`, {
    data: { name: COMPANY },
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok()) throw new Error(`createCompany failed: ${res.status()} ${await res.text()}`)
  return res.json()
}

async function createApp(page: any, token: string, companyId: number, overrides: Record<string, unknown> = {}) {
  const res = await page.request.post(`${API_BASE}/api/applications/`, {
    data: { firma: COMPANY, rolle: ROLE, main_status: 'applied', company_profile_id: companyId, ...overrides },
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok()) throw new Error(`createApp failed: ${res.status()} ${await res.text()}`)
  return res.json()
}

async function fetchApps(page: any, token: string) {
  const res = await page.request.get(`${API_BASE}/api/applications/`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok()) throw new Error(`fetchApps failed: ${res.status()} ${await res.text()}`)
  const body = await res.json()
  return body.applications ?? body ?? []
}

test.describe('Merge Dialog (Journey 5)', () => {

  test('merges two applications with different fields via table view', async ({ page, authToken }) => {
    // ── 1. Create company and 2 apps with different metadata ────────
    const company = await createCompany(page, authToken)
    const app1 = await createApp(page, authToken, company.id, { quelle: 'LinkedIn', kommentar: 'Original' })
    const app2 = await createApp(page, authToken, company.id, { quelle: 'XING', kommentar: 'Duplicate' })
    console.log(`Created apps ${app1.id} and ${app2.id} for merge`)

    // ── 2. Navigate and switch to table view ───────────────────────
    await page.goto('/')
    await page.waitForSelector('text=Anbahnung', { timeout: 15_000 })
    await page.getByRole('button', { name: '☰ Tabelle' }).click()
    await page.waitForTimeout(300)

    // ── 3. Find our specific rows and check their checkboxes ──────
    const ourRows = page.locator('tbody tr', { hasText: COMPANY })
    await expect(ourRows).toHaveCount(2, { timeout: 5_000 })
    await ourRows.nth(0).locator('input[type="checkbox"]').check()
    await ourRows.nth(1).locator('input[type="checkbox"]').check()

    // ── 4. Click "Mergen (2)" ──────────────────────────────────────
    await page.getByRole('button', { name: /Mergen/ }).click()
    await page.waitForSelector('text=Bewerbungen zusammenführen', { timeout: 5_000 })

    // ── 5. Click "Zusammenführen" ──────────────────────────────────
    await page.getByRole('button', { name: 'Zusammenführen' }).click()

    // ── 6. Wait for modal to close (merge completed) ───────────────
    await expect(page.getByText('Bewerbungen zusammenführen')).not.toBeVisible({ timeout: 10_000 })

    // ── 7. Verify via API: only 1 app remains with our firma+rolle ─
    const apps = await fetchApps(page, authToken)
    const ours = apps.filter((a: any) => a.firma === COMPANY && a.rolle === ROLE)
    expect(ours).toHaveLength(1)
  })
})
