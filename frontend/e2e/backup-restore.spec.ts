import { test, expect } from './fixtures'

const API_BASE = process.env.E2E_API_URL ?? 'http://localhost:8001'

test.describe('Backup & Restore (Journey 11)', () => {

  test('configures backup, runs manual backup, sees file in list', async ({ page, authToken }) => {
    // Create an app so DB has data
    await page.request.post(`${API_BASE}/api/applications/`, {
      data: { firma: 'Backup Test GmbH', rolle: 'Backup Role', main_status: 'applied' },
      headers: { Authorization: `Bearer ${authToken}` },
    })

    await page.route(/\/api\/backup\//, async (route) => {
      const url = route.request().url()
      if (url.includes('/status')) {
        return route.fulfill({
          status: 200,
          body: JSON.stringify({
            enabled: false, backup_folder: '/Users/test/Backups', frequency_hours: 24, keep_count: 7,
            last_backup: '2026-07-09T12:00:00', backups: [
              { name: 'rapport_backup_2026-07-09T12-00-00.zip', path: '/Users/test/Backups', modified: 1720000000, size: 512000 },
            ],
          }),
        })
      }
      if (url.includes('/settings')) {
        return route.fulfill({
          status: 200,
          body: JSON.stringify({
            enabled: false, backup_folder: '/Users/test/Backups', frequency_hours: 24, keep_count: 7,
            last_backup: null,
          }),
        })
      }
      if (url.includes('/run')) {
        return route.fulfill({
          status: 200,
          body: JSON.stringify({ success: true, filename: 'rapport_backup_2026-07-09T13-00-00.zip' }),
        })
      }
      if (url.includes('/restore')) {
        return route.fulfill({
          status: 200,
          body: JSON.stringify({ success: true, filename: 'rapport_backup_2026-07-09T12-00-00.zip' }),
        })
      }
      return route.fulfill({ status: 200, body: JSON.stringify({}) })
    })

    await page.goto('/')
    await page.waitForSelector('text=Anbahnung', { timeout: 15_000 })

    // Open Settings modal
    await page.locator('button[title="KI-Einstellungen"]').click()
    await expect(page.getByText('Einstellungen')).toBeVisible()

    // Navigate to Backup tab in sidebar
    await page.locator('nav button', { hasText: 'Backup' }).click()
    await page.waitForTimeout(300)

    // Verify Backup panel is visible
    await expect(page.getByText('Datenbank-Backup')).toBeVisible()

    // Set backup folder
    const folderInput = page.locator('input[placeholder*="/Users/…/Backups/Rapport"]')
    await folderInput.fill('/Users/test/Backups')

    // Save settings
    await page.locator('button', { hasText: 'Speichern' }).first().click()
    await expect(page.getByText('Gespeichert')).toBeVisible({ timeout: 5_000 })

    // Run manual backup
    await page.locator('button', { hasText: 'Jetzt sichern' }).click()
    await expect(page.getByText(/Backup erstellt/)).toBeVisible({ timeout: 5_000 })

    // Verify backup appears in existing backups list
    await expect(page.getByText('Vorhandene Backups')).toBeVisible()
    await expect(page.getByText('rapport_backup_2026-07-09T12-00-00.zip')).toBeVisible()

    // Test restore flow: click Restore → confirmation dialog appears
    await page.locator('button', { hasText: 'Restore' }).first().click()
    await expect(page.getByText('Backup wirklich wiederherstellen?')).toBeVisible()
    await expect(page.getByText('Ja, wiederherstellen')).toBeVisible()

    // Click restore confirmation
    await page.getByText('Ja, wiederherstellen').click()
    await expect(page.getByText(/Wiederhergestellt aus/)).toBeVisible({ timeout: 5_000 })
  })
})
