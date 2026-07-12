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
    await page.waitForSelector('[data-testid="stats-bar"]', { timeout: 15_000 })

    // Open Settings modal
    await page.getByTestId('settings-button').click()
    await expect(page.getByTestId('settings-tab-backup')).toBeVisible()

    // Navigate to Backup tab in sidebar
    await page.getByTestId('settings-tab-backup').click()
    await page.waitForTimeout(300)

    // Verify Backup panel is visible
    await expect(page.getByTestId('backup-panel-title')).toBeVisible()

    // Set backup folder
    await page.getByTestId('backup-folder-input').fill('/Users/test/Backups')

    // Save settings
    await page.getByTestId('backup-save-button').click()
    await expect(page.getByTestId('backup-save-button')).toContainText(/gespeichert|saved/i, { timeout: 5_000 })

    // Run manual backup
    await page.getByTestId('backup-now-button').click()
    await expect(page.getByTestId('backup-run-result')).toBeVisible({ timeout: 5_000 })

    // Verify backup appears in existing backups list
    await expect(page.getByTestId('backup-existing-title')).toBeVisible()
    await expect(page.getByText('rapport_backup_2026-07-09T12-00-00.zip')).toBeVisible()

    // Test restore flow: click Restore → confirmation dialog appears
    await page.getByTestId('backup-restore-button').first().click()
    await expect(page.getByTestId('backup-restore-confirm-title')).toBeVisible()
    await expect(page.getByTestId('backup-restore-confirm-yes')).toBeVisible()

    // Click restore confirmation
    await page.getByTestId('backup-restore-confirm-yes').click()
    await expect(page.getByTestId('backup-restore-result')).toBeVisible({ timeout: 5_000 })
  })
})
