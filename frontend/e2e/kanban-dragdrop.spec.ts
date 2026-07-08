import { test, expect, type Page } from './fixtures'

const COMPANY = 'Kanban DnD GmbH'
const ROLE = 'Drag & Drop Engineer'

async function createApplication(page: Page) {
  await page.getByRole('button', { name: /Neu/ }).click()
  await page.getByText('Manuell anlegen').click()
  await page.getByText('Firma wählen…').click()
  await page.locator('input[placeholder="Firma suchen…"]').fill(COMPANY)
  await page.getByText(`"${COMPANY}" neu anlegen`).click()
  await page.locator('input[placeholder="Rolle *"]').fill(ROLE)
  await page.getByRole('button', { name: 'Anlegen', exact: true }).click()
  await expect(page.getByText(COMPANY).first()).toBeVisible({ timeout: 5_000 })
}

async function dragToColumn(page: Page, sourceText: string, targetLabel: string) {
  const source = page.getByText(sourceText).first()
  const sourceBox = await source.boundingBox()
  const targetBadge = page.getByText(targetLabel).first()
  const targetColumn = targetBadge.locator('..').locator('..')
  const targetBox = await targetColumn.boundingBox()
  if (!sourceBox || !targetBox) throw new Error('Bounding box not found')

  const sx = sourceBox.x + sourceBox.width / 2
  const sy = sourceBox.y + sourceBox.height / 2
  const tx = targetBox.x + targetBox.width / 2
  const ty = targetBox.y + targetBox.height - 20

  await page.mouse.move(sx, sy)
  await page.mouse.down()
  const steps = 15
  for (let i = 1; i <= steps; i++) {
    await page.mouse.move(
      sx + (tx - sx) * (i / steps),
      sy + (ty - sy) * (i / steps),
    )
  }
  await page.mouse.up()
}

test.describe('Kanban Drag & Drop (Journey 2)', () => {

  test.beforeEach(async ({ page, authToken }) => {
    await page.goto('/')
    await page.waitForSelector('text=Anbahnung', { timeout: 15_000 })
  })

  test('drag between columns changes status and resets sub_status on non-HR/FB move', async ({ page }) => {
    // ── 1. Create application (defaults to "Beworben" / applied) ──────────
    await createApplication(page)

    // ── 2. Switch to Kanban view ──────────────────────────────────────────
    await page.getByRole('button', { name: '▦ Kanban' }).click()
    await page.waitForSelector('text=Anbahnung', { timeout: 5_000 })

    // ── 3. Drag from "Beworben" → "Gespräch HR/HH" ───────────────────────
    await expect(page.getByText(ROLE).first()).toBeVisible()
    await dragToColumn(page, ROLE, 'Gespräch HR/HH')
    await expect(page.getByText(ROLE).first()).toBeVisible({ timeout: 5_000 })

    // ── 4. Verify status changed to "Gespräch HR/HH" via modal ───────────
    await page.getByText(ROLE).first().click()
    await page.waitForSelector('text=Verlauf', { timeout: 5_000 })
    await expect(page.getByText('Gespräch HR/HH').first()).toBeVisible()
    // Close modal by clicking the backdrop
    await page.keyboard.press('Escape')
    await page.waitForTimeout(500)

    // ── 5. Set sub_status via edit modal, then close ──────────────────────
    await page.getByText(ROLE).first().click()
    await page.waitForSelector('text=Verlauf', { timeout: 5_000 })
    await page.getByRole('button', { name: 'Bearbeiten' }).click()
    await page.getByText('1. Gespräch terminiert').click()
    await page.getByRole('button', { name: 'Speichern' }).click()
    await expect(page.getByText('1. Gespräch terminiert').first()).toBeVisible({ timeout: 5_000 })
    await page.keyboard.press('Escape')
    await page.waitForTimeout(500)

    // ── 6. Drag from "Gespräch HR/HH" → "Angebotsverhandlung" (non-HR/FB → sub_status cleared) ──
    await dragToColumn(page, ROLE, 'Angebotsverhandlung')
    await expect(page.getByText(ROLE).first()).toBeVisible({ timeout: 5_000 })

    // ── 7. Verify sub_status was reset (no sub_status label visible) ─────
    await page.getByText(ROLE).first().click()
    await page.waitForSelector('text=Verlauf', { timeout: 5_000 })
    // Should show the new main status
    await expect(page.getByText('Angebotsverhandlung').first()).toBeVisible()
    // sub_status label should NOT be visible in the modal
    await expect(page.getByText('1. Gespräch terminiert')).not.toBeVisible()
  })

})
