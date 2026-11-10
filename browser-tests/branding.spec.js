import { test, expect } from '@playwright/test'
import { writeFile } from 'node:fs/promises'
import { Buffer } from 'node:buffer'

for (const width of [375, 1440]) {
  test(`local FF branding and small favicon rendering at ${width}px`, async ({ page, request }, testInfo) => {
    await page.setViewportSize({ width, height: 950 })
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()) })
    await page.goto('/')
    const mark = page.locator('.sidebar img.brand-mark')
    await expect(mark).toBeVisible()
    await expect(mark).toHaveAttribute('src', '/brand-mark.svg')
    await expect(mark).toHaveAttribute('alt', '')
    await expect(page.getByRole('link', { name: 'Freelance Flow home', exact: true })).toHaveAttribute('href', '/')
    await expect(page.locator('.brand')).toContainText('Freelance Flow')
    await page.evaluate(() => document.fonts.ready)
    expect(await page.locator('.brand').evaluate((element) => getComputedStyle(element).fontFamily.startsWith('Inter'))).toBe(true)
    expect(await mark.evaluate((image) => image.complete && image.naturalWidth === 64 && image.naturalHeight === 64)).toBe(true)
    const box = await mark.boundingBox()
    expect(box.width).toBe(36)
    expect(box.height).toBe(36)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.locator('.brand').screenshot({ path: testInfo.outputPath(`sidebar-brand-${width}.png`) })

    const favicon = page.locator('head link[rel="icon"]')
    await expect(favicon).toHaveAttribute('href', '/brand-mark.svg')
    await expect(favicon).toHaveAttribute('type', 'image/svg+xml')
    await expect(favicon).toHaveAttribute('sizes', 'any')
    const asset = await request.get('/brand-mark.svg')
    expect(asset.status()).toBe(200)
    expect(asset.headers()['content-type']).toContain('image/svg+xml')
    const svg = await asset.text()
    expect(svg).toContain('Freelance Flow FF monogram')
    expect(svg).not.toMatch(/<text\b|<image\b|<script\b|foreignObject|@import/)
    expect(svg).toContain('#0F2D5B')
    expect(svg).toContain('#2563EB')

    const rendered = await page.evaluate(async () => {
      const image = new Image()
      image.src = '/brand-mark.svg'
      await image.decode()
      const icons = []
      for (const size of [16, 24, 32]) {
        const canvas = document.createElement('canvas')
        canvas.width = canvas.height = size
        const context = canvas.getContext('2d')
        context.drawImage(image, 0, 0, size, size)
        const pixels = context.getImageData(0, 0, size, size).data
        const white = new Set()
        for (let i = 0; i < size * size; i++) {
          if (pixels[i * 4] > 240 && pixels[i * 4 + 1] > 240 && pixels[i * 4 + 2] > 240 && pixels[i * 4 + 3] > 240) white.add(i)
        }
        const count = white.size
        let components = 0
        while (white.size) {
          components++
          const start = white.values().next().value
          const stack = [start]
          white.delete(start)
          while (stack.length) {
            const index = stack.pop()
            const x = index % size
            for (const next of [x ? index - 1 : -1, x < size - 1 ? index + 1 : -1, index - size, index + size]) {
              if (white.delete(next)) stack.push(next)
            }
          }
        }
        icons.push({ size, components, whitePixels: count, png: canvas.toDataURL('image/png').split(',')[1] })
      }
      const preview = document.createElement('canvas')
      preview.width = 360
      preview.height = 160
      const context = preview.getContext('2d')
      context.fillStyle = '#FFFFFF'
      context.fillRect(0, 0, 360, 80)
      context.fillStyle = '#0F2D5B'
      context.fillRect(0, 80, 360, 80)
      context.font = '500 14px Inter'
      for (const [index, size] of [16, 24, 32].entries()) {
        for (const row of [0, 1]) {
          context.drawImage(image, 20 + index * 118, 20 + row * 80, size, size)
          context.fillStyle = row ? '#FFFFFF' : '#0F2D5B'
          context.fillText(`${size}px`, 18 + index * 118, 64 + row * 80)
        }
      }
      return { icons, preview: preview.toDataURL('image/png').split(',')[1] }
    })
    for (const icon of rendered.icons) {
      expect(icon.components, `Both uppercase Fs must remain separate at ${icon.size}px`).toBe(2)
      expect(icon.whitePixels).toBeGreaterThanOrEqual(40)
      await writeFile(testInfo.outputPath(`favicon-${icon.size}.png`), Buffer.from(icon.png, 'base64'))
    }
    await writeFile(testInfo.outputPath('favicon-size-preview.png'), Buffer.from(rendered.preview, 'base64'))

    const response = await request.post('/api/requests', { data: {
      client_name: `Branding Fixture ${width}`, service_description: 'Fictional brand placement check', amount: '1.00', due_date: '2030-11-12',
    } })
    expect(response.status()).toBe(201)
    const item = (await response.json()).request
    await page.goto(new URL(item.payment_url).pathname)
    await expect(page.locator('.client-header img.brand-mark')).toHaveAttribute('src', '/brand-mark.svg')
    await expect(page.locator('.client-header img.brand-mark')).toBeVisible()
    await expect(page.locator('.client-header .sandbox-label')).toHaveText('PayPal sandbox')
    await expect(page.locator('.client-header .brand')).toContainText('Freelance Flow')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.locator('.client-header').screenshot({ path: testInfo.outputPath(`client-brand-${width}.png`) })
    expect(errors).toEqual([])
  })
}
