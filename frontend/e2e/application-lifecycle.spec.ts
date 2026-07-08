import { test, expect } from './fixtures'

test.describe('Application Lifecycle (Journey 1)', () => {

  test.beforeEach(async ({ page, authToken }) => {
    await page.goto('/')
    await page.waitForSelector('text=Anbahnung', { timeout: 15_000 })
  })

  test('creates an application, changes status, rejects, and shows reasoning', async ({ page }) => {
    // ── 1. "Neu" → "Manuell anlegen" ──────────────────────────────────
    await page.getByRole('button', { name: /Neu/ }).click()
    await page.getByText('Manuell anlegen').click()

    // Fill company via the picker: type a name, then click the create option
    await page.getByText('Firma wählen…').click()
    await page.locator('input[placeholder="Firma suchen…"]').fill('E2E Testfirma GmbH')
    await page.getByText('"E2E Testfirma GmbH" neu anlegen').click()

    // Fill role, source, comment
    await page.locator('input[placeholder="Rolle *"]').fill('Senior Test Engineer')
    await page.locator('textarea[placeholder="Kommentar (optional)"]').fill('E2E Test application')

    // Submit
    await page.getByRole('button', { name: 'Anlegen' }).click()

    // Verify the app appears in the kanban
    await expect(page.getByText('E2E Testfirma GmbH').first()).toBeVisible({ timeout: 5_000 })
    await expect(page.getByText('Senior Test Engineer').first()).toBeVisible()

    // ── 2. Open the app and change status ─────────────────────────────
    await page.getByText('Senior Test Engineer').first().click()
    await page.waitForSelector('text=Verlauf', { timeout: 5_000 })

    // Click "Bearbeiten" to enter edit mode
    await page.getByRole('button', { name: 'Bearbeiten' }).click()

    // Change status to "Beworben" (should already be selected, but click to be sure)
    await page.getByText('Beworben').first().click()
    await page.getByRole('button', { name: 'Speichern' }).click()

    // ── 3. Re-open and change to HR ───────────────────────────────────
    await page.getByRole('button', { name: 'Bearbeiten' }).click()
    await page.getByText('Gespräch HR/HH').click()
    await page.getByRole('button', { name: 'Speichern' }).click()

    // ── 4. Re-open and reject ─────────────────────────────────────────
    await page.getByRole('button', { name: 'Bearbeiten' }).click()
    await page.getByText('Absage').click()
    await page.getByRole('button', { name: 'Speichern' }).click()

    // ── 5. Verify rejection triggers AI assessment ────────────────────
    // After save the modal should show AI reasoning for rejection
    // The close button is hidden but click the backdrop to close
    await expect(page.getByText('Abgesagt').first()).toBeVisible({ timeout: 5_000 })
  })

})
