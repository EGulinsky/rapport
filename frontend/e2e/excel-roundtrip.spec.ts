import { test, expect } from './fixtures'

const API_BASE = process.env.E2E_API_URL ?? 'http://localhost:8001'

test.describe('Excel Round-Trip (Journey 12)', () => {

  test('exports and imports Excel, shows correct import counts', async ({ page, authToken }) => {
    // Create applications via API to have data for the round-trip
    for (const app of [
      { firma: 'Excel Round AG', rolle: 'Developer', main_status: 'applied' },
      { firma: 'Excel Round GmbH', rolle: 'Manager', main_status: 'hr' },
      { firma: 'Excel Round KG', rolle: 'Designer', main_status: 'signed' },
    ]) {
      const res = await page.request.post(`${API_BASE}/api/applications/`, {
        data: app,
        headers: { Authorization: `Bearer ${authToken}` },
      })
      if (!res.ok()) throw new Error(`createApp failed: ${res.status()}`)
    }

    let exportCalled = false
    let importCalled = false

    // Mock export endpoint — returns a blob with Content-Disposition
    await page.route(/\/api\/export\/excel/, async (route) => {
      exportCalled = true
      await route.fulfill({
        status: 200,
        headers: {
          'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          'Content-Disposition': 'attachment; filename="rapport_export_2026-07-09.xlsx"',
        },
        body: Buffer.from('mock-excel-content'),
      })
    })

    // Mock import endpoint — returns ImportResult JSON
    await page.route(/\/api\/import\/excel/, async (route) => {
      importCalled = true
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          imported: 3,
          skipped: 0,
          errors: [],
          message: 'Import erfolgreich: 3 Einträge importiert.',
        }),
      })
    })

    await page.goto('/')
    await expect(page.getByTestId('stats-bar')).toBeVisible({ timeout: 15_000 })

    // ---------- Export ----------
    await page.getByTestId('import-export-menu-button').click()
    await expect(page.getByTestId('export-excel-button')).toBeVisible()
    await page.getByTestId('export-excel-button').click()
    await page.waitForTimeout(300)
    expect(exportCalled).toBe(true)

    // ---------- Import ----------
    // Re-open dropdown
    await page.getByTestId('import-export-menu-button').click()
    await expect(page.getByTestId('import-excel-button')).toBeVisible()
    await page.getByTestId('import-excel-button').click()

    // Set file on the hidden input
    const fileInput = page.locator('input[type="file"]')
    await fileInput.setInputFiles({
      name: 'test_import.xlsx',
      mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      buffer: Buffer.from('dummy-excel-bytes'),
    })

    // Wait for import result modal
    await expect(page.getByText('Excel-Import abgeschlossen')).toBeVisible({ timeout: 5_000 })
    await expect(page.getByText('Import erfolgreich: 3 Einträge importiert.')).toBeVisible()
    // Verify the imported count badge is shown
    await expect(page.getByTestId('import-result-imported')).toBeVisible()
    expect(importCalled).toBe(true)
  })
})
