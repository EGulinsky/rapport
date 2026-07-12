import { test as base, type Page } from '@playwright/test'

export const E2E_USER = {
  email: 'e2e-test@rapport.local',
  password: 'TestPassword123!',
}

const API_BASE = process.env.E2E_API_URL ?? 'http://localhost:8001'

async function setupUser(page: Page, uiLanguage: 'de' | 'en') {
  const res = await page.request.post(`${API_BASE}/api/e2e/setup-user`, {
    data: { email: E2E_USER.email, password: E2E_USER.password, ui_language: uiLanguage },
  })
  if (!res.ok()) {
    throw new Error(`setup-user failed: ${res.status()} ${await res.text()}`)
  }
  const body = await res.json()
  return body.access_token as string
}

export const test = base.extend<{ uiLanguage: 'de' | 'en'; authToken: string }>({
  // Default 'de' matches the app's existing-user default (see i18n/index.ts) — override
  // per-spec or per-test with test.use({ uiLanguage: 'en' }) for the curated English subset.
  uiLanguage: ['de', { option: true }],
  authToken: async ({ page, uiLanguage }, use) => {
    const token = await setupUser(page, uiLanguage)
    await page.goto('/')
    await page.evaluate((t) => {
      localStorage.setItem('rapport_auth_token', t)
    }, token)
    await use(token)
  },
})

export { expect } from '@playwright/test'
