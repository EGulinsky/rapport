import { test, expect } from './fixtures'

const FIRMA = 'Batch Test GmbH'
const API_BASE = process.env.E2E_API_URL ?? 'http://localhost:8001'

async function createApp(page: any, token: string, rolle: string) {
  const res = await page.request.post(`${API_BASE}/api/applications/`, {
    data: { firma: FIRMA, rolle, main_status: 'applied' },
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok()) throw new Error(`createApp failed: ${res.status()}`)
  return res.json()
}

test.describe('Batch AI Assessment (Journey 9)', () => {

  test('triggers batch, shows progress, completes', async ({ page, authToken }) => {
    await createApp(page, authToken, 'Engineer 1')
    await createApp(page, authToken, 'Engineer 2')

    let batchCalled = false
    await page.route('**/api/applications/ai-assess-all', async (route) => {
      batchCalled = true
      // Simulate latency so "KI läuft…" is visible
      await new Promise(r => setTimeout(r, 300))
      const body = [
        'data: ' + JSON.stringify({ status: 'start', total: 2 }),
        '',
        'data: ' + JSON.stringify({ status: 'progress', done: 1, total: 2, firma: FIRMA }),
        '',
        'data: ' + JSON.stringify({ status: 'progress', done: 2, total: 2, firma: FIRMA }),
        '',
        'data: ' + JSON.stringify({ status: 'done', updated: 2, errors: [] }),
        '',
      ].join('\n')
      await route.fulfill({ status: 200, headers: { 'Content-Type': 'text/event-stream' }, body })
    })

    await page.goto('/')
    await page.waitForSelector('[data-testid="stats-bar"]', { timeout: 15_000 })

    await page.getByTestId('ai-assess-all-button').click()

    await expect(page.getByTestId('ai-assess-all-button')).toContainText(/l\u00e4uft|running/i, { timeout: 3_000 })
    await expect(page.getByTestId('ai-assess-all-button')).not.toContainText(/l\u00e4uft|running/i, { timeout: 10_000 })

    expect(batchCalled).toBe(true)
  })

  test('handles rate limit error gracefully during batch', async ({ page, authToken }) => {
    await createApp(page, authToken, 'Rate Limit Role')

    await page.route('**/api/applications/ai-assess-all', async (route) => {
      await new Promise(r => setTimeout(r, 200))
      const body = [
        'data: ' + JSON.stringify({ status: 'start', total: 1 }),
        '',
        'data: ' + JSON.stringify({ status: 'progress', done: 1, total: 1, firma: FIRMA, error: 'Rate-Limit erreicht' }),
        '',
        'data: ' + JSON.stringify({ status: 'done', updated: 0, errors: ['Rate-Limit erreicht'] }),
        '',
      ].join('\n')
      await route.fulfill({ status: 200, headers: { 'Content-Type': 'text/event-stream' }, body })
    })

    await page.goto('/')
    await page.waitForSelector('[data-testid="stats-bar"]', { timeout: 15_000 })

    await page.getByTestId('ai-assess-all-button').click()

    await expect(page.getByTestId('ai-assess-all-button')).toContainText(/l\u00e4uft|running/i, { timeout: 3_000 })
    await expect(page.getByTestId('ai-assess-all-button')).not.toContainText(/l\u00e4uft|running/i, { timeout: 10_000 })
  })
})
