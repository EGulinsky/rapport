import { test, expect } from './fixtures'

const FIRMA = 'Sync Selektiert'
const API_BASE = process.env.E2E_API_URL ?? 'http://localhost:8001'

async function createCompany(page: any, token: string, name: string) {
  const res = await page.request.post(`${API_BASE}/api/companies`, {
    data: { name },
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok()) throw new Error(`createCompany failed: ${res.status()}`)
  return res.json()
}

test.describe('Company Sync Selection (Journey 10)', () => {

  test('selects companies, runs scoped sync, no auto-continue', async ({ page, authToken }) => {
    const names = ['Sync Alpha', 'Sync Beta', 'Sync Gamma']
    for (const n of names) await createCompany(page, authToken, n)

    let runCalls = 0
    await page.route(/\/api\/sync\/company\//, async (route) => {
      const url = route.request().url()
      if (url.includes('/reset-lock')) {
        return route.fulfill({ status: 200, body: JSON.stringify({ ok: true }) })
      }
      if (url.includes('/run')) {
        runCalls++
        return route.fulfill({ status: 200, body: JSON.stringify({ started: true, count: 2 }) })
      }
      if (url.includes('/status')) {
        return route.fulfill({
          status: 200,
          body: JSON.stringify({
            running: false, current_company: null,
            pending: 0, done: 2, failed: 0,
            needs_review: 0, profiles: [],
          }),
        })
      }
      return route.fulfill({ status: 200, body: JSON.stringify({}) })
    })

    await page.goto('/')
    await page.waitForSelector('[data-testid="stats-bar"]', { timeout: 15_000 })

    // Navigate to Companies tab
    await page.getByTestId('nav-companies').click()

    // Wait for company table to render with data
    await page.waitForSelector('tbody tr', { timeout: 5_000 })

    // Click checkboxes in tbody rows to select 2 companies
    const rowChecks = page.locator('tbody tr td:first-child input[type="checkbox"]')
    await rowChecks.nth(0).click({ force: true })
    await rowChecks.nth(1).click({ force: true })

    // Verify Sync button shows selection count
    await expect(page.getByTestId('sync-companies-button')).toContainText('2', { timeout: 5_000 })

    // Open dropdown and click the (non-reset) Sync option
    await page.getByTestId('sync-companies-button').click()
    await page.getByTestId('sync-menu-sync-option').click()

    // Verify progress message, then wait for sync to finish (bar shows final counts)
    await expect(page.getByTestId('company-sync-status-bar')).toBeVisible({ timeout: 5_000 })
    await expect(page.getByTestId('company-sync-status-bar')).toContainText('2', { timeout: 15_000 })

    // Verify only initial run call — no auto-continue
    expect(runCalls).toBe(1)
  })
})
