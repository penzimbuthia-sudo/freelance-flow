import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

test('persisted request journey, validation, AI failure, editing, copying, and client page', async ({ page, context }) => {
  const consoleErrors = []
  const failedRequests = []
  const unexpectedResponses = []
  page.on('pageerror', (error) => consoleErrors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error' && !/status of (400|503)/.test(message.text())) consoleErrors.push(message.text())
  })
  page.on('requestfailed', (request) => failedRequests.push(request.url()))
  page.on('response', (response) => {
    if (response.status() >= 400 && !(
      (response.status() === 400 && response.url().endsWith('/api/requests')) ||
      (response.status() === 503 && /\/api\/requests\/\d+\/message$/.test(response.url()))
    )) unexpectedResponses.push(`${response.status()} ${response.url()}`)
  })
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Your money, in view.' })).toBeVisible()
  await page.getByRole('link', { name: 'New Payment Request', exact: true }).first().click()
  await page.getByLabel('Client name', { exact: true }).fill('Browser Demo Client')
  await page.getByLabel('Service description', { exact: true }).fill('Fictional browser-tested website design')
  await page.getByLabel('Amount (USD)', { exact: true }).fill('0')
  await page.getByLabel('Due date', { exact: true }).fill('2030-11-12')
  await page.getByRole('button', { name: 'Create payment request' }).click()
  await expect(page.getByRole('alert')).toContainText('between $0.01')
  await page.getByLabel('Amount (USD)', { exact: true }).fill('123.45')
  await page.getByRole('button', { name: 'Create payment request' }).click()
  await expect(page.getByRole('heading', { name: 'Browser Demo Client', exact: true })).toBeVisible()
  const detailsUrl = page.url()
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Browser Demo Client', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Generate payment message' }).click()
  await expect(page.getByRole('alert')).toContainText('GOOGLE_API_KEY')
  await expect(page.getByText('Real Gemini output', { exact: false })).toHaveCount(0)
  await page.getByLabel('Review and edit your message').fill('Manual browser-test draft. Please review USD 123.45.')
  await page.getByRole('button', { name: 'Copy message', exact: true }).click()
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toContain('Manual browser-test draft')
  const paymentUrl = await page.getByLabel('Client payment URL').inputValue()
  await page.getByRole('button', { name: 'Copy link', exact: true }).click()
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe(paymentUrl)

  // Deliberately intercepted and visibly labelled test fixture; never a fallback in the app.
  await page.route('**/api/requests/*/message', (route) => route.fulfill({
    json: { message: 'EXPLICIT TEST FIXTURE: Please review USD 123.45.', source: 'test-fixture', model: 'none' },
  }))
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Clear draft' }).click()
  await page.getByRole('button', { name: 'Generate payment message' }).click()
  await expect(page.getByText('Explicit test fixture · not real AI output', { exact: false })).toBeVisible()
  await expect(page.getByLabel('Review and edit your message')).toHaveValue('EXPLICIT TEST FIXTURE: Please review USD 123.45.')
  await page.unroute('**/api/requests/*/message')

  await page.getByRole('link', { name: 'Payment requests', exact: true }).first().click()
  await page.getByLabel('Search requests').fill('Browser Demo Client')
  await expect(page.getByRole('link', { name: 'Browser Demo Client', exact: true })).toBeVisible()
  await page.getByLabel('Status', { exact: true }).selectOption('paid')
  await expect(page.getByRole('heading', { name: 'No matching requests' })).toBeVisible()
  await page.getByLabel('Status', { exact: true }).selectOption('pending')
  await expect(page.getByRole('link', { name: 'Browser Demo Client', exact: true })).toBeVisible()
  await page.goto(paymentUrl)
  await expect(page.getByRole('heading', { name: 'Your payment request', exact: true })).toBeVisible()
  await expect(page.getByText('Sandbox checkout is not configured yet.', { exact: false })).toBeVisible()
  await expect(page.getByText('Browser Demo Client', { exact: true })).toHaveCount(0)
  await expect(page.getByRole('navigation')).toHaveCount(0)
  await expect(page.getByText('Payment confirmed', { exact: true })).toHaveCount(0)

  for (const width of [375, 768, 1440]) {
    await page.setViewportSize({ width, height: 950 })
    for (const [name, url] of [['dashboard', '/'], ['requests', '/requests'], ['new', '/requests/new'], ['details', detailsUrl], ['client', paymentUrl]]) {
      await page.goto(url)
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      await expect(page.getByRole('status').filter({ hasText: 'Loading saved records' })).toHaveCount(0)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `${name} at ${width}px must not overflow the viewport`).toBe(true)
      const accessibility = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()
      expect(accessibility.violations, `${name} at ${width}px`).toEqual([])
      await page.screenshot({ path: test.info().outputPath(`${name}-${width}.png`), fullPage: true })
    }
  }
  expect(consoleErrors).toEqual([])
  expect(failedRequests).toEqual([])
  expect(unexpectedResponses).toEqual([])
})

test('keyboard navigation exposes skip link and visible focus', async ({ page }) => {
  await page.goto('/')
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('main')).toBeFocused()
})
