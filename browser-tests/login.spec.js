import { test, expect } from '@playwright/test'
import { spawn, execFileSync } from 'node:child_process'
import { once } from 'node:events'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import http from 'node:http'
import https from 'node:https'
import net from 'node:net'
import process from 'node:process'
import { randomBytes } from 'node:crypto'
import { setTimeout as delay } from 'node:timers/promises'
import { fileURLToPath } from 'node:url'

test('native HTTPS form login preserves Origin across an HTTP proxy and keeps Secure cookies', async ({ browser }) => {
  const root = fileURLToPath(new URL('..', import.meta.url))
  const directory = mkdtempSync('/tmp/opencode/ff-native-login-')
  const python = `${root}/.venv/bin/python`
  const password = randomBytes(24).toString('hex') // Ephemeral fictional credentials only.
  let child
  let context
  let proxy
  try {
    execFileSync('openssl', ['req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
      '-keyout', `${directory}/key.pem`, '-out', `${directory}/cert.pem`, '-subj', '/CN=127.0.0.1',
      '-addext', 'subjectAltName=IP:127.0.0.1'], { stdio: 'ignore' })
    const passwordHash = execFileSync(python, ['-c', 'import os; from werkzeug.security import generate_password_hash; print(generate_password_hash(os.environ["FICTIONAL_TEST_PASSWORD"]))'], {
      env: { ...process.env, FICTIONAL_TEST_PASSWORD: password }, encoding: 'utf8',
    }).trim()
    const reservation = net.createServer()
    await new Promise(resolve => reservation.listen(0, '127.0.0.1', resolve))
    const port = reservation.address().port
    await new Promise(resolve => reservation.close(resolve))
    proxy = https.createServer({ key: readFileSync(`${directory}/key.pem`), cert: readFileSync(`${directory}/cert.pem`) }, (request, response) => {
      // TLS terminates here, like Render. Do not inject/trust forwarded headers.
      const upstream = http.request({ hostname: '127.0.0.1', port, path: request.url, method: request.method, headers: request.headers }, result => {
        response.writeHead(result.statusCode, result.headers)
        result.pipe(response)
      })
      upstream.on('error', () => { response.writeHead(502); response.end() })
      request.pipe(upstream)
    })
    await new Promise(resolve => proxy.listen(0, '127.0.0.1', resolve))
    const origin = `https://127.0.0.1:${proxy.address().port}`
    writeFileSync(`${directory}/empty.env`, '', { mode: 0o600 })
    child = spawn(python, ['-m', 'gunicorn', '--config', 'gunicorn.conf.py', 'wsgi:app'], {
      cwd: root, stdio: 'ignore',
      env: { ...process.env, APP_ENV: 'local', RENDER: 'false', PORT: String(port),
        FF_ENV_FILE: `${directory}/empty.env`, FLASK_SKIP_DOTENV: '1',
        DATABASE_PATH: `${directory}/fictional.sqlite3`, DATABASE_URL: '',
        PUBLIC_BASE_URL: origin, APP_HOSTS: '127.0.0.1',
        SECRET_KEY: randomBytes(48).toString('hex'), ADMIN_USERNAME: 'fictional-native-admin', ADMIN_PASSWORD_HASH: passwordHash,
        GOOGLE_API_KEY: '', GEMINI_API_KEY: '', PAYPAL_CLIENT_ID: '', PAYPAL_CLIENT_SECRET: '', PAYPAL_MERCHANT_ID: '' },
    })
    let ready = false
    for (let attempt = 0; attempt < 150; attempt++) {
      expect(child.exitCode).toBeNull()
      try {
        const response = await fetch(`http://127.0.0.1:${port}/healthz`, { signal: AbortSignal.timeout(1000) })
        if (response.ok) { ready = true; break }
      } catch { /* Own test-server readiness only. */ }
      await delay(100)
    }
    expect(ready).toBe(true)
    // Self-signed TLS is ignored only in this isolated local browser context.
    context = await browser.newContext({ ignoreHTTPSErrors: true })
    const page = await context.newPage()
    const loginPage = await page.goto(`${origin}/login`)
    expect(loginPage.headers()['referrer-policy']).toBe('same-origin')
    await page.getByLabel('Username', { exact: true }).fill('fictional-native-admin')
    await page.getByLabel('Password', { exact: true }).fill(password)
    const [submitted] = await Promise.all([
      page.waitForResponse(response => response.url() === `${origin}/login` && response.request().method() === 'POST'),
      page.getByRole('button', { name: 'Sign in', exact: true }).click(),
    ])
    // Do not synthesize Origin/CSRF/Cookie headers: Chromium must generate them.
    expect((await submitted.request().allHeaders()).origin).toBe(origin)
    expect(submitted.status()).toBe(303)
    const session = await context.request.get(`${origin}/api/auth/session`)
    expect(session.status()).toBe(200)
    const { csrf_token: csrf } = await session.json()
    const cookie = (await context.cookies()).find(cookie => cookie.name === '__Host-ff_session')
    expect(cookie.secure && cookie.httpOnly && cookie.sameSite === 'Lax').toBe(true)
    expect((await context.request.get(`${origin}/pay/fictional-token`)).headers()['referrer-policy']).toBe('no-referrer')
    expect((await context.request.post(`${origin}/api/auth/logout`, { headers: { Origin: origin, 'X-CSRF-Token': csrf }, data: {} })).status()).toBe(200)
    expect((await context.request.get(`${origin}/api/settings`)).status()).toBe(401)
  } finally {
    if (context) await context.close()
    if (proxy) {
      proxy.closeAllConnections()
      await new Promise(resolve => proxy.close(resolve))
    }
    if (child && child.exitCode === null) {
      const exited = once(child, 'exit')
      child.kill('SIGTERM')
      await Promise.race([exited, delay(10_000, null, { ref: false })])
      if (child.exitCode === null) { child.kill('SIGKILL'); await exited }
    }
    rmSync(directory, { recursive: true, force: true }) // Only this test's fresh directory.
  }
})
