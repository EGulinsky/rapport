import { test, expect } from './fixtures'

const COMPANY = 'Sync Test GmbH'
const ROLE = 'Sync Target'
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

test.describe('Targeted Sync (Journey 6)', () => {

  test('triggers targeted sync for an application and shows result via mocked backend', async ({ page, authToken }) => {
    // ── 1. Create company + app ─────────────────────────────────────
    const company = await createCompany(page, authToken)
    const app = await createApp(page, authToken, company.id)
    console.log(`Created app ${app.id} for targeted sync`)

    // ── 2. Mock sync endpoints — browser calls /api/sync/... ────────
    await page.route(/\/api\/sync\//, async (route) => {
      const url = route.request().url()
      const method = route.request().method()

      if (url.includes('/linkedin/config')) {
        return route.fulfill({ status: 200, body: JSON.stringify({ configured: false }) })
      }
      if (url.includes('/google/progress') || url.includes('/progress')) {
        return route.fulfill({ status: 200, body: JSON.stringify({}) })
      }
      if (url.endsWith('/result')) {
        return route.fulfill({ status: 200, body: JSON.stringify({ done: true, created: 3, errors: [] }) })
      }
      if (method === 'POST') {
        return route.fulfill({ status: 200, body: JSON.stringify({ processed: 0, created: 0, skipped: 0, errors: [] }) })
      }
      return route.fulfill({ status: 200, body: JSON.stringify({}) })
    })

    // ── 3. Open modal ──────────────────────────────────────────────
    await page.goto('/')
    await page.waitForSelector('text=Anbahnung', { timeout: 15_000 })
    await page.getByText(ROLE).first().click()
    await page.waitForSelector('text=Verlauf', { timeout: 5_000 })

    // ── 4. Click the modal's Sync button (via title) ────────────────
    const syncPromise = page.waitForRequest(req => req.url().includes('/api/sync/targeted/') && req.method() === 'POST' && !req.url().endsWith('/reset'), { timeout: 5_000 })
    await page.locator('button[title="Gezielter Sync für diese Bewerbung (KI)"]').click()
    await syncPromise
    console.log('Sync POST request fired')

    // ── 5. Wait for result banner ──────────────────────────────────
    await expect(
      page.getByText('Sync abgeschlossen — 3 neue Einträge')
    ).toBeVisible({ timeout: 15_000 })
  })
})
