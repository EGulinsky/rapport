import { test, expect } from './fixtures'

const COMPANY = 'Manual Assign GmbH'
const ROLE = 'Manual Target'
const API_BASE = process.env.E2E_API_URL ?? 'http://localhost:8001'

const MOCK_CANDIDATES = [
  { id: 1, source: 'gmail', external_id: 'a1', titel: 'Mail von HR', datum: '2026-07-01', extract: 'Einladung', confidence: 85 },
  { id: 2, source: 'gcal', external_id: 'b2', titel: 'Interview Termin', datum: '2026-07-05', confidence: 90 },
]

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

test.describe('Manual Candidate Assignment (Journey 7)', () => {

  test('opens manual assign dialog, selects candidates, imports them', async ({ page, authToken }) => {
    const company = await createCompany(page, authToken)
    const app = await createApp(page, authToken, company.id)
    console.log(`Created app ${app.id} for manual assign`)

    let assignCalls = 0
    await page.route(/\/api\/sync\//, async (route) => {
      const url = route.request().url()
      const method = route.request().method()
      if (url.includes('/candidates')) {
        return route.fulfill({ status: 200, body: JSON.stringify(MOCK_CANDIDATES) })
      }
      if (url.includes('/assign') && method === 'POST') {
        assignCalls++
        return route.fulfill({ status: 200, body: JSON.stringify({ conflict: false, event_id: 99 + assignCalls }) })
      }
      return route.fulfill({ status: 200, body: JSON.stringify({}) })
    })

    await page.goto('/')
    await page.waitForSelector('text=Anbahnung', { timeout: 15_000 })
    await page.getByText(ROLE).first().click()
    await page.waitForSelector('text=Verlauf', { timeout: 5_000 })
    console.log('Modal open')

    await page.locator('button[title="Gezielter Sync für diese Bewerbung (KI)"] + button').click()
    await page.waitForTimeout(200)
    await page.getByText('Manuell zuordnen').first().click()
    console.log('Manual dialog opened')

    await expect(page.getByText('Mail von HR')).toBeVisible({ timeout: 5_000 })
    await expect(page.getByText('Interview Termin')).toBeVisible()
    console.log('Candidates visible')

    // Check candidate checkboxes via evaluate (bypasses overlay pointer-events)
    await page.evaluate(() => {
      const overlay = document.querySelector('[class*="z-[60]"]')
      if (!overlay) throw new Error('manual dialog overlay not found')
      const cbs = overlay.querySelectorAll('input[type="checkbox"]')
      if (cbs.length < 2) throw new Error(`expected >=2 checkboxes in dialog, got ${cbs.length}`)
      cbs.forEach(cb => (cb as HTMLInputElement).click())
    })
    console.log('Both selected')

    await page.getByRole('button', { name: /2 importieren/ }).click()
    console.log('Import triggered')

    await expect(page.getByText('Mail von HR')).not.toBeVisible({ timeout: 10_000 })
    await expect(page.getByText('Interview Termin')).not.toBeVisible()
    expect(assignCalls).toBe(2)
    console.log('Done')
  })
})
