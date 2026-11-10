import { test, expect, chromium } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { fileURLToPath } from 'node:url'
import { writeFile } from 'node:fs/promises'
import { Buffer } from 'node:buffer'

const extensionPath = fileURLToPath(new URL('./support/zoom-extension/', import.meta.url))
const longName = 'Alexandria O’Demo with a deliberately long client name for responsive typography verification and wrapping checks'
const longService = `${'Fictional design and accessibility review, with detailed delivery notes for this typography fixture. '.repeat(9)}End of typography service.`
const longDraft = `${'Editable draft fixture, not real AI output. Please review every detail before sharing.\n\n'.repeat(50)}End of editable draft.`

async function setBrowserZoom(worker, page, zoom, width) {
  const actual = await worker.evaluate(async ({ url, zoom }) => {
    const tabs = await globalThis.chrome.tabs.query({})
    const tab = tabs.find((tab) => tab.url === url)
    await globalThis.chrome.tabs.setZoomSettings(tab.id, { mode: 'automatic', scope: 'per-tab' })
    await globalThis.chrome.tabs.setZoom(tab.id, zoom)
    return globalThis.chrome.tabs.getZoom(tab.id)
  }, { url: page.url(), zoom })
  expect(actual).toBe(zoom)
  await page.waitForFunction(({ zoom, width }) => Math.abs(devicePixelRatio - zoom) < .01 && Math.abs(innerWidth - width / zoom) <= 1, { zoom, width })
}

async function inspectTypography(page, cdp) {
  const fonts = await page.evaluate(async () => {
    await Promise.all([400, 500, 600, 700].map((weight) => document.fonts.load(`${weight} 16px Inter`)))
    await document.fonts.ready
    return [...document.fonts].map((font) => ({ family: font.family, weight: font.weight, style: font.style, display: font.display, status: font.status }))
  })
  expect(fonts.map((font) => font.weight).sort()).toEqual(['400', '500', '600', '700'])
  expect(fonts.every((font) => font.family === 'Inter' && font.style === 'normal' && font.display === 'swap' && font.status === 'loaded')).toBe(true)
  const problems = await page.evaluate(() => {
    const problems = []
    for (const element of document.querySelectorAll('h1,h2,h3,p,small,label,button,input,textarea,select,dt,dd,td,th,time,.sandbox-label,.status,.stat-value')) {
      if (!element.getClientRects().length) continue
      const style = getComputedStyle(element)
      if (!style.fontFamily.startsWith('Inter')) problems.push(`${element.tagName}: wrong family`)
      if (parseFloat(style.fontSize) < 14) problems.push(`${element.tagName}: smaller than 14px`)
      if (!['400', '500', '600', '700'].includes(style.fontWeight)) problems.push(`${element.tagName}: unsupported weight`)
      if (style.letterSpacing !== 'normal' && parseFloat(style.letterSpacing) < 0) problems.push(`${element.tagName}: tight spacing`)
      if (element.tagName === 'H1' && (parseFloat(style.fontSize) < 28 || parseFloat(style.fontSize) > 32 || style.fontWeight !== '600')) problems.push('Wrong page heading scale')
      if (['H2', 'H3'].includes(element.tagName) && (parseFloat(style.fontSize) < 18 || parseFloat(style.fontSize) > 20 || style.fontWeight !== '600')) problems.push('Wrong section heading scale')
      if (['BUTTON', 'LABEL'].includes(element.tagName) && (parseFloat(style.fontSize) > 16 || style.fontWeight !== '500')) problems.push('Wrong control scale')
    }
    return problems
  })
  expect(problems).toEqual([])
  // Prove the downloaded font actually rendered glyphs, not just a CSS family name.
  const { root } = await cdp.send('DOM.getDocument')
  const { nodeId } = await cdp.send('DOM.querySelector', { nodeId: root.nodeId, selector: 'h1' })
  const rendered = await cdp.send('CSS.getPlatformFontsForNode', { nodeId })
  expect(rendered.fonts.some((font) => font.postScriptName.startsWith('Inter-') && font.isCustomFont && font.glyphCount > 0), JSON.stringify(rendered.fonts)).toBe(true)
}

async function expectReflow(page) {
  const layout = await page.evaluate(() => {
    const overflow = [...document.querySelectorAll('.page-heading,.card-heading,.ai-panel,.client-main,.confirm-dialog[open]')]
      .filter((element) => { const bounds = element.getBoundingClientRect(); return bounds.width && (bounds.left < -1 || bounds.right > innerWidth + 1) })
      .map((element) => element.className)
    return { width: innerWidth, scrollWidth: document.documentElement.scrollWidth, overflow }
  })
  expect(layout.scrollWidth).toBeLessThanOrEqual(layout.width + 1)
  expect(layout.overflow).toEqual([])
}

async function captureZoomedPage(page, cdp, path) {
  await page.evaluate(() => scrollTo(0, 0))
  // Chromium's DIP metrics include native browser zoom. A CSS-sized full-page
  // clip would crop a 200% screenshot to half its actual viewport width.
  const { contentSize, layoutViewport } = await cdp.send('Page.getLayoutMetrics')
  const { data } = await cdp.send('Page.captureScreenshot', {
    format: 'png', captureBeyondViewport: true,
    clip: { x: 0, y: 0, width: layoutViewport.clientWidth, height: contentSize.height, scale: 1 },
  })
  const png = Buffer.from(data, 'base64')
  expect(png.readUInt32BE(16)).toBe(page.viewportSize().width)
  await writeFile(path, png)
}

for (const width of [375, 1440]) {
  test(`Inter and long content reflow at ${width}px with genuine 100% and 200% browser zoom`, async ({ request }, testInfo) => {
    test.setTimeout(180_000)
    // Set up only isolated, fictional records using the existing mocked provider harness.
    await request.post('/__test__/services', { data: { enabled: true } })
    let paid, unpaid
    try {
      await request.put('/api/settings', { data: { freelancer_display_name: 'Typography Fixture Freelancer' } })
      const create = async () => {
        const response = await request.post('/api/requests', { data: { client_name: longName, service_description: longService, amount: '999999.99', due_date: '2030-01-01' } })
        expect(response.status()).toBe(201)
        return (await response.json()).request
      }
      paid = await create()
      unpaid = await create()
      const path = `/api/public/requests/${new URL(paid.payment_url).pathname.split('/').pop()}`
      const { order_id: orderId } = await (await request.post(`${path}/orders`)).json()
      await request.post('/__test__/approve', { data: { order_id: orderId } })
      expect((await request.post(`${path}/capture`, { data: { order_id: orderId } })).status()).toBe(200)
    } finally {
      await request.post('/__test__/services', { data: { enabled: false } })
    }

    const context = await chromium.launchPersistentContext(testInfo.outputPath('browser-profile'), {
      channel: 'chromium', headless: true, baseURL: testInfo.project.use.baseURL,
      viewport: { width, height: 950 }, deviceScaleFactor: 1,
      args: [`--disable-extensions-except=${extensionPath}`, `--load-extension=${extensionPath}`],
    })
    try {
      const worker = context.serviceWorkers()[0] || await context.waitForEvent('serviceworker')
      const page = context.pages()[0]
      const cdp = await context.newCDPSession(page)
      await cdp.send('DOM.enable')
      await cdp.send('CSS.enable')
      const errors = []
      const fontResponses = []
      const mutations = []
      page.on('pageerror', (error) => errors.push(error.message))
      page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()) })
      page.on('response', (response) => {
        if (/\.woff2?$/.test(new URL(response.url()).pathname)) fontResponses.push({ status: response.status(), host: new URL(response.url()).hostname })
      })
      page.on('request', (request) => { if (request.method() !== 'GET') mutations.push(request.method()) })
      await context.route('**/*', (route) => ['localhost', '127.0.0.1'].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort())
      await page.route('**/api/requests/*', async (route) => {
        const response = await route.fetch()
        const data = await response.json()
        data.request.payment_url += `?typography=${'long-url-fixture-'.repeat(80)}`
        await route.fulfill({ response, json: data })
      })
      const views = [
        ['dashboard', '/'], ['requests', '/requests'], ['new-request', '/requests/new'],
        ['details', `/requests/${unpaid.id}`], ['client-payment', new URL(unpaid.payment_url).pathname],
        ['confirmation', new URL(paid.payment_url).pathname],
      ]
      for (const zoom of [1, 2]) {
        for (const [name, url] of views) {
          await page.goto(url)
          await setBrowserZoom(worker, page, zoom, width)
          await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
          await expect(page.getByRole('status').filter({ hasText: 'Loading saved records' })).toHaveCount(0)
          await page.keyboard.press('Tab')
          await expect(page.getByRole('link', { name: 'Skip to content', exact: true })).toBeFocused()
          await page.keyboard.press('Enter')
          await expect(page.getByRole('main')).toBeFocused()
          await expect(page.getByRole('main')).toHaveCSS('outline-width', '3px')
          await inspectTypography(page, cdp)
          await expectReflow(page)
          if (['dashboard', 'requests'].includes(name)) {
            const columns = await page.locator('.amount-cell').evaluateAll((cells) => cells.map((cell) => getComputedStyle(cell).fontVariantNumeric))
            expect(columns.length).toBeGreaterThan(0)
            expect(columns.every((value) => value.includes('tabular-nums'))).toBe(true)
          }
          if (name === 'details') {
            const draft = page.getByLabel('Review and edit your message')
            await draft.fill(longDraft)
            await expect(draft).toHaveCSS('font-size', '16px')
            await expect(draft).toHaveCSS('font-weight', '400')
            await expect(draft).toHaveCSS('line-height', '25.6px')
            await draft.press('Control+End')
            expect(await draft.evaluate((element) => element.selectionStart)).toBe(longDraft.length)
            await page.getByRole('navigation').getByRole('link', { name: 'Payment requests', exact: true }).press('Enter')
            const leaveDialog = page.getByRole('dialog', { name: 'Leave this draft?' })
            const keepEditing = leaveDialog.getByRole('button', { name: 'Keep editing' })
            await expect(keepEditing).toBeFocused()
            await expectReflow(page)
            await expect(leaveDialog).toHaveCSS('font-family', await draft.evaluate((element) => getComputedStyle(element).fontFamily))
            expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([])
            await page.keyboard.press('Escape')
            await expect(draft).toHaveValue(longDraft)
            await expect(draft).toBeFocused()
            const trigger = page.locator('.ai-actions').getByRole('button', { name: 'Clear draft', exact: true })
            await trigger.focus()
            await page.keyboard.press('Enter')
            const dialog = page.getByRole('dialog', { name: 'Clear this draft?' })
            const keep = dialog.getByRole('button', { name: 'Keep draft' })
            const confirm = dialog.getByRole('button', { name: 'Clear draft', exact: true })
            await expect(keep).toBeFocused()
            await expect(dialog).toHaveCSS('font-family', await draft.evaluate((element) => getComputedStyle(element).fontFamily))
            await expectReflow(page)
            await page.keyboard.press('Shift+Tab')
            await expect(confirm).toBeFocused()
            await page.keyboard.press('Tab')
            await expect(keep).toBeFocused()
            await page.keyboard.press('Escape')
            await expect(draft).toHaveValue(longDraft)
            await expect(trigger).toBeFocused()
            await page.keyboard.press('Enter')
            await keep.press('Enter')
            await expect(draft).toHaveValue(longDraft)
            await trigger.press('Enter')
            await page.mouse.click(1, 1)
            await expect(dialog).toHaveCount(0)
            await expect(draft).toHaveValue(longDraft)
            await expect(trigger).toBeFocused()
            await trigger.press('Enter')
            await confirm.press('Enter')
            await expect(draft).toHaveValue('')
            await expect(draft).toBeFocused()
            await expect(trigger).toBeDisabled()
            await draft.fill(longDraft)
          }
          const scan = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()
          expect(scan.violations, `${name} at ${width}px / ${zoom * 100}%`).toEqual([])
          await captureZoomedPage(page, cdp, testInfo.outputPath(`${name}-${width}-${zoom * 100}.png`))
          if (name === 'details') {
            await page.locator('.ai-actions').getByRole('button', { name: 'Clear draft', exact: true }).press('Enter')
            await page.getByRole('dialog', { name: 'Clear this draft?' }).getByRole('button', { name: 'Clear draft', exact: true }).press('Enter')
            await expect(page.getByLabel('Review and edit your message')).toHaveValue('')
          }
          if (name === 'confirmation') {
            await expect(page.locator('.payment-confirmation')).toContainText('End of typography service.')
            await page.emulateMedia({ media: 'print' })
            await expect(page.locator('.payment-confirmation')).toHaveCSS('font-family', await page.locator('body').evaluate((element) => getComputedStyle(element).fontFamily))
            await expect(page.locator('.capture-reference')).toHaveCSS('font-family', await page.locator('body').evaluate((element) => getComputedStyle(element).fontFamily))
            await expect(page.getByRole('button', { name: 'Print confirmation' })).toBeHidden()
            await expect(page.locator('.client-header')).toBeHidden()
            await page.pdf({ path: testInfo.outputPath(`inter-confirmation-${width}-${zoom * 100}.pdf`), format: 'A4', displayHeaderFooter: false })
            await page.emulateMedia({ media: 'screen' })
          }
        }
      }
      expect(fontResponses.length).toBeGreaterThanOrEqual(4)
      expect(fontResponses.every((font) => font.status === 200 && font.host === 'localhost')).toBe(true)
      expect(mutations).toEqual([]) // Typography and clearing must never call Gemini/payment APIs.
      expect(errors).toEqual([])
    } finally {
      await context.close()
    }
  })
}
