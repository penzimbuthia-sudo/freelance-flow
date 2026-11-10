import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

test('context guidance, persisted activity, verified confirmation and print — mocked providers', async ({ page, context, request }) => {
  const externalHosts = []
  const pageErrors = []
  const consoleErrors = []
  page.on('pageerror', (error) => pageErrors.push(error.name))
  page.on('console', (message) => {
    if (message.type() === 'error' && !/status of (502|404)/.test(message.text())) consoleErrors.push(message.text())
  })
  await context.route('**/*', async (route) => {
    const url = new URL(route.request().url())
    if (!['localhost', '127.0.0.1'].includes(url.hostname)) {
      externalHosts.push(url.hostname)
      await route.abort()
    } else await route.continue()
  })
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await request.post('/__test__/services', { data: { enabled: true } })
  try {
    const { today } = await (await request.get('/api/health')).json()
    await request.put('/api/settings', { data: { freelancer_display_name: 'Enhancement Fixture Freelancer' } })
    const created = await request.post('/api/requests', { data: {
      client_name: 'Enhancement Fixture Client', service_description: 'Explicit browser fixture — fictional design service', amount: '42.35', due_date: today,
    } })
    const { request: item } = await created.json()
    const detailsUrl = `/requests/${item.id}`
    const publicPath = new URL(item.payment_url).pathname
    const apiPath = `/api/public/requests/${publicPath.split('/').pop()}`
    await page.goto(detailsUrl)
    const explanation = page.getByRole('region', { name: 'Explain this payment' })
    const activity = page.getByRole('region', { name: 'Payment activity' })
    await expect(explanation).toContainText('due today')
    await expect(explanation).toContainText('USD 42.35')
    await expect(page.getByRole('button', { name: 'Print confirmation' })).toHaveCount(0)
    await page.getByRole('button', { name: 'Generate payment message' }).click()
    await expect(explanation.getByText('Explicit test fixture · not real AI output', { exact: false })).toBeVisible()
    const draft = page.getByLabel('Review and edit your message')
    await expect(draft).toHaveValue(/Hello Enhancement Fixture Client,[\s\S]*USD 42.35[\s\S]*Kind regards,\nEnhancement Fixture Freelancer$/)
    const edited = 'Edited explicit test fixture. Please review this fictional payment request.'
    await draft.fill(edited)
    await page.getByRole('button', { name: 'Copy message', exact: true }).click()
    await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe(edited)

    await page.getByRole('button', { name: 'Clear draft' }).click()
    await page.getByRole('dialog', { name: 'Clear this draft?' }).getByRole('button', { name: 'Clear draft', exact: true }).click()
    await request.post('/__test__/ai', { data: { mode: 'error' } })
    await page.getByRole('button', { name: 'Generate payment message' }).click()
    await expect(page.getByRole('alert')).toContainText('Gemini could not generate')
    await expect(explanation).toContainText('due today')
    await expect(draft).toHaveValue('')
    await request.post('/__test__/ai', { data: { mode: 'malformed' } })
    await page.getByRole('button', { name: 'Try again', exact: true }).click()
    await expect(page.getByRole('alert')).toContainText('invalid guidance choice')
    await request.post('/__test__/ai', { data: { mode: 'empty' } })
    await page.getByRole('button', { name: 'Try again', exact: true }).click()
    await expect(page.getByRole('alert')).toContainText('returned no message')
    await request.post('/__test__/ai', { data: { mode: 'success' } })
    await page.getByRole('button', { name: 'Try again', exact: true }).click()
    await expect(draft).not.toHaveValue('')

    await page.setViewportSize({ width: 375, height: 950 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([])
    await page.evaluate(() => document.activeElement?.blur())
    await page.screenshot({ path: test.info().outputPath('guidance-mobile.png'), fullPage: true })

    const orderResponse = await request.post(`${apiPath}/orders`)
    expect(orderResponse.status()).toBe(201)
    const { order_id: orderId } = await orderResponse.json()
    for (let i = 0; i < 2; i++) await request.post(`${apiPath}/cancel`, { data: { order_id: orderId } })
    await page.reload()
    await expect(activity.getByText('Request created', { exact: true })).toHaveCount(1)
    await expect(activity.getByText('PayPal sandbox order created', { exact: true })).toHaveCount(1)
    await expect(activity.getByText('Checkout cancellation reported by browser', { exact: true })).toHaveCount(1)
    await expect(explanation).toContainText('remains unpaid')
    await expect(page.getByRole('button', { name: 'Print confirmation' })).toHaveCount(0)
    // Keep an unpaid draft open while canonical server state changes.
    await page.getByRole('button', { name: 'Generate payment message' }).click()
    await expect(draft).not.toHaveValue('')
    await request.post('/__test__/approve', { data: { order_id: orderId } })
    const capture = await request.post(`${apiPath}/capture`, { data: { order_id: orderId } })
    expect(capture.status()).toBe(200)
    const { capture_id: captureId } = await capture.json()
    await request.post(`${apiPath}/capture`, { data: { order_id: orderId } })
    await request.post(`${apiPath}/cancel`, { data: { order_id: orderId } })
    await page.getByRole('button', { name: 'Refresh status' }).click()
    await expect(page.getByRole('heading', { name: 'Payment confirmed', exact: true })).toBeVisible()
    await expect(explanation).toContainText('recorded as paid')
    await expect(explanation).toContainText('Payment status changed since this draft')
    await expect(page.getByRole('button', { name: 'Copy message', exact: true })).toBeDisabled()
    await page.getByRole('button', { name: 'Clear draft' }).click()
    await page.getByRole('dialog', { name: 'Clear this draft?' }).getByRole('button', { name: 'Clear draft', exact: true }).click()
    await page.getByRole('button', { name: 'Generate thank-you message' }).click()
    await expect(draft).toHaveValue(/Thank you[\s\S]*USD 42.35/)
    expect(await draft.inputValue()).not.toMatch(/unpaid|overdue|payment link/)
    await expect(activity.getByText('Payment confirmed', { exact: true })).toHaveCount(1)
    await page.reload()
    await expect(activity.getByText('Payment confirmed', { exact: true })).toHaveCount(1)
    expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([])

    await page.evaluate(() => { window.printCalls = 0; window.print = () => { window.printCalls++ } })
    await page.getByRole('button', { name: 'Print confirmation' }).click()
    expect(await page.evaluate(() => window.printCalls)).toBe(1)
    await page.emulateMedia({ media: 'print' })
    for (const selector of ['html', 'body', '#root']) {
      expect(await page.locator(selector).evaluate((element) => getComputedStyle(element).backgroundColor)).toBe('rgb(255, 255, 255)')
    }
    await expect(page.getByRole('region', { name: 'Sandbox payment confirmation' })).toBeVisible()
    await expect(page.locator('.sidebar')).toBeHidden()
    await expect(explanation).toBeHidden()
    await expect(page.getByRole('button', { name: 'Print confirmation' })).toBeHidden()
    const pdf = await page.pdf({ path: test.info().outputPath('management-confirmation.pdf'), format: 'A4', printBackground: true, displayHeaderFooter: false })
    expect(pdf.subarray(0, 4).toString()).toBe('%PDF')
    expect((pdf.toString('latin1').match(/\/Type \/Page\b/g) || []).length).toBe(1)
    await page.screenshot({ path: test.info().outputPath('confirmation-print-preview.png'), fullPage: true })
    await page.emulateMedia({ media: 'screen' })

    await page.goto(publicPath)
    const confirmation = page.getByRole('region', { name: 'Sandbox payment confirmation' })
    await expect(confirmation).toContainText('$42.35 USD')
    await expect(confirmation).toContainText('Enhancement Fixture Freelancer')
    await expect(confirmation).toContainText(captureId)
    await expect(confirmation).toContainText('Sandbox · Test payment only')
    await expect(page.getByRole('navigation')).toHaveCount(0)
    await expect(page.getByText('Enhancement Fixture Client', { exact: true })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Check payment status' })).toHaveCount(0)
    for (const width of [375, 1440]) {
      await page.setViewportSize({ width, height: 950 })
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
      expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([])
      await page.evaluate(() => document.activeElement?.blur())
      await page.screenshot({ path: test.info().outputPath(`confirmation-${width}.png`), fullPage: true })
    }
    await page.emulateMedia({ media: 'print' })
    await expect(page.locator('.client-header')).toBeHidden()
    await expect(confirmation).toBeVisible()
    const publicPdf = await page.pdf({ path: test.info().outputPath('public-confirmation.pdf'), format: 'A4', displayHeaderFooter: false })
    expect((publicPdf.toString('latin1').match(/\/Type \/Page\b/g) || []).length).toBe(1)
    await page.emulateMedia({ media: 'screen' })
    // A paid flag without the server's capture evidence is not a confirmation.
    await page.route('**/api/public/requests/*', async (route) => {
      const response = await route.fetch()
      const data = await response.json()
      data.request.confirmation = null
      await route.fulfill({ response, json: data })
    })
    await page.reload()
    await expect(page.getByRole('heading', { name: 'Your payment record', exact: true })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Payment confirmed', exact: true })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Print confirmation' })).toHaveCount(0)
    await expect(page.getByText('SERVER-VERIFIED PAYMENT DETAILS', { exact: true })).toHaveCount(0)
    await page.unroute('**/api/public/requests/*')
    await page.goto('/pay/invalid-token?success=true')
    await expect(page.getByRole('alert')).toContainText('Payment request not found')
    await expect(page.getByRole('heading', { name: 'Payment confirmed', exact: true })).toHaveCount(0)
    expect(externalHosts).toEqual([])
    expect(pageErrors).toEqual([])
    expect(consoleErrors).toEqual([])
  } finally {
    await request.post('/__test__/services', { data: { enabled: false } })
  }
})
