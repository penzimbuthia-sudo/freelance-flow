import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

async function createRequest(request, clientName = 'Alex Details Fixture') {
  const response = await request.post('/api/requests', { data: {
    client_name: clientName, service_description: 'Fictional request-details polish service', amount: '1.00', due_date: '2030-11-12',
  } })
  expect(response.status()).toBe(201)
  return (await response.json()).request
}

for (const width of [375, 1440]) {
  test(`compact details, sender editing and exact link/draft copying at ${width}px`, async ({ page, context, request }, testInfo) => {
    await page.setViewportSize({ width, height: 950 })
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    page.on('console', (message) => { if (message.type() === 'error' && !/status of 400/.test(message.text())) errors.push(message.text()) })
    await context.grantPermissions(['clipboard-read', 'clipboard-write'])
    await context.route('**/api/public/config', (route) => route.fulfill({ json: { sandbox: true, paypal_configured: false, paypal_client_id: null } }))
    await request.post('/__test__/services', { data: { enabled: true } })
    try {
      await request.put('/api/settings', { data: { freelancer_display_name: 'Jane Details Fixture' } })
      const item = await createRequest(request)
      const before = await (await request.get(`/api/requests/${item.id}`)).json()
      const completeUrl = `${item.payment_url}?note=${'long-link-fixture-'.repeat(80)}`
      await page.route(`**/api/requests/${item.id}`, async (route) => {
        const response = await route.fetch()
        const data = await response.json()
        data.request.payment_url = completeUrl
        await route.fulfill({ response, json: data })
      })
      let generations = 0
      page.on('request', (request) => { if (request.method() === 'POST' && request.url().endsWith('/message')) generations++ })
      await page.goto(`/requests/${item.id}`)
      const panel = page.getByRole('region', { name: 'Explain this payment' })
      const draft = page.getByLabel('Review and edit your message')
      const edit = panel.getByRole('button', { name: 'Edit', exact: true })
      const nameInput = page.getByLabel('Freelancer display name', { exact: true })
      await expect(panel).toContainText('Understand this request and draft your next message.')
      await expect(panel.getByRole('note', { name: 'Payment facts' })).toContainText('$1.00 is unpaid. Due 12 Nov 2030.')
      await expect(panel).toContainText('Next step: share the payment link.')
      await expect(panel).toContainText('To: Alex Details Fixture')
      await expect(panel.locator('.sender-summary')).toContainText('Sending as Jane Details Fixture')
      await expect(nameInput).toHaveCount(0)
      expect(await panel.innerText()).not.toMatch(/SQLite|approved wording style|facts composed by the app/)
      const textareaBox = await draft.boundingBox()
      expect(textareaBox.height).toBeGreaterThanOrEqual(160)
      expect(textareaBox.height).toBeLessThanOrEqual(200)
      await expect(draft).toHaveCSS('resize', 'vertical')
      if (width === 1440) {
        const left = await page.locator('.details-left').boundingBox()
        const right = await panel.boundingBox()
        expect(right.x).toBeGreaterThan(left.x + left.width)
        expect((await panel.getByRole('button', { name: 'Generate payment message' }).boundingBox()).y).toBeLessThan(850)
      }
      await page.screenshot({ path: testInfo.outputPath(`compact-details-${width}.png`), fullPage: true })

      await edit.click()
      await expect(nameInput).toHaveValue('Jane Details Fixture')
      await expect(nameInput).toBeFocused()
      await nameInput.fill('Cancelled name edit')
      await panel.getByRole('button', { name: 'Cancel', exact: true }).click()
      await expect(panel.locator('.sender-summary')).toContainText('Jane Details Fixture')
      await expect(edit).toBeFocused()
      await edit.click()
      await expect(nameInput).toHaveValue('Jane Details Fixture')
      await nameInput.fill('  Jane Updated Fixture  ')
      let releaseSave
      const saveGate = new Promise((resolve) => { releaseSave = resolve })
      const delaySave = async (route) => {
        if (route.request().method() === 'PUT') await saveGate
        await route.continue()
      }
      await page.route('**/api/settings', delaySave)
      await panel.getByRole('button', { name: 'Save', exact: true }).click()
      await expect(panel.getByRole('button', { name: 'Saving…' })).toBeDisabled()
      await expect(nameInput).toBeDisabled()
      releaseSave()
      await expect(panel.locator('.sender-summary')).toContainText('Jane Updated Fixture')
      await page.unroute('**/api/settings', delaySave)
      expect((await (await request.get('/api/settings')).json()).settings.freelancer_display_name).toBe('Jane Updated Fixture')
      await page.reload()
      await expect(panel.locator('.sender-summary')).toContainText('Jane Updated Fixture')
      await expect(nameInput).toHaveCount(0)

      await panel.getByRole('button', { name: 'Generate payment message' }).click()
      await expect(draft).toHaveValue(/^Hello Alex Details Fixture,[\s\S]*Kind regards,\nJane Updated Fixture$/)
      const edited = 'Edited request-details fixture. These edits must never be overwritten.'
      await draft.fill(edited)
      await edit.click()
      await nameInput.fill('Later Sender Fixture')
      await panel.getByRole('button', { name: 'Save', exact: true }).click()
      await expect(panel.locator('.sender-summary')).toContainText('Later Sender Fixture')
      await expect(draft).toHaveValue(edited)
      await expect(panel).toContainText('Your current draft is unchanged.')
      await edit.click()
      await nameInput.fill('Rejected sender edit')
      const rejectSave = (route) => route.request().method() === 'PUT'
        ? route.fulfill({ status: 400, json: { error: { code: 'validation_error', message: 'Use a single-line sender name.' } } })
        : route.continue()
      await page.route('**/api/settings', rejectSave)
      await panel.getByRole('button', { name: 'Save', exact: true }).click()
      await expect(panel.getByRole('alert')).toContainText('Use a single-line sender name.')
      await expect(nameInput).toHaveValue('Rejected sender edit')
      await expect(draft).toHaveValue(edited)
      await panel.getByRole('button', { name: 'Cancel', exact: true }).click()
      await page.unroute('**/api/settings', rejectSave)
      await expect(panel.locator('.sender-summary')).toContainText('Later Sender Fixture')
      await panel.getByRole('button', { name: 'Copy message', exact: true }).click()
      await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe(edited)

      const linkInput = page.getByLabel('Client payment URL')
      await expect(linkInput).toHaveValue(completeUrl)
      await expect(linkInput).toHaveAttribute('readonly', '')
      await linkInput.focus()
      expect(await linkInput.evaluate((input) => input.selectionEnd - input.selectionStart)).toBe(completeUrl.length)
      await page.getByRole('button', { name: 'Copy link', exact: true }).click()
      await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe(completeUrl)
      await expect(page.getByText('Anyone with this link can view this request’s payment details.', { exact: true })).toHaveCount(1)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      const popupReady = page.waitForEvent('popup')
      await page.getByRole('link', { name: 'Open client page', exact: false }).click()
      const popup = await popupReady
      await expect(popup.getByRole('heading', { name: 'Your payment request', exact: true })).toBeVisible()
      await expect(page.getByRole('dialog', { name: 'Leave this draft?' })).toHaveCount(0)
      await popup.close()
      await expect(draft).toHaveValue(edited)

      const clear = panel.locator('.ai-actions').getByRole('button', { name: 'Clear draft', exact: true })
      await clear.click()
      await page.getByRole('dialog', { name: 'Clear this draft?' }).getByRole('button', { name: 'Keep draft' }).click()
      await expect(draft).toHaveValue(edited)
      await clear.click()
      await page.getByRole('dialog', { name: 'Clear this draft?' }).getByRole('button', { name: 'Clear draft', exact: true }).click()
      await expect(draft).toHaveValue('')
      await expect(draft).toBeFocused()
      await expect(clear).toBeDisabled()
      expect(generations).toBe(1)
      const after = await (await request.get(`/api/requests/${item.id}`)).json()
      expect(after).toEqual(before)
      expect((await (await request.get('/api/settings')).json()).settings.freelancer_display_name).toBe('Later Sender Fixture')
      expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([])
      expect(errors).toEqual([])
    } finally {
      await request.post('/__test__/services', { data: { enabled: false } })
    }
  })
}

test('edited drafts are protected on links and browser history, without unnecessary prompts or generation', async ({ page, context, request }) => {
  const errors = []
  const nativeDialogs = []
  const writes = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()) })
  page.on('dialog', async (dialog) => { nativeDialogs.push(dialog.type()); await dialog.dismiss() })
  await page.addInitScript(() => { window.confirm = undefined; window.alert = undefined })
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await request.put('/api/settings', { data: { freelancer_display_name: 'Navigation Fixture Sender' } })
  const item = await createRequest(request, 'Navigation Fixture Client')
  const before = await (await request.get(`/api/requests/${item.id}`)).json()
  let generations = 0
  await page.route(`**/api/requests/${item.id}/message`, (route) => {
    generations++
    return route.fulfill({ json: { message: 'Unedited generated test fixture.', source: 'test-fixture', model: 'none' } })
  })
  page.on('request', (request) => { if (request.method() !== 'GET') writes.push(new URL(request.url()).pathname) })
  await page.goto('/')
  await page.getByRole('link', { name: 'Navigation Fixture Client', exact: true }).click()
  const draft = page.getByLabel('Review and edit your message')
  const edited = 'My unsent, edited request message.'
  await draft.fill(edited)
  const dialog = page.getByRole('dialog', { name: 'Leave this draft?', exact: true })
  const keep = dialog.getByRole('button', { name: 'Keep editing' })
  const leave = dialog.getByRole('button', { name: 'Leave page' })
  const requestList = page.getByRole('navigation').getByRole('link', { name: 'Payment requests', exact: true })
  const unloadBlocked = () => page.evaluate(() => {
    const event = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(event)
    return event.defaultPrevented
  })
  expect(await unloadBlocked()).toBe(true)
  await requestList.click()
  await expect(dialog).toHaveAccessibleDescription('Your message edits will be lost.')
  await expect(keep).toBeFocused()
  await page.keyboard.press('Shift+Tab')
  await expect(leave).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(keep).toBeFocused()
  expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([])
  await page.keyboard.press('Escape')
  await expect(draft).toHaveValue(edited)
  await expect(draft).toBeFocused()
  await requestList.click()
  await page.mouse.click(4, 4)
  await expect(dialog).toHaveCount(0)
  await expect(draft).toHaveValue(edited)
  await requestList.click()
  await keep.click()
  await expect(draft).toHaveValue(edited)
  // Actual history POP, not a custom link wrapper: the router restores the URL
  // while blocked and replays the requested history traversal only on consent.
  await page.evaluate(() => history.back())
  await expect(dialog).toBeVisible()
  await expect(page).toHaveURL(new RegExp(`/requests/${item.id}$`))
  await keep.click()
  await expect(draft).toHaveValue(edited)
  await page.evaluate(() => history.back())
  await leave.click()
  await expect(page.getByRole('heading', { name: 'Your money, in view.' })).toBeVisible()
  await page.goForward()
  await expect(draft).toHaveValue('')
  await expect(dialog).toHaveCount(0)
  expect(await unloadBlocked()).toBe(false)
  await draft.fill(' \n ')
  await requestList.click()
  await expect(page.getByRole('heading', { name: 'Payment requests', exact: true })).toBeVisible()
  await expect(dialog).toHaveCount(0)
  await page.getByRole('link', { name: 'Navigation Fixture Client', exact: true }).click()
  await page.getByRole('button', { name: 'Generate payment message' }).click()
  await expect(draft).toHaveValue('Unedited generated test fixture.')
  expect(await unloadBlocked()).toBe(false)
  await draft.fill('An edited generated message.')
  await requestList.click()
  await expect(dialog).toBeVisible()
  await keep.click()
  await draft.fill('Unedited generated test fixture.')
  expect(await unloadBlocked()).toBe(false)
  await requestList.click()
  await expect(page.getByRole('heading', { name: 'Payment requests', exact: true })).toBeVisible()
  await page.getByRole('link', { name: 'Navigation Fixture Client', exact: true }).click()
  await draft.fill('Clear intentionally before leaving.')
  await page.locator('.ai-actions').getByRole('button', { name: 'Clear draft', exact: true }).click()
  await page.getByRole('dialog', { name: 'Clear this draft?' }).getByRole('button', { name: 'Clear draft', exact: true }).click()
  expect(await unloadBlocked()).toBe(false)
  await requestList.click()
  await expect(page.getByRole('heading', { name: 'Payment requests', exact: true })).toBeVisible()
  expect(generations).toBe(1)
  expect(writes).toEqual([`/api/requests/${item.id}/message`])
  expect(await (await request.get(`/api/requests/${item.id}`)).json()).toEqual(before)
  expect(nativeDialogs).toEqual([])
  expect(errors).toEqual([])
})

test('compact factual copy reflects canonical payment and attempt state with readable dates', async ({ page, request }) => {
  const item = await createRequest(request, 'Payment Facts Fixture')
  const original = await (await request.get(`/api/requests/${item.id}`)).json()
  let scenario
  await page.route(`**/api/requests/${item.id}`, (route) => route.fulfill({ json: {
    ...original,
    request: { ...original.request, due_date: '2026-11-12', status: scenario.payment_status === 'paid' ? 'paid' : scenario.timing === 'overdue' ? 'overdue' : 'pending' },
    guidance: { ...original.guidance, amount_cents: 100, due_date: '2026-11-12', overdue_days: 0, attempt_outcome: null, ...scenario },
  } }))
  const cases = [
    { payment_status: 'unpaid', timing: 'future', text: '$1.00 is unpaid. Due 12 Nov 2026.', action: 'share the payment link.' },
    { payment_status: 'unpaid', timing: 'today', text: '$1.00 is unpaid. Due today, 12 Nov 2026.', action: 'send a polite due-today message.' },
    { payment_status: 'unpaid', timing: 'overdue', overdue_days: 3, text: '3 calendar days overdue (due 12 Nov 2026).', action: 'send a friendly follow-up.' },
    { payment_status: 'unpaid', timing: 'future', attempt_outcome: 'failed', text: 'The last attempt failed.', action: 'retry checkout using the payment link.' },
    { payment_status: 'unpaid', timing: 'future', attempt_outcome: 'cancelled', text: 'Checkout cancellation reported by the browser.', action: 'retry checkout using the payment link.' },
    { payment_status: 'paid', timing: 'paid', attempt_outcome: 'failed', text: '$1.00 is recorded as paid.', action: 'send a thank-you message.' },
    { payment_status: 'unpaid', timing: 'future', attempt_outcome: 'unconfirmed', text: 'A payment attempt needs verification.', action: 'check payment status before trying again.' },
  ]
  for (const entry of cases) {
    scenario = entry
    await page.goto(`/requests/${item.id}`)
    const facts = page.getByRole('note', { name: 'Payment facts' })
    await expect(facts).toContainText(entry.text)
    await expect(facts).toContainText(`Next step: ${entry.action}`)
    if (entry.payment_status !== 'paid') await expect(facts).toContainText('is unpaid')
    await expect(page.locator('dl > div').filter({ has: page.locator('dt', { hasText: 'Due date' }) }).locator('dd')).toHaveText('12 Nov 2026')
    await expect(page.getByText(/Africa\/Nairobi/)).toHaveCount(1)
    await expect(page.getByRole('heading', { name: 'Payment confirmed', exact: true })).toHaveCount(0)
  }
})
