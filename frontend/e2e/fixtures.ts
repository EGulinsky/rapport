import { test as base, type Page } from '@playwright/test'

export const E2E_USER = {
  email: 'e2e-test@rapport.local',
  password: 'TestPassword123!',
}

const API_BASE = process.env.E2E_API_URL ?? 'http://localhost:8001'

async function setupUser(page: Page) {
  const res = await page.request.post(`${API_BASE}/api/e2e/setup-user`, {
    data: { email: E2E_USER.email, password: E2E_USER.password },
  })
  if (!res.ok()) {
    throw new Error(`setup-user failed: ${res.status()} ${await res.text()}`)
  }
  const body = await res.json()
  return body.access_token as string
}

export const test = base.extend<{ authToken: string }>({
  authToken: async ({ page }, use) => {
    const token = await setupUser(page)
    await page.goto('/')
    await page.evaluate((t) => {
      localStorage.setItem('rapport_auth_token', t)
    }, token)
    await use(token)
  },
})

export { expect } from '@playwright/test'
