import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

for (const width of [375, 1440]) {
  test(`clear draft modal preserves edits and manages focus at ${width}px`, async ({ page, context, request }) => {
    await page.setViewportSize({ width, height: 900 })
    const errors = []
    const nativeDialogs = []
    const mutations = []
    page.on('pageerror', (error) => errors.push(error.message))
    page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()) })
    page.on('dialog', async (dialog) => { nativeDialogs.push(dialog.type()); await dialog.dismiss() })
    page.on('request', (request) => {
      if (new URL(request.url()).pathname.startsWith('/api/') && request.method() !== 'GET') mutations.push(request.method())
    })
    // Reproduce the original host limitation: native browser prompts are absent.
    await page.addInitScript(() => { window.confirm = undefined; window.alert = undefined })
    await context.grantPermissions(['clipboard-read', 'clipboard-write'])
    await request.put('/api/settings', { data: { freelancer_display_name: 'Clear Draft Fixture Freelancer' } })
    const create = async (suffix) => {
      const response = await request.post('/api/requests', { data: {
        client_name: `Clear Draft Fixture ${suffix}`, service_description: `Fictional modal regression service ${suffix}`,
        amount: '12.34', due_date: '2030-01-01',
      } })
      expect(response.status()).toBe(201)
      return (await response.json()).request
    }
    const first = await create('A')
    const second = await create('B')
    const before = await (await request.get(`/api/requests/${first.id}`)).json()
    const otherBefore = await (await request.get(`/api/requests/${second.id}`)).json()
    const settingsBefore = await (await request.get('/api/settings')).json()
    let generations = 0
    await page.route(`**/api/requests/${first.id}/message`, async (route) => {
      generations++
      await route.fulfill({ json: { message: 'Explicit generated test fixture. Please review before sharing.', source: 'test-fixture', model: 'none' } })
    })

    await page.goto(`/requests/${first.id}`)
    const panel = page.getByRole('region', { name: 'Explain this payment' })
    const draft = page.getByLabel('Review and edit your message')
    const trigger = panel.locator('.ai-actions').getByRole('button', { name: 'Clear draft', exact: true })
    const dialog = page.getByRole('dialog', { name: 'Clear this draft?', exact: true })
    const keep = dialog.getByRole('button', { name: 'Keep draft', exact: true })
    const confirm = dialog.getByRole('button', { name: 'Clear draft', exact: true })
    await expect(trigger).toBeDisabled()
    await page.getByRole('button', { name: 'Generate payment message' }).click()
    await expect(draft).not.toHaveValue('')
    const edited = 'Edited fixture draft — keep every edit.\n\nSecond paragraph, not sent automatically.'
    await draft.fill(edited)
    const source = await panel.locator('.ai-source').textContent()
    const unsavedName = 'Unsaved freelancer edit'
    await panel.getByRole('button', { name: 'Edit', exact: true }).click()
    await page.getByLabel('Freelancer display name', { exact: true }).fill(unsavedName)
    const explanation = await panel.locator('.payment-explanation').textContent()
    const timeline = await page.getByRole('region', { name: 'Payment activity' }).textContent()
    const previousOverflow = await page.evaluate(() => document.body.style.overflow)

    // A different request's draft in another tab must never be affected.
    const otherPage = await context.newPage()
    await otherPage.goto(`/requests/${second.id}`)
    const otherDraft = otherPage.getByLabel('Review and edit your message')
    await otherDraft.fill('Other request’s untouched draft.')
    await page.bringToFront()

    async function openModal() {
      await trigger.click()
      await expect(dialog).toBeVisible()
      await expect(dialog).toHaveAttribute('aria-modal', 'true')
      await expect(dialog).toHaveAccessibleDescription('This will remove your current message, including any edits.')
      await expect(keep).toBeFocused()
      expect(await page.evaluate(() => document.body.style.overflow)).toBe('hidden')
      const bounds = await dialog.boundingBox()
      expect(bounds.x).toBeGreaterThanOrEqual(0)
      expect(bounds.x + bounds.width).toBeLessThanOrEqual(width)
    }

    async function expectPreserved() {
      await expect(dialog).toHaveCount(0)
      await expect(trigger).toBeFocused()
      await expect(draft).toHaveValue(edited)
      await expect(panel.locator('.ai-source')).toHaveText(source)
      await expect(page.getByLabel('Freelancer display name', { exact: true })).toHaveValue(unsavedName)
      expect(await page.evaluate(() => document.body.style.overflow)).toBe(previousOverflow)
    }

    await openModal()
    // Both directions wrap within the two modal buttons; background is inert.
    await page.keyboard.press('Shift+Tab')
    await expect(confirm).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(keep).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(confirm).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(keep).toBeFocused()
    expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([])
    await keep.click()
    await expectPreserved()

    await openModal()
    await page.keyboard.press('Escape')
    await expectPreserved()

    await openModal()
    await page.mouse.click(4, 4)
    await expectPreserved()

    await openModal()
    const bounds = await dialog.boundingBox()
    await page.mouse.click(bounds.x + 4, bounds.y + 4) // Inside padding is not the backdrop.
    await expect(dialog).toBeVisible()
    await expect(draft).toHaveValue(edited)
    await page.screenshot({ path: test.info().outputPath(`clear-dialog-${width}.png`) })
    await confirm.click()
    await expect(dialog).toHaveCount(0)
    await expect(draft).toHaveValue('')
    await expect(draft).toBeFocused()
    await expect(trigger).toBeDisabled()
    await expect(page.getByRole('button', { name: 'Copy message', exact: true })).toBeDisabled()
    await expect(panel.locator('.ai-source')).toHaveCount(0)
    await expect(page.getByLabel('Freelancer display name', { exact: true })).toHaveValue(unsavedName)
    expect(await panel.locator('.payment-explanation').textContent()).toBe(explanation)
    expect(await page.getByRole('region', { name: 'Payment activity' }).textContent()).toBe(timeline)
    expect(await page.evaluate(() => document.body.style.overflow)).toBe(previousOverflow)
    await expect(otherDraft).toHaveValue('Other request’s untouched draft.')
    expect(await (await request.get(`/api/requests/${first.id}`)).json()).toEqual(before)
    expect(await (await request.get(`/api/requests/${second.id}`)).json()).toEqual(otherBefore)
    expect(await (await request.get('/api/settings')).json()).toEqual(settingsBefore)
    expect(generations).toBe(1)
    expect(mutations).toEqual(['POST']) // Explicit generation only: clearing never writes/calls Gemini.
    expect(nativeDialogs).toEqual([])
    expect(errors).toEqual([])
    await otherPage.close()
  })
}
