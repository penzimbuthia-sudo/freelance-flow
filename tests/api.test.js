import assert from 'node:assert/strict'
import { test } from 'node:test'
import { api, post } from '../src/api.js'

test('management writes obtain a same-origin CSRF token', async () => {
  const calls = []
  const original = globalThis.fetch
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options })
    return { ok: true, status: 200, json: async () => url.endsWith('/session') ? { csrf_token: 'fictional-csrf' } : { saved: true } }
  }
  try {
    assert.deepEqual(await post('/requests', { amount: '50.10' }), { saved: true })
    assert.deepEqual(calls.map(call => call.url), ['/api/auth/session', '/api/requests'])
    assert.equal(calls[1].options.headers['X-CSRF-Token'], 'fictional-csrf')
    assert.equal(calls[1].options.credentials, 'same-origin')
  } finally { globalThis.fetch = original }
})

test('public token writes never request a management session', async () => {
  const calls = []
  const original = globalThis.fetch
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options })
    return { ok: true, status: 200, json: async () => ({ sandbox: true }) }
  }
  try {
    await post('/public/requests/fictional/orders')
    assert.equal(calls.length, 1)
    assert.equal(calls[0].options.headers['X-CSRF-Token'], undefined)
    await api('/public/config')
    assert.equal(calls[1].url, '/api/public/config')
  } finally { globalThis.fetch = original }
})

test('expired management session redirects to server login before any write', async () => {
  const originalFetch = globalThis.fetch
  const originalWindow = globalThis.window
  const calls = []
  let redirect
  globalThis.window = { location: { pathname: '/requests/new', search: '', assign: value => { redirect = value } } }
  globalThis.fetch = async url => {
    calls.push(url)
    return { ok: false, status: 401, json: async () => ({ error: { code: 'authentication_required', message: 'Sign in.' } }) }
  }
  try {
    await assert.rejects(post('/requests'), error => error.code === 'authentication_required')
    assert.deepEqual(calls, ['/api/auth/session'])
    assert.equal(redirect, '/login?next=%2Frequests%2Fnew')
  } finally { globalThis.fetch = originalFetch; globalThis.window = originalWindow }
})

test('public errors never redirect clients to management login', async () => {
  const originalFetch = globalThis.fetch
  const originalWindow = globalThis.window
  globalThis.window = { location: { assign: () => assert.fail('Public clients must not be redirected') } }
  globalThis.fetch = async () => ({ ok: false, status: 401, json: async () => ({ error: { code: 'fictional_public_error', message: 'Unavailable.' } }) })
  try {
    await assert.rejects(api('/public/requests/fictional'), error => error.code === 'fictional_public_error')
  } finally { globalThis.fetch = originalFetch; globalThis.window = originalWindow }
})
