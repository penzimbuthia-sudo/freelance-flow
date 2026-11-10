import test from 'node:test'
import assert from 'node:assert/strict'
import { dueDate, hasDraftEdits, paymentPresentation, paymentTime, generationError } from '../src/paymentPresentation.js'

const facts = { amount_cents: 100, currency: 'USD', payment_status: 'unpaid', due_date: '2026-11-12', timing: 'future', overdue_days: 0, attempt_outcome: null }

test('future payment facts use saved amount and readable date without claiming lateness', () => {
  assert.deepEqual(paymentPresentation(facts), { explanation: '$1.00 is unpaid. Due 12 Nov 2026.', nextStep: 'share the payment link.' })
  assert.equal(paymentPresentation({ ...facts, amount_cents: 123456 }).explanation, '$1,234.56 is unpaid. Due 12 Nov 2026.')
})
test('today and overdue presentation uses backend timing/day counts, not browser clock', () => {
  assert.equal(paymentPresentation({ ...facts, timing: 'today' }).explanation, '$1.00 is unpaid. Due today, 12 Nov 2026.')
  assert.equal(paymentPresentation({ ...facts, timing: 'overdue', overdue_days: 1 }).explanation, '$1.00 is unpaid. 1 calendar day overdue (due 12 Nov 2026).')
  assert.equal(paymentPresentation({ ...facts, timing: 'overdue', overdue_days: 27 }).explanation, '$1.00 is unpaid. 27 calendar days overdue (due 12 Nov 2026).')
})
test('paid status takes precedence over earlier cancelled or failed attempts', () => {
  for (const attempt_outcome of ['failed', 'cancelled', 'unconfirmed', null]) {
    const result = paymentPresentation({ ...facts, payment_status: 'paid', attempt_outcome })
    assert.equal(result.explanation, '$1.00 is recorded as paid.')
    assert.equal(result.nextStep, 'send a thank-you message.')
  }
})
test('attempt notices do not imply payment or override uncertain capture safeguards', () => {
  for (const attempt_outcome of ['failed', 'cancelled', 'unavailable']) {
    const result = paymentPresentation({ ...facts, attempt_outcome })
    assert.match(result.explanation, /is unpaid/)
    assert.equal(result.nextStep, 'retry checkout using the payment link.')
  }
  assert.equal(paymentPresentation({ ...facts, attempt_outcome: 'unconfirmed' }).nextStep, 'check payment status before trying again.')
})
test('date-only formatting and precise timestamps preserve their respective date conventions', () => {
  assert.equal(dueDate('2026-11-12'), '12 Nov 2026')
  assert.match(paymentTime('2026-11-11T22:15:00+00:00'), /12 Nov 2026, 01:15/)
})
test('only meaningful edited content is dirty; generated, reverted, blank and cleared drafts are clean', () => {
  assert.equal(hasDraftEdits('Generated draft', 'Generated draft'), false)
  assert.equal(hasDraftEdits('  Generated draft\n', 'Generated draft'), false)
  assert.equal(hasDraftEdits('', ''), false)
  assert.equal(hasDraftEdits(' \n ', ''), false)
  assert.equal(hasDraftEdits('Edited draft', 'Generated draft'), true)
  assert.equal(hasDraftEdits('Manual message', ''), true)
  assert.equal(hasDraftEdits('', 'Generated draft'), false)
})
test('known generation failures use product copy without exposing configuration or structured-output mechanics', () => {
  for (const code of ['ai_not_configured', 'ai_model_unavailable', 'ai_rate_limited', 'ai_upstream_error', 'ai_empty_response', 'ai_invalid_response']) {
    const message = generationError({ code, message: 'Internal provider/schema/configuration explanation' })
    assert.doesNotMatch(message, /Internal|schema|configuration|Gemini|GOOGLE_API_KEY/)
    assert.match(message, /message|Message/)
  }
  assert.equal(generationError({ message: 'Check your connection and try again.' }), 'Check your connection and try again.')
  assert.equal(generationError({ code: 'constructor', message: 'Unknown failure' }), 'Unknown failure')
})
test('archived unpaid guidance does not invite payment; archived paid guidance remains a thank-you', () => {
  assert.deepEqual(paymentPresentation(facts, true), { explanation: '$1.00 is unpaid. This request is archived.', nextStep: 'restore the request before sharing the payment link.' })
  assert.equal(paymentPresentation({ ...facts, payment_status: 'paid' }, true).nextStep, 'send a thank-you message.')
})
