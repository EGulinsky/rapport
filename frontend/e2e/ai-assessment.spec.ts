import { test, expect } from './fixtures'

const FIRMA = 'KI Bewertung GmbH'
const ROLLE = 'AI Engineer'
const API_BASE = process.env.E2E_API_URL ?? 'http://localhost:8001'

async function createApp(page: any, token: string) {
  const res = await page.request.post(`${API_BASE}/api/applications/`, {
    data: { firma: FIRMA, rolle: ROLLE, main_status: 'applied' },
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok()) throw new Error(`createApp failed: ${res.status()} ${await res.text()}`)
  return res.json()
}

test.describe('AI Assessment (Journey 8)', () => {

  test('evaluates app, shows ampel and reasoning, re-evaluate updates result', async ({ page, authToken }) => {
    const app = await createApp(page, authToken)

    let callIndex = 0
    await page.route(/\/api\/applications\/\d+\/ai-assess/, async (route) => {
      callIndex++
      if (callIndex === 1) {
        await route.fulfill({
          status: 200, contentType: 'application/json',
          body: JSON.stringify({
            color: 'yellow',
            reasoning: 'Bisher nur Bewerbung eingereicht, noch kein Gespräch.',
            next_step: 'Auf Rückmeldung warten und ggf. nachfassen.',
          }),
        })
      } else {
        await route.fulfill({
          status: 200, contentType: 'application/json',
          body: JSON.stringify({
            color: 'green',
            reasoning: 'Gute Gespräche geführt, hohe Erfolgschance.',
            next_step: 'Auf Angebot warten.',
          }),
        })
      }
    })

    await page.goto('/')
    await page.waitForSelector('[data-testid="stats-bar"]', { timeout: 15_000 })

    // Open modal
    await page.getByText(ROLLE).first().click()
    await page.waitForSelector('[data-testid="modal-tab-timeline"]', { timeout: 5_000 })

    // First assessment: click "Jetzt bewerten"
    await page.getByTestId('ai-assess-now-button').click()

    // Wait for yellow result
    await expect(page.getByText('Mittlere Erfolgschance (30–60 %)')).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText('Bisher nur Bewerbung eingereicht')).toBeVisible()
    await expect(page.getByText('Auf Rückmeldung warten')).toBeVisible()
    await expect(page.getByText('Bewertet am')).toBeVisible()

    // Re-evaluate: click "Neu bewerten"
    await page.getByTestId('ai-reassess-button').click()

    // Wait for green result
    await expect(page.getByText('Hohe Erfolgschance (>60 %)')).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText('Gute Gespräche geführt')).toBeVisible()
    await expect(page.getByText('Auf Angebot warten')).toBeVisible()

    expect(callIndex).toBe(2)
  })
})
